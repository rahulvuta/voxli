"""Direction of arrival from the two phone mics via GCC-PHAT. Owner: overlap agent."""
from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000
MIC_SPACING_M = 0.14  # assumed phone mic spacing (long edge); configurable via estimate(mic_spacing=)
SPEED_OF_SOUND = 343.0
MIN_RMS = 1e-3  # below this the channels are too quiet to localise
MIN_CONF = 0.15  # shortcut: PHAT peak-to-median ratio threshold picked on synthetic data; recalibrate on real phones


def is_duplicated_mono(stereo: np.ndarray, tol: float = 1e-3) -> bool:
    """iPhone Safari returns the same signal on both channels."""
    l, r = stereo[:, 0], stereo[:, 1]
    return float(np.max(np.abs(l - r))) <= tol * max(float(np.max(np.abs(l))), 1e-9)


def estimate(stereo: np.ndarray | None, mic_spacing: float = MIC_SPACING_M,
             sr: int = SAMPLE_RATE) -> tuple[float, float] | None:
    """stereo: float32 [n, 2] at 16 kHz. Returns (deg -90..90, confidence 0..1) or None.

    Channel 0 = left mic, channel 1 = right mic. A source on the right reaches the right mic earlier,
    so right channel leads and the angle is positive.
    """
    if stereo is None or stereo.ndim != 2 or stereo.shape[1] != 2 or stereo.shape[0] < sr // 10:
        return None
    x = stereo.astype(np.float32)
    if is_duplicated_mono(x) or float(np.sqrt(np.mean(x ** 2))) < MIN_RMS:
        return None
    n = 1 << int(np.ceil(np.log2(2 * len(x))))
    L, R = np.fft.rfft(x[:, 0], n), np.fft.rfft(x[:, 1], n)
    cross = L * np.conj(R)
    cc = np.fft.irfft(cross / (np.abs(cross) + 1e-12), n)
    max_lag = max(1, int(np.ceil(mic_spacing / SPEED_OF_SOUND * sr)))
    cc = np.concatenate([cc[-max_lag:], cc[:max_lag + 1]])  # lags -max_lag..+max_lag
    k = int(np.argmax(cc))
    lag = k - max_lag + _parabolic(cc, k)  # samples; >0 means L lags R, i.e. source on the right
    sin = np.clip(lag / sr * SPEED_OF_SOUND / mic_spacing, -1.0, 1.0)
    conf = float(np.clip((cc[k] - np.median(np.abs(cc))) / (cc[k] + 1e-12), 0.0, 1.0)) * float(np.clip(cc[k] * 4, 0, 1))
    if conf < MIN_CONF:
        return None
    return float(np.degrees(np.arcsin(sin))), conf


def _parabolic(cc: np.ndarray, k: int) -> float:
    if 0 < k < len(cc) - 1:
        a, b, c = cc[k - 1], cc[k], cc[k + 1]
        d = a - 2 * b + c
        if d != 0:
            return float(0.5 * (a - c) / d)
    return 0.0
