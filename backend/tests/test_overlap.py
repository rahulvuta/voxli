import asyncio

import numpy as np

from voxli.overlap import processor as P

SR = 16000


def _voice(f0, secs=2.0, seed=0):
    t = np.arange(int(secs * SR)) / SR
    ph = 2 * np.pi * np.cumsum(f0 * (1 + 0.02 * np.sin(2 * np.pi * 4 * t + seed))) / SR  # light vibrato
    x = sum(np.sin(h * ph) / h for h in range(1, 20))
    return (0.05 * x / np.sqrt((x ** 2).mean())).astype(np.float32)


def test_si_sdr():
    x = _voice(120)
    n = x + 0.3 * _voice(190)
    assert P.si_sdr(x, x) > 60 and P.si_sdr(n, x) < 15
    assert abs(P.si_sdr(3 * n, x) - P.si_sdr(n, x)) < 0.01  # scale invariant


def test_detect_silence_and_single_voice_none():
    p = P.OverlapProcessor()
    assert p.detect(np.zeros(2 * SR, np.float32), 0.0) == []
    assert p.detect(_voice(120), 0.0) == []


def test_detect_two_voices_span_in_session_time():
    a, b = _voice(110), _voice(173, seed=1)
    mix = a.copy()
    mix[SR // 2:] += b[SR // 2:]  # second voice joins at 0.5 s
    spans = P.OverlapProcessor().detect(mix, 10.0)
    assert spans and spans[0][0] >= 10.0 and spans[-1][1] <= 12.0  # padded by 0.3 s but clipped to the audio
    assert spans[0][0] > 10.0 or spans[0][1] > 10.5


def _fake(streams):
    return lambda name, audio: np.stack([s[: len(audio)] for s in streams])


def test_separate_returns_two_level_matched_streams(monkeypatch):
    a, b = _voice(110), 0.3 * _voice(173, seed=1)
    monkeypatch.setattr(P, "run_model", _fake([b, a]))
    out = asyncio.run(P.OverlapProcessor().separate(a + b, 5.0))
    assert len(out) == 2 and out[0].t0 == 5.0 and abs(out[0].t1 - 7.0) < 1e-6
    assert out[0].energy == 1.0 and out[1].energy < 0.5  # strongest first
    assert all(s.audio.dtype == np.float32 and len(s.audio) == 2 * SR for s in out)


def test_separate_single_speaker_or_too_short_is_empty(monkeypatch):
    a = _voice(110)
    monkeypatch.setattr(P, "run_model", _fake([a, 0.001 * a]))
    assert asyncio.run(P.OverlapProcessor().separate(a, 0.0)) == []
    assert asyncio.run(P.OverlapProcessor().separate(a[: SR // 4], 0.0)) == []
