"""Voiceprint identity engine. Owner: identity agent.

Online clustering of ECAPA embeddings: a speaker is a duration-weighted centroid plus a few
exemplars. Strong match -> assign; weak match -> new speaker; in between -> best guess flagged
uncertain ("?"). Nobody enrolls. Vendor diarization hints and stereo direction only break ties.
"""
from __future__ import annotations

import json
import os
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .. import config
from ..types import Assignment, Speaker

SR = 16000
# Calibrated with backend/scripts/eval_identity.py on synthetic `say` voices (see eval/out/identity.md).
T_HI = 0.65      # >= : same person
T_LO = 0.40      # <  : someone new
T_MERGE = 0.80   # two speakers whose centroids exceed this are one person (late correction)
MERGE_MIN_N = 3  # ...but only once both have this many confident segments
SHORT = 0.8      # s; shorter segments are weak evidence: never create speakers or move centroids
MIN_EMBED = 0.4  # s; shorter than this we do not even embed
MARGIN_SHORT = 0.15  # short segments must also beat the runner-up by this to be called certain
EXEMPLARS = 6
POOL = 8         # recent in-between segments kept so two that agree can found a new speaker


@dataclass
class _Voice:
    speaker: Speaker
    sum: np.ndarray                 # duration-weighted sum of unit embeddings
    n: int = 0                      # confident segments folded in
    ex: deque = field(default_factory=lambda: deque(maxlen=EXEMPLARS))

    @property
    def centroid(self) -> np.ndarray:
        return self.sum / (np.linalg.norm(self.sum) + 1e-9)

    def score(self, e: np.ndarray) -> float:
        c = float(e @ self.centroid)
        return 0.5 * (c + max(float(e @ x) for x in self.ex)) if self.ex else c

    def add(self, e: np.ndarray, w: float) -> None:
        self.sum = self.sum + w * e
        self.ex.append(e)
        self.n += 1


