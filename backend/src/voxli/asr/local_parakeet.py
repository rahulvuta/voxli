"""Offline fallback ASR: Silero VAD finds utterances, parakeet-mlx transcribes each one. Owner: pipeline agent.

Interims re-decode the utterance-so-far every ~0.6 s (full-context decoding is far more accurate than
parakeet-mlx's streaming mode, and its draft-token timestamps are unreliable); the final is the
decode at VAD end. All MLX/torch work runs on ONE worker thread (MLX streams are not thread-safe).
"""
from __future__ import annotations

import asyncio
import itertools
import os
import re
import subprocess
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .. import config
from ..types import ASRResult, Word
from .base import OnResult

MODEL_ID = "mlx-community/parakeet-tdt-0.6b-v3"
FRAME = 512  # Silero VAD frame at 16 kHz (32 ms)
PREROLL_FRAMES = 10  # audio kept from before VAD fires so word onsets are not clipped
STEP_FRAMES = 19  # re-decode every ~0.6 s of speech -> interim updates
MAX_UTT_S = 6.0  # force a final: re-decode cost grows with length, and fluent talk rarely pauses long enough for VAD


def _work_around_m5_metal() -> None:
    """MLX 0.32 + macOS 26.1 cannot compile the M5 "NAX" matmul kernels (every matmul with M>1 raises).
    Pretending to be an M4-class GPU makes MLX pick the older kernels. Must run before `import mlx`."""
    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout
    m = re.search(r"Apple M(\d+)", chip)
    if m and int(m.group(1)) >= 5:
        os.environ.setdefault("MLX_METAL_GPU_ARCH", "applegpu_g16s")


_pool = ThreadPoolExecutor(1, thread_name_prefix="local-asr")
_models: dict = {}
_conn_ids = itertools.count(1)


def _load():
    """Load (once) the recognizer and the VAD. Slow on first call: may download weights."""
    if not _models:
        _work_around_m5_metal()
        from parakeet_mlx import from_pretrained
        from silero_vad import load_silero_vad
        _models["asr"], _models["vad"] = from_pretrained(MODEL_ID), load_silero_vad()
    return _models["asr"], _models["vad"]


async def warm_up() -> None:
    await asyncio.get_running_loop().run_in_executor(_pool, _load)


def tokens_to_words(tokens, t0: float) -> list[Word]:
    """Group sub-word tokens into words (a token starting with a space begins a new word)."""
    words: list[Word] = []
    confs: list[list[float]] = []
    for t in tokens:
        if not words or t.text.startswith(" "):
            words.append(Word(w=t.text.strip(), start=t0 + t.start, end=t0 + t.end))
            confs.append([t.confidence])
        else:
            words[-1].w += t.text
            words[-1].end = t0 + t.end
            confs[-1].append(t.confidence)
    for w, c in zip(words, confs):
        w.conf = float(np.mean(c))
    return [w for w in words if w.w]


class LocalParakeet:
    name = "local"

    def __init__(self) -> None:
        self.t0 = 0.0  # session time of the first sample fed
        self.reuse_ids: list[str] = []  # segment ids to adopt first (so a failed-over interim finalizes)
        self.dead = asyncio.Event()
        self.error: str | None = None
        self._conn = next(_conn_ids)
        self._n_seg = 0
        self._model = self._vad = None
        self._carry = np.zeros(0, np.float32)
        self._frames = 0  # frames consumed so far
        self._preroll: deque = deque(maxlen=PREROLL_FRAMES)
        self._since_step = 0
        self._skip_until = 0.0
        self._in_speech = False
        self._buf: list[np.ndarray] | None = None  # frames of the open utterance
        self._seg_id = ""
        self._stream_t0 = 0.0
        self._last_text = ""

    async def start(self, on_result: OnResult) -> None:
        self.on_result = on_result
        try:
            self._model, vad_model = await asyncio.get_running_loop().run_in_executor(_pool, _load)
            from silero_vad import VADIterator
            self._vad = VADIterator(vad_model, threshold=0.5, min_silence_duration_ms=250, speech_pad_ms=100)
        except Exception as e:
            self.error = f"local model unavailable: {type(e).__name__}"
            self.dead.set()
            raise ConnectionError(self.error) from None

    @property
    def idle(self) -> bool:
        return not self._in_speech and self._buf is None

    async def feed(self, pcm_mono_int16: bytes) -> None:
        await self._run(self.feed_sync, pcm_mono_int16)

    async def flush(self) -> None:
        await self._run(self._close)

    async def stop(self) -> None:
        await self.flush()

    async def _run(self, fn, *args) -> None:
        try:
            results = await asyncio.get_running_loop().run_in_executor(_pool, fn, *args)
        except Exception as e:
            self.error = f"local asr failed: {type(e).__name__}"
            self.dead.set()
            return
        for r in results:
            await self.on_result(r)

    # ---- synchronous core, runs on the worker thread ----
    def feed_sync(self, pcm: bytes) -> list[ASRResult]:
        import torch
        x = np.concatenate([self._carry, np.frombuffer(pcm, "<i2").astype(np.float32) / 32768.0])
        out: list[ASRResult] = []
        n = len(x) // FRAME
        for i in range(n):
            f = x[i * FRAME:(i + 1) * FRAME]
            ev = self._vad(torch.from_numpy(f))
            self._frames += 1
            if ev and "start" in ev:
                self._in_speech = True
            if ev and "end" in ev:
                self._in_speech = False
            if self._buf is None:
                self._preroll.append(f)
                if self._in_speech:
                    self._open()
                continue
            self._buf.append(f)
            self._since_step += 1
            long = (self._frames * FRAME / config.SAMPLE_RATE - self._stream_t0) > MAX_UTT_S
            if not self._in_speech or long:
                out += self._close()
            elif self._since_step >= STEP_FRAMES and time.monotonic() >= self._skip_until:
                self._since_step = 0
                t = time.monotonic()
                r = self._step(final=False)
                self._skip_until = time.monotonic() + 2 * (time.monotonic() - t)  # never spend >1/3 of the time on interims
                if r:
                    out.append(r)
        self._carry = x[n * FRAME:]
        return out

    def _open(self) -> None:
        self._buf = list(self._preroll)
        self._since_step = 0
        self._preroll.clear()
        self._stream_t0 = (self._frames - len(self._buf)) * FRAME / config.SAMPLE_RATE
        self._seg_id = self.reuse_ids.pop(0) if self.reuse_ids else f"l{self._conn}-{self._n_seg}"
        self._n_seg += 1
        self._last_text = ""

    def _step(self, final: bool) -> ASRResult | None:
        import mlx.core as mx
        from parakeet_mlx.audio import get_logmel
        audio = np.concatenate(self._buf)
        if float(np.sqrt(np.mean(audio * audio))) < 0.004:
            return None  # near-silence: ASR models hallucinate words here
        mel = get_logmel(mx.array(audio), self._model.preprocessor_config)
        res = self._model.generate(mel)[0]
        words = tokens_to_words([t for s in res.sentences for t in s.tokens], self.t0 + self._stream_t0)
        text = " ".join(w.w for w in words)
        if not words or (text == self._last_text and not final):
            return None
        self._last_text = text
        return ASRResult(text=text, words=words, start=words[0].start, end=words[-1].end, is_final=final,
                         provider="local", segment_id=self._seg_id)

    def _close(self) -> list[ASRResult]:
        if self._buf is None:
            return []
        r = self._step(final=True)
        self._buf = None
        if r is None:
            self.reuse_ids.insert(0, self._seg_id)  # nothing recognised: keep the adopted id for the next one
        return [r] if r else []
