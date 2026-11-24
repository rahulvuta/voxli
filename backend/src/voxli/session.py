"""One live captioning session per WebSocket. Owner: pipeline agent.

Flow: audio -> AudioBuffer -> FailoverASR -> (final) identity.assign -> Utterance -> client
                                  |                    -> overlap.detect/separate -> re-transcribe -> "separated" utterances
                                  -> context.on_final -> annotations / name suggestions
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import asdict, replace
from typing import Awaitable, Callable

import httpx

from .asr.failover import FailoverASR
from .asr.openrouter import transcribe
from .audio import AudioBuffer
from .config import SAMPLE_RATE
from .context.engine import ContextEngine
from .identity.engine import IdentityEngine
from .overlap.processor import OverlapProcessor
from .spatial import doa
from .types import ASRResult, Speaker, Utterance

Send = Callable[[dict], Awaitable[None]]
ACTIVE_S = 1.5  # a speaker is "active" this long after their last words
DIRECTION_STEP_DEG = 10.0  # re-send a speaker when its direction moves more than this
BUSY_WINDOW, BUSY_MIN = 6, 4  # >= 4 of the last 6 captions flagged two voices = continuous background chatter, not interruptions
MIN_SPLIT_S = 1.5  # sentences shorter than this join a neighbour: ~1 s sentences ("Yes. It was easy.") embed unreliably and spawned duplicate speakers
TTS_TAIL_S = 0.6  # keep ignoring ASR this long after the phone stops speaking (room echo)
TTS_MAX_S = 30.0  # safety: a tts_start with no tts_end stops muting after this
SPECIAL = {"YOU": Speaker(id="YOU", label="You", name="You", color_index=7),
           "UNKNOWN": Speaker(id="UNKNOWN", label="Unknown speaker", color_index=0)}
RESUME_S = 60.0  # a dropped client may reattach to its session within this long
PARKED: dict[str, Session] = {}  # session_id -> detached session awaiting a reconnect


class Session:
    def __init__(self, send: Send, channels: int = 1, asr=None, identity=None, overlap=None, context=None):
        self.send = send
        self.buffer = AudioBuffer(channels=channels)
        self.session_id: str | None = None
        self.parked_at = 0.0
        self._make_asr = (lambda start_at: asr) if asr else (lambda start_at: FailoverASR(self.buffer, self._on_status, start_at=start_at))
        self.asr = None
        self.identity = identity or IdentityEngine()
        self.overlap = overlap or OverlapProcessor()
        self.context = context or ContextEngine()
        self.history: list[Utterance] = []
        self._utts: dict[str, Utterance] = {}
        self._http = httpx.AsyncClient(timeout=15)
        self._id_lock = asyncio.Lock()  # identity.assign may run on a worker thread; keep it serial
        self._tasks: set[asyncio.Task] = set()
        self._sep_busy = False
        self._ovl_recent: deque[bool] = deque(maxlen=BUSY_WINDOW)
        self._busy_room = False
        self._reset_state()

    def _reset_state(self) -> None:
        self._hint_map: dict[str, str] = {}  # vendor diarization label -> our speaker id (confident finals only)
        self._last_spoke: dict[str, float] = {}  # speaker id -> monotonic time of last words
        self._sent: dict[str, dict] = {}  # speaker id -> last speaker dict sent to the client
        self._special: set[str] = set()  # "YOU"/"UNKNOWN" once announced to the client
        self._tts: dict[str, list] = {}  # tts id -> [start, end|None]
        self._suggestions: dict[str, dict] = {}

    # ---- lifecycle ----
    async def start(self, resume: bool = False) -> None:
        self.asr = self._make_asr(self.buffer.now() if resume else 0.0)  # a reattached session skips the past
        await self._on_status("reconnecting")
        await self.asr.start(self.on_asr)
        self._spawn(self._active_loop())
        if not getattr(self, "_warmed", False):  # model loads take ~7-10 s; assign() waits on the lock
            self._warmed = True
            if hasattr(self.identity, "warmup"):
                self._spawn(self._warm_identity())
            if hasattr(self.overlap, "warmup"):
                self._spawn(asyncio.to_thread(self.overlap.warmup))

    async def detach(self) -> None:
        """Stop ASR and background work but keep speakers/history so the client can reattach."""
        for t in list(self._tasks):
            t.cancel()
        await self.asr.stop()

    async def attach(self, send: Send) -> None:
        self.send = send
        self._sent.clear()  # the new client knows nothing: re-announce every speaker
        self._tts.clear()
        await self.start(resume=True)
        await self._sync_speakers()

    async def stop(self) -> None:
        await self.detach()
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()
        await self.context.aclose()

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def _warm_identity(self) -> None:
        async with self._id_lock:
            await asyncio.to_thread(self.identity.warmup)

    async def _on_status(self, state: str, message: str | None = None) -> None:
        ev = {"type": "status", "asr": state, "stereo": self.buffer.channels == 2}
        if self.session_id:
            ev["session_id"] = self.session_id
        if message:
            ev["message"] = message
        await self.send(ev)

    async def feed(self, pcm: bytes) -> None:
        self.buffer.append(pcm)
        await self.asr.feed(b"")  # the ASR wrapper reads audio from the buffer itself

    # ---- ASR results ----
    def _muted(self, start: float, end: float) -> bool:
        for s, e in self._tts.values():
            if s - 0.2 < end and start < (e + TTS_TAIL_S if e is not None else s + TTS_MAX_S):
                return True
        return False

    def _touch(self, speaker_id: str) -> None:
        if speaker_id not in ("UNKNOWN", "YOU"):
            self._last_spoke[speaker_id] = time.monotonic()

    async def on_asr(self, r: ASRResult) -> None:
        if self._muted(r.start, r.end):
            return  # the phone's own TTS; already shown as a "you" utterance
        uid = f"u_{r.segment_id}"
        if not r.is_final:
            prev = self._utts.get(uid)
            mapped = self._hint_map.get(r.speaker_hint) if r.speaker_hint else None
            sid = mapped or (prev.speaker_id if prev else "UNKNOWN")
            u = Utterance(id=uid, speaker_id=sid, speaker_confidence=0.3 if sid != "UNKNOWN" else 0.0,
                          speaker_uncertain=True, text=r.text, words=r.words, start=r.start, end=r.end, is_final=False)
            self._utts[uid] = u
            self._touch(sid)
            await self._announce(sid)
            await self.send({"type": "utterance", "utterance": asdict(u)})
            return
        groups = await self._voice_groups(r)
        made: list[Utterance] = []
        for k, (words, a, direction) in enumerate(groups):
            gid = uid if k == 0 else f"{uid}_{k}"
            if r.speaker_hint and not a.uncertain and len(groups) == 1:
                self._hint_map[r.speaker_hint] = a.speaker_id
            self._touch(a.speaker_id)
            u = Utterance(id=gid, speaker_id=a.speaker_id, speaker_confidence=a.confidence,
                          speaker_uncertain=a.uncertain, text=" ".join(w.w for w in words), words=words,
                          start=words[0].start, end=words[-1].end, is_final=True, direction_deg=direction)
            made.append(u)
            self._utts[gid] = u
            self.history.append(u)
            await self._announce(u.speaker_id)
            await self.send({"type": "utterance", "utterance": asdict(u)})
            self._spawn(self._context(u))
        if made:
            self._spawn(self._overlap(made, self.buffer.mono(r.start, r.end), r.start))

    async def _voice_groups(self, r: ASRResult) -> list[tuple]:
        """Split a final at sentence ends, identify each sentence's voice, rejoin same-voice neighbours.
        ASR segments can hold several quick turns; one caption must hold one voice.
        Returns [(words, Assignment, direction_deg)]."""
        sents, cur = [], []
        for w in r.words:
            cur.append(w)
            if w.w[-1:] in ".?!":
                sents.append(cur)
                cur = []
        if cur:
            sents.append(cur)
        if not sents:
            return []
        items = []
        for sw in sents:
            s0, s1 = sw[0].start, sw[-1].end
            est = doa.estimate(self.buffer.stereo(s0, s1))
            d = est[0] if est and est[1] > 0.5 else None
            short = len(sents) > 1 and s1 - s0 < MIN_SPLIT_S
            a = None if short else await self._assign(self.buffer.mono(s0, s1), s0, s1, r.speaker_hint, d)
            items.append([sw, a, d])
        if all(a is None for _, a, _ in items):  # every sentence too short alone: identify the whole final
            a = await self._assign(self.buffer.mono(r.start, r.end), r.start, r.end, r.speaker_hint, items[0][2])
            return [(r.words, a, items[0][2])]
        # too-short sentences join the previous voice (or the next one at the start)
        nxt = next(a for _, a, _ in items if a is not None)
        for it in items:
            if it[1] is None:
                it[1] = nxt
            nxt = it[1]
        merged: list = []
        for sw, a, d in items:
            if merged and merged[-1][1].speaker_id == a.speaker_id:
                merged[-1][0] = merged[-1][0] + sw
                if merged[-1][1].uncertain and not a.uncertain:
                    merged[-1][1] = a  # a confident sentence vouches for the group
            else:
                merged.append([sw, a, d])
        return [tuple(m) for m in merged]

    async def _assign(self, audio, start, end, hint=None, direction=None):
        async with self._id_lock:
            return await asyncio.to_thread(self.identity.assign, audio, start, end, hint, direction)

    # ---- speakers ----
    def _view(self, s: Speaker) -> dict:
        return asdict(replace(s, active=time.monotonic() - self._last_spoke.get(s.id, -1e9) < ACTIVE_S))

    async def _sync_speakers(self) -> None:
        """Send `speaker` upserts for anything that changed, `speaker_removed` for merged-away speakers."""
        current = self.identity.speakers() + [SPECIAL[i] for i in sorted(self._special)]
        for frm, into in self.identity.pending_merges():  # identity's late auto-merges (drains the list)
            for u in [*self.history, *self._utts.values()]:
                if u.speaker_id == frm:
                    u.speaker_id = into
            self._hint_map = {k: into if v == frm else v for k, v in self._hint_map.items()}
            self._sent.pop(frm, None)
            self._sent.pop(into, None)  # force a fresh upsert of the surviving speaker
            await self.send({"type": "speaker_removed", "id": frm, "merged_into": into})
        for s in current:
            d, old = self._view(s), self._sent.get(s.id)
            if old and old.get("direction_deg") is not None and d["direction_deg"] is not None \
                    and abs(old["direction_deg"] - d["direction_deg"]) <= DIRECTION_STEP_DEG:
                d["direction_deg"] = old["direction_deg"]  # ignore small direction jitter
            if old != d:
                self._sent[s.id] = d
                await self.send({"type": "speaker", "speaker": d})
        for gone in set(self._sent) - {s.id for s in current}:
            del self._sent[gone]
            await self.send({"type": "speaker_removed", "id": gone})
        for t0, t1, sid in self.identity.pending_relabels():  # a "?" guess turned out to be a new person (after its upsert)
            for u in self.history:
                if u.is_final and u.source == "live" and u.start < t1 and t0 < u.end:
                    u.speaker_id, u.speaker_uncertain = sid, False
                    await self.send({"type": "utterance", "utterance": asdict(u)})

    async def _announce(self, speaker_id: str) -> None:
        """Every speaker (incl. YOU / UNKNOWN) must be upserted before its first utterance."""
        if speaker_id in SPECIAL:
            self._special.add(speaker_id)
        if speaker_id not in self._sent:
            await self._sync_speakers()

    async def _active_loop(self) -> None:
        while True:
            await asyncio.sleep(0.3)
            await self._sync_speakers()

    # ---- overlap ----
    async def _overlap(self, lives: list[Utterance], audio, t0: float) -> None:
        """Background: detect overlap in a final's audio, separate it, re-transcribe each stream."""
        try:
            spans = await asyncio.to_thread(self.overlap.detect, audio, t0)  # cheap (~5 ms per caption second)
        except Exception:
            return  # detection is best-effort
        self._ovl_recent.append(bool(spans))
        busy = sum(self._ovl_recent) >= BUSY_MIN
        if busy != self._busy_room:  # tell the user why overlaps stop (or start) being separated
            self._busy_room = busy
            await self.send({"type": "room", "busy": busy})
        if not spans or busy or self._sep_busy:  # at most one separation in flight; skip rather than queue
            return
        self._sep_busy = True
        try:
            # longest span only: each separation costs ~1 s per audio second, and captions must not queue behind it
            a, b = max(spans, key=lambda sp: sp[1] - sp[0])
            # attach to the caption that covers most of the span
            live = max(lives, key=lambda u: min(u.end, b) - max(u.start, a))
            streams = await self.overlap.separate(self.buffer.mono(a, b), a)
            if len(streams) < 2:
                return
            group, made = f"og_{live.id}", []
            texts = await asyncio.gather(*(transcribe(s.audio, s.t0, self._http) for s in streams))
            for i, (s, tr) in enumerate(zip(streams, texts)):
                if not tr:
                    continue
                async with self._id_lock:  # separated audio is degraded: match only, never create/update voices
                    asg = await asyncio.to_thread(self.identity.match, s.audio)
                made.append(Utterance(id=f"{live.id}_s{i}", speaker_id=asg.speaker_id, speaker_confidence=asg.confidence,
                                      speaker_uncertain=asg.uncertain, text=tr[0], words=tr[1], start=s.t0, end=s.t1,
                                      is_final=True, overlap_group=group, source="separated"))
            if len(made) < 2:
                return  # one voice recovered is just a transcription, not an overlap to show
            live.overlap_group = group
            self.history += made
            for u in made:
                await self._announce(u.speaker_id)
            for u in made:
                await self.send({"type": "utterance", "utterance": asdict(u)})
            await self.send({"type": "utterance", "utterance": asdict(live)})
        except Exception as e:  # separation is best-effort; the live caption stays
            await self.send({"type": "error", "code": "overlap", "message": str(e)[:200]})
        finally:
            self._sep_busy = False

    # ---- context ----
    async def _context(self, u: Utterance) -> None:
        try:
            for ev in await self.context.on_final(u, self.history):
                if ev.get("type") == "name_suggestion":
                    await self._on_suggestion(ev)
                await self.send(ev)
        except Exception as e:  # context is best-effort; captions must keep flowing
            await self.send({"type": "error", "code": "context", "message": str(e)[:200]})

    async def _on_suggestion(self, ev: dict) -> None:
        sid = ev["speaker_id"]
        prev = next((s for s in self.identity.speakers() if s.id == sid), None)
        self._suggestions[ev["id"]] = {"speaker_id": sid, "name": ev["name"], "applied": bool(ev.get("auto_applied")),
                                       "prev": (prev.name, prev.name_source) if prev else (None, None)}
        if ev.get("auto_applied"):
            self.identity.rename(sid, ev["name"], "auto")
            await self._sync_speakers()

    async def _suggestion_response(self, suggestion_id: str, accept: bool) -> None:
        s = self._suggestions.get(suggestion_id)
        if not s:
            raise ValueError(f"unknown suggestion {suggestion_id}")
        if accept and not s["applied"]:
            self.identity.rename(s["speaker_id"], s["name"], "suggested")
            s["applied"] = True
        elif not accept and s["applied"]:  # reject / undo: restore the name that was there before
            self.identity.rename(s["speaker_id"], *s["prev"])
            s["applied"] = False
        self._sent.pop(s["speaker_id"], None)  # always re-send the speaker, even if nothing changed
        await self._sync_speakers()

    # ---- control messages ----
    async def control(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "rename_speaker":
            if not self.identity.rename(msg["speaker_id"], str(msg["name"]), "user"):
                raise ValueError(f"unknown speaker {msg['speaker_id']}")
            await self._sync_speakers()
        elif t == "merge_speakers":
            self.identity.merge(msg["from_id"], msg["into_id"])
            self._sent.pop(msg["from_id"], None)
            await self.send({"type": "speaker_removed", "id": msg["from_id"], "merged_into": msg["into_id"]})
            await self._sync_speakers()
        elif t == "name_suggestion_response":
            await self._suggestion_response(msg["suggestion_id"], bool(msg["accept"]))
        elif t == "tts_start":
            now, tid = self.buffer.now(), str(msg["id"])
            self._tts[tid] = [now, None]
            u = Utterance(id=f"you_{tid}", speaker_id="YOU", speaker_confidence=1.0, speaker_uncertain=False,
                          text=str(msg.get("text", "")), words=[], start=now, end=now, is_final=True, source="you")
            self._utts[u.id] = u
            self.history.append(u)
            await self._announce("YOU")
            await self.send({"type": "utterance", "utterance": asdict(u)})
        elif t == "tts_end":
            tid, now = str(msg["id"]), self.buffer.now()
            if tid in self._tts:
                self._tts[tid][1] = now
                self.identity.add_mute_window(self._tts[tid][0], now + TTS_TAIL_S)
            u = self._utts.get(f"you_{tid}")
            if u:
                u.end = now
                await self.send({"type": "utterance", "utterance": asdict(u)})
        elif t == "catch_up":
            self._spawn(self._reply(self.context.catch_up(self.history, self.identity.speakers(), float(msg.get("seconds", 60)))))
        elif t == "suggest_replies":
            self._spawn(self._reply(self.context.suggest_replies(self.history, self.identity.speakers())))
        elif t == "set_voice_memory":
            self.identity.set_voice_memory(bool(msg["enabled"]))
            await self._sync_speakers()  # remembered speakers get loaded
        elif t == "forget_all":
            self.identity.forget_all()
            self.history.clear()
            self._utts.clear()
            self.buffer.clear()
            for sid in self._sent:
                await self.send({"type": "speaker_removed", "id": sid})
            self._reset_state()
        else:
            raise ValueError(f"unknown message type {t!r}")

    async def _reply(self, coro) -> None:
        try:
            await self.send(await coro)
        except Exception as e:
            await self.send({"type": "error", "code": "context", "message": str(e)[:200]})


def _expire(sid: str, session: Session) -> None:
    if PARKED.get(sid) is session and time.monotonic() - session.parked_at >= RESUME_S - 1:  # not re-parked since
        del PARKED[sid]
        asyncio.get_running_loop().create_task(session.close())


async def run_ws(ws, session_factory=Session) -> None:
    """Drive a Session from a Starlette WebSocket. Bad input yields `error` events, never a crash."""
    async def send(ev: dict) -> None:
        try:
            await ws.send_text(json.dumps(ev))
        except Exception:
            pass  # client went away; the receive loop will notice

    async def error(code: str, message: str) -> None:
        await send({"type": "error", "code": code, "message": message})

    hello: dict = {}
    first = await ws.receive()
    if first["type"] == "websocket.disconnect":
        return
    try:
        hello = json.loads(first["text"])
        if not isinstance(hello, dict) or hello.get("type") != "hello":
            raise ValueError("first message must be a hello object")
        if hello.get("sample_rate") != SAMPLE_RATE:
            await error("bad_hello", f"sample_rate must be {SAMPLE_RATE}")
            await ws.close()
            return
    except (KeyError, TypeError, ValueError) as e:
        await error("bad_hello", str(e)[:200] or "unreadable hello")
        await ws.close()
        return
    sid = hello.get("session_id") if isinstance(hello.get("session_id"), str) else None
    channels = 2 if hello.get("channels") == 2 else 1
    session = PARKED.pop(sid, None) if sid else None
    if session and session.buffer.channels == channels:
        await session.attach(send)  # reconnect within RESUME_S: same speakers, history, clock
    else:
        session = session_factory(send, channels)
        session.session_id = sid
        await session.start()
    try:
        while True:
            m = await ws.receive()
            if m["type"] == "websocket.disconnect":
                break
            try:
                if m.get("bytes") is not None:
                    await session.feed(m["bytes"])
                elif m.get("text") is not None:
                    msg = json.loads(m["text"])
                    if not isinstance(msg, dict):
                        raise ValueError("message must be a JSON object")
                    await session.control(msg)
            except (KeyError, TypeError, ValueError) as e:  # includes json.JSONDecodeError
                await error("bad_message", f"{type(e).__name__}: {str(e)[:150]}")
            except Exception as e:
                await error("internal", f"{type(e).__name__}: {str(e)[:150]}")
    finally:
        if sid:  # keep it around briefly so a flaky connection can resume
            await session.detach()
            PARKED[sid] = session
            session.parked_at = time.monotonic()
            asyncio.get_running_loop().call_later(RESUME_S, _expire, sid, session)
        else:
            await session.stop()
