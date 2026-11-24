"""Session audio ring buffer, in memory only (never written to disk)."""
from __future__ import annotations

import numpy as np

from .config import SAMPLE_RATE


class AudioBuffer:
    def __init__(self, channels: int = 1, max_seconds: float = 300.0):
        self.channels = channels
        self.cap = int(max_seconds * SAMPLE_RATE)
        self.data = np.zeros((self.cap, channels), dtype=np.float32)
        self.total = 0  # samples written since session start

    def append(self, pcm: bytes) -> np.ndarray:
        """Append interleaved Int16 PCM. Returns the new chunk as float32 mono."""
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        x = x[: len(x) - len(x) % self.channels].reshape(-1, self.channels)
        n = len(x)
        idx = (self.total + np.arange(n)) % self.cap
        self.data[idx] = x
        self.total += n
        return x.mean(axis=1)

    def now(self) -> float:
        return self.total / SAMPLE_RATE

    def _slice(self, start: float, end: float) -> np.ndarray:
        a = max(round(start * SAMPLE_RATE), self.total - self.cap, 0)
        b = min(round(end * SAMPLE_RATE), self.total)
        if b <= a:
            return np.zeros((0, self.channels), dtype=np.float32)
        return self.data[np.arange(a, b) % self.cap]

    def mono(self, start: float, end: float) -> np.ndarray:
        return self._slice(start, end).mean(axis=1)

    def stereo(self, start: float, end: float) -> np.ndarray | None:
        return self._slice(start, end) if self.channels == 2 else None

    def clear(self) -> None:
        self.data[:] = 0  # keep `total`: the session clock (and ASR timestamps) must not go backwards


if __name__ == "__main__":  # self-check
    b = AudioBuffer(channels=2, max_seconds=1)
    s = (np.arange(32000) % 100).astype("<i2")  # 1 s stereo interleaved
    b.append(s.tobytes())
    assert abs(b.now() - 1.0) < 1e-9 and b.stereo(0, 1).shape == (16000, 2)
    b.append(s.tobytes())  # wraps
    assert b.mono(0, 0.5).shape == (0,) and b.mono(1.5, 2).shape == (8000,)
    print("audio ok")
