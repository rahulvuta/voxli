"""Deepgram-first ASR with automatic fall back to on-device Parakeet. Owner: pipeline agent.

The wrapper owns the audio cursor: it pumps AudioBuffer -> active engine in order. A switch just
moves the cursor back to where the dead engine last committed, so the gap is replayed into the
new engine (faster than real time) and no captions are lost. Interim segments the dead engine
had open are handed to the new engine so the same utterance id finalizes.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

import numpy as np

from ..audio import AudioBuffer
from ..config import SAMPLE_RATE
from .base import OnResult
from .deepgram_live import DeepgramLive
from .local_parakeet import LocalParakeet

OnStatus = Callable[[str, str | None], Awaitable[None]]
CHUNK = SAMPLE_RATE // 2  # replay/pump granularity: 0.5 s
SPEECH_RMS = 0.01  # about -40 dBFS: "there is speech in this audio"
MAX_REPLAY_S = 60.0


class FailoverASR:
    def __init__(self, buffer: AudioBuffer, on_status: OnStatus | None = None, primary=DeepgramLive,
                 fallback=LocalParakeet, silence_s: float = 2.0, retry_s: float = 5.0, start_at: float = 0.0):
        self.buffer, self.on_status = buffer, on_status
        self.primary, self.fallback = primary, fallback
        self.silence_s, self.retry_s = silence_s, retry_s
        self.state = "reconnecting"
        self.active = None  # engine currently receiving audio
        self._accepting = None  # engine whose results we forward
        self._pos = 0  # next sample to send to `active`
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._pending: dict[str, float] = {}  # segment_id -> start of segments with no final yet
        self._committed = start_at  # end time of the last final we forwarded
        self._speech_since: float | None = None
        self._tasks: list[asyncio.Task] = []

    @property
    def name(self) -> str:
        return self.state

    async def start(self, on_result: OnResult) -> None:
        self.on_result = on_result
        await self._set("reconnecting")
        self._tasks = [asyncio.create_task(self._supervise()), asyncio.create_task(self._pump_loop())]

    async def feed(self, pcm_mono_int16: bytes = b"") -> None:
        self._wake.set()  # audio itself is read from the AudioBuffer so replay and live share one path

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await self._pump_once()
        if self.active:
            await self.active.stop()
        self.active = self._accepting = None

    # ---- internals ----
    async def _set(self, state: str, message: str | None = None) -> None:
        if state != self.state or message:
            self.state = state
            if self.on_status:
                await self.on_status(state, message)

    def _cb(self, eng) -> OnResult:
        async def cb(r):
            if eng is not self._accepting:
                return
            if r.is_final:
                self._pending.pop(r.segment_id, None)
                self._committed = max(self._committed, r.end)
            else:
                self._pending.setdefault(r.segment_id, r.start)
            await self.on_result(r)
        return cb

    async def _activate(self, eng, old=None) -> None:
        """Make `eng` the active engine. With `old`, hand over cleanly (finish its utterance first)."""
        if old:
            end = time.monotonic() + 3
            while not old.idle and time.monotonic() < end:
                await asyncio.sleep(0.1)
        async with self._lock:
            if old:
                self.active = None
                await old.stop()  # emits its pending final; results still accepted
                resume = self._pos / SAMPLE_RATE
            else:
                resume = max(min(self._pending.values(), default=self._committed), self.buffer.now() - MAX_REPLAY_S, 0.0)
                eng.reuse_ids = [i for i, _ in sorted(self._pending.items(), key=lambda kv: kv[1])] if hasattr(eng, "reuse_ids") else []
                self._pending.clear()
            eng.t0 = resume
            self._pos = round(resume * SAMPLE_RATE)
            self._accepting, self.active = eng, eng
        self._wake.set()

    async def _drop(self, eng) -> None:
        if self.active is eng:
            self.active = None
        if self._accepting is eng:
            self._accepting = None
        try:
            await asyncio.wait_for(eng.stop(), 5)
        except Exception:
            pass

    async def _supervise(self) -> None:
        while True:
            eng = self.primary()
            try:
                await asyncio.wait_for(eng.start(self._cb(eng)), 6)
            except Exception as e:
                eng, why = None, str(e)
            if eng:
                await self._activate(eng, old=self.active)
                await self._set(eng.name)
                why = await self._watch(eng)
                await self._drop(eng)
            if self.active is None:
                await self._set("reconnecting", f"{self.primary.name} unavailable ({why}); switching to on-device recognition")
                fb = self.fallback()
                try:
                    await fb.start(self._cb(fb))
                    await self._activate(fb)
                    await self._set(fb.name)
                except Exception as e:
                    await self._set("offline", str(e))
            for _ in range(int(self.retry_s)):  # fallback running; try Deepgram again in a few seconds
                await asyncio.sleep(1)
                if self.active is not None and self.active.dead.is_set():
                    await self._drop(self.active)
                    await self._set("offline", "on-device recognition failed")

    async def _watch(self, eng) -> str:
        """Return why the primary engine is no longer usable."""
        while True:
            await asyncio.sleep(0.25)
            if eng.dead.is_set():
                return eng.error or "connection lost"
            s = self._speech_since
            if s is not None and eng.last_msg >= s:
                self._speech_since = None  # it answered after the speech started: alive
            elif s is not None and time.monotonic() - s > self.silence_s:
                return f"no response for {self.silence_s:.0f}s while audio has speech"

    async def _pump_loop(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            await self._pump_once()

    async def _pump_once(self) -> None:
        async with self._lock:
            eng = self.active
            while eng is not None and eng is self.active and self._pos < self.buffer.total:
                end = min(self.buffer.total, self._pos + CHUNK)
                x = self.buffer.mono(self._pos / SAMPLE_RATE, end / SAMPLE_RATE)
                self._pos = end
                if self._speech_since is None and len(x) and float(np.sqrt(np.mean(x * x))) > SPEECH_RMS:
                    self._speech_since = time.monotonic()
                await eng.feed((x * 32767).clip(-32768, 32767).astype("<i2").tobytes())