class IdentityEngine:
    def __init__(self, embed: Callable[[np.ndarray], np.ndarray] | None = None, memory_path=None) -> None:
        self._embed = embed  # lazily becomes Ecapa(); tests inject a fake
        self._memory_path = memory_path or config.VOICE_MEMORY_PATH
        self._memory = False
        self._reset()

    def _reset(self) -> None:
        self._voices: dict[str, _Voice] = {}
        self._mutes: list[tuple[float, float]] = []
        self._hints: dict[str, Counter] = {}   # vendor label -> {our id: confident count}
        self._merges: list[tuple[str, str]] = []
        self._pool: deque = deque(maxlen=POOL)  # (embedding, seconds) of uncertain segments
        self._counter = 0                      # ids/colors are never reused, even after merges

    # ---- main entry -------------------------------------------------------------------
    def assign(self, audio: np.ndarray, t_start: float, t_end: float,
               hint: str | None = None, direction: float | None = None) -> Assignment:
        dur = len(audio) / SR
        if dur < MIN_EMBED or float(np.sqrt(np.mean(audio ** 2) + 1e-12)) < 1e-4:
            return Assignment("UNKNOWN", 0.0, True, False)
        e = self._embedder()(audio)
        short = dur < SHORT
        scores = {sid: v.score(e) for sid, v in self._voices.items()}
        if not scores:
            return Assignment("UNKNOWN", 0.0, True, False) if short else self._new(e, dur, direction, hint, 0.0)

        # hint/direction nudge the ranking only; confidence uses the raw voice score
        def rank(sid: str) -> float:
            b = 0.0
            top = self._hints.get(hint or "")
            if top and top.most_common(1)[0] == (sid, top[sid]) and top[sid] >= 2:
                b += 0.15 if short else 0.05
            d = self._voices[sid].speaker.direction_deg
            if direction is not None and d is not None and abs(d - direction) <= 20:
                b += 0.03
            return scores[sid] + b

        best = max(scores, key=rank)
        s = scores[best]
        second = max((x for k, x in scores.items() if k != best), default=-1.0)
        conf = float(np.clip((s - T_LO) / (0.9 - T_LO), 0.0, 1.0))
        if short:
            if s < T_LO:
                return Assignment("UNKNOWN", 0.0, True, False)
            certain = s >= T_HI and s - second >= MARGIN_SHORT
            return Assignment(best, min(conf, 0.6), not certain, False)
        if s < T_LO:
            return self._new(e, dur, direction, hint, s)
        if s < T_HI:
            # between: keep the guess but flag it. Two in-between segments that agree with each
            # other are a new person who merely resembles an existing one.
            for j, (pe, pd) in enumerate(self._pool):
                if float(e @ pe) >= T_HI:
                    del self._pool[j]
                    a = self._new(e, dur, direction, hint, s)
                    self._voices[a.speaker_id].add(pe, min(pd, 5.0))
                    return a
            self._pool.append((e, dur))
            return Assignment(best, conf, True, False)
        self._fold(best, e, dur, direction, hint)
        self._auto_merge(best)
        return Assignment(best, conf, False, False)

    def match(self, audio: np.ndarray) -> Assignment:
        """Read-only best match against known voices: never creates a speaker or moves a centroid.
        For degraded audio (separated overlap streams) that must not pollute voiceprints."""
        if len(audio) / SR < MIN_EMBED or not self._voices:
            return Assignment("UNKNOWN", 0.0, True, False)
        e = self._embedder()(audio)
        scores = {sid: v.score(e) for sid, v in self._voices.items()}
        best = max(scores, key=scores.get)
        s = scores[best]
        if s < T_LO:
            return Assignment("UNKNOWN", 0.0, True, False)
        return Assignment(best, float(np.clip((s - T_LO) / (0.9 - T_LO), 0.0, 1.0)), s < T_HI, False)

    # ---- speakers ---------------------------------------------------------------------
    def _embedder(self):
        if self._embed is None:
            from .embed import Ecapa
            self._embed = Ecapa()
        return self._embed

    def warmup(self) -> None:
        self._embedder()(np.zeros(SR, dtype=np.float32) + 1e-3)

    def _make(self, e: np.ndarray, w: float, name: str | None = None, source: str | None = None) -> str:
        i = self._counter
        self._counter += 1
        label = f"Speaker {chr(65 + i)}" if i < 26 else f"Speaker {i + 1}"
        sp = Speaker(id=f"S{i + 1}", label=label, name=name, name_source=source, color_index=i)
        v = _Voice(sp, np.zeros_like(e))
        v.add(e, w)
        self._voices[sp.id] = v
        return sp.id

    def _new(self, e, dur, direction, hint, s) -> Assignment:
        sid = self._make(e, min(dur, 5.0))
        self._fold(sid, None, 0, direction, hint)
        return Assignment(sid, float(np.clip(0.5 + 0.5 * (T_LO - s) / T_LO, 0.5, 1.0)), False, True)

    def _fold(self, sid, e, dur, direction, hint) -> None:
        v = self._voices[sid]
        if e is not None:
            v.add(e, min(dur, 5.0))
        if direction is not None:
            d = v.speaker.direction_deg
            v.speaker.direction_deg = direction if d is None else 0.7 * d + 0.3 * direction
        if hint:
            self._hints.setdefault(hint, Counter())[sid] += 1
        self._save()

    def _auto_merge(self, sid: str) -> None:
        a = self._voices[sid]
        for oid, o in list(self._voices.items()):
            if oid != sid and min(a.n, o.n) >= MERGE_MIN_N and float(a.centroid @ o.centroid) >= T_MERGE:
                old, young = sorted((sid, oid), key=lambda k: int(k[1:]))
                self.merge(young, old)
                self._merges.append((young, old))
                return

    def pending_merges(self) -> list[tuple[str, str]]:
        """Automatic late merges since the last call, as (from_id, into_id); the session should
        emit speaker_removed{id: from, merged_into: into} and re-send the `into` speaker."""
        out, self._merges = self._merges, []
        return out

    def rename(self, speaker_id: str, name: str, source: str = "user") -> Speaker | None:
        v = self._voices.get(speaker_id)
        if not v:
            return None
        v.speaker.name, v.speaker.name_source = name, source
        self._save()
        return v.speaker

    def merge(self, from_id: str, into_id: str) -> None:
        a, b = self._voices.get(from_id), self._voices.get(into_id)
        if not a or not b or a is b:
            return
        b.sum, b.n = b.sum + a.sum, b.n + a.n
        b.ex.extend(a.ex)
        if a.speaker.name and not b.speaker.name:
            b.speaker.name, b.speaker.name_source = a.speaker.name, a.speaker.name_source
        for c in self._hints.values():
            if from_id in c:
                c[into_id] += c.pop(from_id)
        del self._voices[from_id]
        self._save()

    def speakers(self) -> list[Speaker]:
        return [v.speaker for v in self._voices.values()]

    # ---- TTS mute windows -------------------------------------------------------------
    def add_mute_window(self, start: float, end: float) -> None:
        self._mutes.append((start, end))

    def is_muted(self, start: float, end: float) -> bool:
        return any(a < end and start < b for a, b in self._mutes)

    # ---- privacy / voice memory -------------------------------------------------------
    def forget_all(self) -> None:
        self._reset()
        self._memory_path.unlink(missing_ok=True)

    def set_voice_memory(self, enabled: bool) -> None:
        """On: load saved voiceprints (embeddings + names only, never audio) and keep saving.
        Off: stop saving and delete the file, so turning the toggle off really forgets."""
        self._memory = enabled
        if not enabled:
            self._memory_path.unlink(missing_ok=True)
            return
        try:
            saved = json.loads(self._memory_path.read_text())["speakers"]
        except (OSError, ValueError, KeyError):
            saved = []
        for r in saved:
            e = np.asarray(r["centroid"], dtype=np.float32)
            known = [v for v in self._voices.values() if float(e @ v.centroid) >= T_HI]
            if known:  # already met in this session: just adopt the remembered name
                if r.get("name") and not known[0].speaker.name:
                    known[0].speaker.name, known[0].speaker.name_source = r["name"], r.get("name_source")
            else:
                sid = self._make(e, 1.0, r.get("name"), r.get("name_source"))
                self._voices[sid].n = min(int(r.get("n", 1)), 5)  # stay adaptable
        self._save()

    def _save(self) -> None:
        if not self._memory:
            return
        rows = [{"name": v.speaker.name, "name_source": v.speaker.name_source, "n": v.n,
                 "centroid": [round(float(x), 5) for x in v.centroid]} for v in self._voices.values()]
        tmp = self._memory_path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"version": 1, "speakers": rows}, f)
        tmp.replace(self._memory_path)
