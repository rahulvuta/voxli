import numpy as np
import pytest

from voxli.spatial import doa

SR = 16000


def _voice(n=SR, seed=0):
    rng = np.random.default_rng(seed)
    # band-limited-ish noise with an envelope, like speech
    x = np.convolve(rng.standard_normal(n), np.ones(4) / 4, mode="same")
    return (x * (0.5 + 0.5 * np.sin(np.linspace(0, 20, n)) ** 2) * 0.2).astype(np.float32)


def _delayed(x, delay):  # positive delay: right channel leads, left lags
    left = np.concatenate([np.zeros(delay, np.float32), x])[: len(x)] if delay > 0 else x
    right = x if delay > 0 else np.concatenate([np.zeros(-delay, np.float32), x])[: len(x)]
    return np.stack([left, right], 1)


def test_duplicated_mono_returns_none():
    x = _voice()
    assert doa.estimate(np.stack([x, x], 1)) is None


def test_none_and_silence():
    assert doa.estimate(None) is None
    assert doa.estimate(np.zeros((SR, 2), np.float32)) is None
    assert doa.estimate(_voice()[:, None]) is None


@pytest.mark.parametrize("delay,sign", [(4, 1), (-4, -1), (2, 1)])
def test_side(delay, sign):
    deg, conf = doa.estimate(_delayed(_voice(), delay))
    assert np.sign(deg) == sign and conf > 0.3


def test_angle_value():
    # 0.14 m spacing: 4 samples = 0.25 ms * 343 = 8.6 cm -> asin(0.61) ~ 38 deg
    deg, _ = doa.estimate(_delayed(_voice(), 4))
    assert abs(deg - 38) < 4


def test_noise_still_right_side():
    x = _delayed(_voice(), 3)
    x = x + np.random.default_rng(1).standard_normal(x.shape).astype(np.float32) * 0.02
    deg, _ = doa.estimate(x)
    assert deg > 10
