"""Speaker embeddings: SpeechBrain ECAPA-TDNN (192-d), run on CPU.

CPU beat MPS in our measurements (15-45 ms vs 40-95 ms per 1-6 s segment, MPS pays
per-shape overhead on short variable-length inputs), so CPU is the default.
"""
from __future__ import annotations

import numpy as np

from ..config import ROOT

CACHE = ROOT / "backend" / "models_cache" / "ecapa"
MAX_SECONDS = 10  # cap cost on long segments; speaker identity saturates well before this


class Ecapa:
    def __init__(self, device: str = "cpu") -> None:
        import torch
        from speechbrain.inference.speaker import EncoderClassifier

        self._torch = torch
        self._model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb", savedir=str(CACHE), run_opts={"device": device})
        self._device = device

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        """float32 mono 16 kHz -> L2-normalised 192-d embedding."""
        x = self._torch.from_numpy(np.ascontiguousarray(audio[: 16000 * MAX_SECONDS], dtype=np.float32))
        with self._torch.no_grad():
            e = self._model.encode_batch(x[None].to(self._device))[0, 0].cpu().numpy()
        return e / (np.linalg.norm(e) + 1e-9)
