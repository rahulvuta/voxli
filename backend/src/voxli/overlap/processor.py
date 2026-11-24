"""Overlap detection + separation. Owner: overlap agent.

separate(): 2-speaker neural separation (TIGER default, or MossFormer2_SS_16K, vendored under backend/vendor/).
detect(): ungated fallback detector (the pyannote segmentation-3.0 path needs a gated HF token, see docs/dev-log/overlap.md).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from ..types import SeparatedStream

VENDOR = Path(__file__).resolve().parents[3] / "vendor"
DEFAULT_MODEL = os.getenv("VOXLI_SEP_MODEL", "tiger")  # "tiger" | "mossformer2"; chosen from eval/out/overlap.md (TIGER 28% vs 55% cpWER under reverb+noise, equal on clean)
MAX_SPAN_S = 6.0  # longer spans are processed in the first MAX_SPAN_S only (cost grows with length)
MIN_ENERGY_RATIO = 0.05  # weaker/stronger stream energy; below this it was one speaker, not two
SR = 16000

# MPS is 2-5x faster than CPU here (measured on a busy M5: MossFormer2 0.6-1.3 s per audio s, TIGER 1.2-1.4); VOXLI_SEP_DEVICE=cpu overrides.
DEVICE = os.getenv("VOXLI_SEP_DEVICE", "mps" if torch.backends.mps.is_available() else "cpu")
_models: dict[str, torch.nn.Module] = {}
_lock = threading.Lock()  # torch modules are not safe to call from two threads at once


def _load(name: str) -> torch.nn.Module:
    if name in _models:
        return _models[name]
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    from huggingface_hub import hf_hub_download, snapshot_download

    if name == "tiger":
        from safetensors.torch import load_file
        from tiger_sep.tiger import TIGER

        d = snapshot_download("JusperLee/TIGER-speech")
        m = TIGER(**json.load(open(f"{d}/config.json")))
        m.load_state_dict(load_file(f"{d}/model.safetensors"))
    elif name == "mossformer2":
        from mossformer2_ss.mossformer2 import MossFormer2_SS_16K

        args = SimpleNamespace(encoder_embedding_dim=512, mossformer_sequence_dim=512,
                               num_mossformer_layer=24, encoder_kernel_size=16, num_spks=2)
        m = MossFormer2_SS_16K(args).model
        ck = torch.load(hf_hub_download("alibabasglab/MossFormer2_SS_16K", "last_best_checkpoint.pt"),
                        map_location="cpu", weights_only=True)
        m.load_state_dict(ck["model"])
    else:
        raise ValueError(f"unknown separation model {name!r}")
    _models[name] = m.eval().to(DEVICE)
    return m


def run_model(name: str, audio: np.ndarray) -> np.ndarray:
    """float32 mono 16 kHz [n] -> [2, n] raw model outputs (not level-matched)."""
    m = _load(name)
    x = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))[None].to(DEVICE)
    # NNPACK's CPU conv path is ~10x slower than the default for these models (profiled); scoped off, restored after
    with _lock, torch.inference_mode(), torch.backends.nnpack.flags(enabled=False):
        y = m(x[:, None]) if name == "tiger" else torch.stack([o[0] for o in m(x)])[None]
    return y[0, :, : len(audio)].float().cpu().numpy()


def si_sdr(est: np.ndarray, ref: np.ndarray) -> float:
    n = min(len(est), len(ref))
    est, ref = est[:n].astype(np.float64), ref[:n].astype(np.float64)
    est, ref = est - est.mean(), ref - ref.mean()
    target = (est @ ref) / (ref @ ref + 1e-12) * ref
    return float(10 * np.log10((target @ target + 1e-12) / (((est - target) ** 2).sum() + 1e-12)))


FRAME, HOP = 1024, 256  # 64 ms analysis frames, 16 ms hop
LAG_LO, LAG_HI = SR // 400, SR // 70  # f0 search 70-400 Hz
VOICED = 0.45  # YIN aperiodicity below this = periodic; swept 0.35/0.45/0.55: recall 51/67/81%, false-flag 0/4.5/21% of single-speaker audio (separate() re-checks)
MIN_RUN_S, MAX_GAP_S = 0.4, 0.25


def _yin(x: np.ndarray) -> tuple[float, int]:
    """(aperiodicity 0..1+, lag) of the strongest periodicity in x (cumulative-mean-normalised difference)."""
    n = len(x)
    cs = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    r = np.fft.irfft(np.abs(np.fft.rfft(x, 2 * n)) ** 2)[: LAG_HI + 1]
    tau = np.arange(1, LAG_HI + 1)
    d = cs[n - tau] + (cs[n] - cs[tau]) - 2 * r[1:]
    dn = d * tau / (np.cumsum(d) + 1e-12)
    k = int(np.argmin(dn[LAG_LO - 1:])) + LAG_LO - 1
    return float(dn[k]), k + 1


def two_pitch_frames(audio: np.ndarray) -> np.ndarray:
    """Per-frame bool: a second periodic voice remains after cancelling the dominant pitch (de Cheveigne-style).
    shortcut: voiced+voiced overlap only (unvoiced/whispered overlap and noise are not flagged); upgrade = pyannote segmentation-3.0 (gated)."""
    n = max(0, (len(audio) - FRAME) // HOP + 1)
    out = np.zeros(n, bool)
    for i in range(n):
        x = audio[i * HOP: i * HOP + FRAME]
        if np.sqrt((x ** 2).mean()) < 2e-3:
            continue
        a0, t0_ = _yin(x)
        if a0 > 0.8:
            continue  # nothing periodic to cancel
        res = x[:-t0_] - x[t0_:]
        a1, t1_ = _yin(res)
        ratio = t1_ / t0_
        out[i] = a1 < VOICED and abs(ratio - round(ratio)) > 0.08 and np.sqrt((res ** 2).mean()) > 0.15 * np.sqrt((x ** 2).mean())
    return out


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """Merge flagged frames: bridge gaps <= MAX_GAP_S, keep runs >= MIN_RUN_S. Returns (first_frame, last_frame)."""
    idx = np.flatnonzero(flags)
    runs: list[list[int]] = []
    for i in idx:
        if runs and (i - runs[-1][1]) * HOP / SR <= MAX_GAP_S:
            runs[-1][1] = int(i)
        else:
            runs.append([int(i), int(i)])
    return [(a, b) for a, b in runs if ((b - a) * HOP + FRAME) / SR >= MIN_RUN_S]


class OverlapProcessor:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model

    def detect(self, audio: np.ndarray, t0: float) -> list[tuple[float, float]]:
        """Candidate two-voice spans [(start, end)] in session seconds. Cheap pre-gate; separate() confirms."""
        flags = two_pitch_frames(np.asarray(audio, dtype=np.float32))
        end, pad = len(audio) / SR, 0.3  # context helps the separator; spans stay inside the audio given
        return [(t0 + max(0.0, a * HOP / SR - pad), t0 + min(end, (b * HOP + FRAME) / SR + pad)) for a, b in _runs(flags)]

    def warmup(self) -> None:
        """Load weights (downloads on first run) so the first real overlap isn't delayed ~10 s. Call in a thread."""
        run_model(self.model, 1e-3 * np.random.default_rng(0).standard_normal(SR).astype(np.float32))

    async def separate(self, audio: np.ndarray, t0: float) -> list[SeparatedStream]:
        """audio: float32 mono 16 kHz covering the overlap span starting at session time t0.
        Returns two streams (strongest first) or [] if the span holds only one speaker."""
        audio = np.asarray(audio, dtype=np.float32)[: int(MAX_SPAN_S * SR)]
        if len(audio) < SR // 2:
            return []
        raw = await asyncio.to_thread(run_model, self.model, audio)
        e = np.sqrt((raw ** 2).mean(axis=1))
        if e.min() < MIN_ENERGY_RATIO * e.max() or e.max() < 1e-4:
            return []
        target = float(np.sqrt((audio ** 2).mean()))  # model output level is arbitrary; match the input's
        order = np.argsort(-e)
        t1 = t0 + len(audio) / SR
        return [SeparatedStream(audio=(raw[i] / (e[i] + 1e-9) * target).astype(np.float32), t0=t0, t1=t1,
                                energy=float(e[i] / e.max()), extra={"model": self.model}) for i in order]
