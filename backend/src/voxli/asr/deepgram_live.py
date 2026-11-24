"""Deepgram live (Nova-3) streaming ASR over a raw WebSocket. Owner: pipeline agent.

Deepgram sends is_final chunks that are pieces of one utterance (ended by speech_final or
UtteranceEnd). We turn each utterance into one segment: interims show finals-so-far + the
current guess; the segment id is stable from first interim to final.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import time
from collections import Counter
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from .. import config
from ..types import ASRResult, Word
from .base import OnResult

URL = "wss://api.deepgram.com/v1/listen"
PARAMS = {
    "model": "nova-3", "language": "en", "encoding": "linear16", "sample_rate": config.SAMPLE_RATE,
    "channels": 1, "interim_results": "true", "smart_format": "true", "punctuate": "true",
    "diarize": "true", "utterance_end_ms": 1000, "vad_events": "true", "endpointing": 300,
}
MAX_SEGMENT_WORDS = 40
SENTENCE_GAP = 0.3  # seconds of silence after .?! that starts a new caption segment
TURN_GAP = 0.15  # a diarization speaker change needs this much pause (or a sentence end) to split


def _breaks(prev, nxt) -> bool:
    """Start a new segment between two (Word, dg_speaker) items?"""
    gap = nxt[0].start - prev[0].end
    sentence_end = prev[0].w[-1] in ".?!"
    if sentence_end and gap >= SENTENCE_GAP:
        return True
    # Turn change per Deepgram's word labels: one caption must hold one voice, or identity embeds a mix.
    return prev[1] is not None and nxt[1] is not None and prev[1] != nxt[1] and (sentence_end or gap >= TURN_GAP)
_conn_ids = itertools.count(1)


class DeepgramLive:
    name = "deepgram"

    def __init__(self, api_key: str | None = None, url: str = URL):
        self.api_key = config.DEEPGRAM_API_KEY if api_key is None else api_key
        self.url = f"{url}?{urlencode(PARAMS)}"
        self.t0 = 0.0  # session time of the first audio byte sent (set by the failover wrapper)
        self.dead = asyncio.Event()  # set when the connection is lost
        self.error: str | None = None
        self.last_msg = time.monotonic()  # any message at all counts as "Deepgram is alive"
        self._conn = next(_conn_ids)
        self._seg = 0
        self._cut = 0.0  # words starting before this were already emitted in a final
        self._acc: list[tuple[Word, int | None]] = []  # finalized chunks of the current segment
        self._ws = None
        self._tasks: list[asyncio.Task] = []

    async def start(self, on_result: OnResult) -> None:
        self.on_result = on_result
        try:
            self._ws = await connect(self.url, additional_headers={"Authorization": f"Token {self.api_key}"},
                                     open_timeout=4, ping_interval=None, max_size=2**22)
        except Exception as e:  # never include the URL/headers: the key lives there
            raise ConnectionError(f"deepgram connect failed: {type(e).__name__} {getattr(getattr(e, 'response', None), 'status_code', '')}") from None
        self.last_msg = time.monotonic()
        self._tasks = [asyncio.create_task(self._recv()), asyncio.create_task(self._keepalive())]

    async def feed(self, pcm_mono_int16: bytes) -> None:
        try:
            await self._ws.send(pcm_mono_int16)
        except Exception as e:
            self._die(type(e).__name__)

    async def flush(self) -> None:  # Deepgram holds no utterance we need to force out; stop() drains it
        pass

    @property
    def idle(self) -> bool:
        return not self._acc

    async def stop(self) -> None:
        if self._ws and not self.dead.is_set():
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await asyncio.wait_for(self._tasks[0], 3)  # server flushes remaining finals, then closes
            except Exception:
                pass
        for t in self._tasks:
            t.cancel()
        if self._ws:
            await self._ws.close()

    def _die(self, why: str) -> None:
        self.error = self.error or why
        self.dead.set()

    async def _keepalive(self) -> None:
        while True:
            await asyncio.sleep(5)
            try:
                await self._ws.send(json.dumps({"type": "KeepAlive"}))
            except Exception as e:
                return self._die(type(e).__name__)

    async def _recv(self) -> None:
        try:
            async for raw in self._ws:
                self.last_msg = time.monotonic()
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                for r in self.handle(msg):
                    await self.on_result(r)
        except Exception as e:
            self._die(type(e).__name__)
        else:
            self._die("closed")

    # ---- pure message -> ASRResult mapping (unit-tested) ----
    def handle(self, msg: dict) -> list[ASRResult]:
        if not isinstance(msg, dict):
            return []
        kind = msg.get("type")
        if kind == "Error":
            self._die(str(msg.get("description") or msg.get("message") or "error")[:100])
            return []
        if kind == "UtteranceEnd":
            return self._finish()
        if kind != "Results":
            return []
        try:
            ws = msg["channel"]["alternatives"][0].get("words", [])
            items = [(Word(w=w.get("punctuated_word") or w["word"], start=w["start"] + self.t0,
                           end=w["end"] + self.t0, conf=w.get("confidence", 1.0)), w.get("speaker")) for w in ws]
        except (KeyError, IndexError, TypeError, AttributeError):
            return []  # malformed Results: skip, keep the stream alive
        items = [i for i in items if i[0].start >= self._cut - 0.01]  # drop re-sent words we already finalized
        is_final = bool(msg.get("is_final"))
        if not items and not (is_final and msg.get("speech_final")):
            return []
        # Sentences followed by a pause become their own finals right away; the tail stays open.
        cur = self._acc + items
        groups = [[]]
        for prev, nxt in zip([None] + cur, cur):
            if prev and _breaks(prev, nxt):
                groups.append([])
            groups[-1].append(nxt)
        out = []
        for g in groups[:-1]:
            out.append(self._result(g, True))
            self._seg += 1
            self._cut = g[-1][0].end
        self._acc = [i for i in self._acc if i[0].start >= self._cut - 0.01]
        tail = groups[-1]
        if not is_final:
            return out + ([self._result(tail, False)] if tail else [])
        self._acc = tail
        # is_final words never change, so a finished sentence can go out now; waiting for speech_final
        # stalls for many seconds in continuous background noise where Deepgram never sees a pause.
        sentence_done = bool(tail) and tail[-1][0].w[-1:] in ".?!"
        if msg.get("speech_final") or sentence_done or len(tail) >= MAX_SEGMENT_WORDS:
            out += self._finish()
        return out

    def _result(self, items: list, final: bool) -> ASRResult:
        words = [w for w, _ in items]
        hints = [str(s) for _, s in items if s is not None]
        hint = Counter(hints).most_common(1)[0][0] if hints else None
        return ASRResult(text=" ".join(w.w for w in words), words=words, start=words[0].start,
                         end=words[-1].end, is_final=final, provider="deepgram",
                         segment_id=f"d{self._conn}-{self._seg}", speaker_hint=hint)

    def _finish(self) -> list[ASRResult]:
        out = []
        while self._acc:
            n = next((i for i in range(1, len(self._acc)) if _breaks(self._acc[i - 1], self._acc[i])), len(self._acc))
            out.append(self._result(self._acc[:n], True))
            self._cut = self._acc[n - 1][0].end
            self._acc, self._seg = self._acc[n:], self._seg + 1
        return out
