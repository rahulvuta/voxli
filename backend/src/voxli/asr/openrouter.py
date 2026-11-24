"""Transcribe a short float32 clip with Deepgram Nova-3 via OpenRouter's file endpoint. Owner: pipeline agent.

Used to re-transcribe each separated stream of an overlap. Returns None on any failure (callers
treat separation as best-effort; the live caption is already on screen).
"""
from __future__ import annotations

import base64
import io

import httpx
import numpy as np
import soundfile as sf

from .. import config
from ..types import Word

URL = "https://openrouter.ai/api/v1/audio/transcriptions"
MODEL = "deepgram/nova-3"


def wav_b64(audio: np.ndarray) -> str:
    buf = io.BytesIO()
    sf.write(buf, np.clip(audio, -1, 1), config.SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return base64.b64encode(buf.getvalue()).decode()


def parse(resp: dict, t0: float) -> tuple[str, list[Word]]:
    """OpenRouter STT response -> (text, words with session-relative times)."""
    words = [Word(w=w["word"], start=t0 + w["start"], end=t0 + w["end"], conf=w.get("confidence", 1.0))
             for w in resp.get("words") or [] if w.get("type", "word") == "word" and w.get("word")]
    return str(resp.get("text") or " ".join(w.w for w in words)).strip(), words


async def transcribe(audio: np.ndarray, t0: float, client: httpx.AsyncClient) -> tuple[str, list[Word]] | None:
    body = {"model": MODEL, "language": "en", "input_audio": {"data": wav_b64(audio), "format": "wav"},
            "response_format": "verbose_json", "timestamp_granularities": ["word"]}
    try:
        r = await client.post(URL, json=body, headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"})
        r.raise_for_status()
        text, words = parse(r.json(), t0)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None
    return (text, words) if text else None
