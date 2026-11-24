"""Shared data classes. Field names mirror docs/CONTRACT.md so asdict() is the wire format."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Word:
    w: str
    start: float
    end: float
    conf: float = 1.0


@dataclass
class ASRResult:
    text: str
    words: list[Word]
    start: float
    end: float
    is_final: bool
    provider: str  # "deepgram" | "local" | "openrouter:<model>"
    segment_id: str  # stable across interim -> final for the same segment
    speaker_hint: str | None = None  # vendor diarization label, only a hint


@dataclass
class Speaker:
    id: str
    label: str
    name: str | None = None
    name_source: str | None = None  # "auto" | "user" | "suggested" | None
    color_index: int = 0
    direction_deg: float | None = None
    active: bool = False


@dataclass
class Utterance:
    id: str
    speaker_id: str
    speaker_confidence: float
    speaker_uncertain: bool
    text: str  # verbatim ASR output, never rewritten
    words: list[Word]
    start: float
    end: float
    is_final: bool
    overlap_group: str | None = None
    source: str = "live"  # "live" | "separated" | "you"
    direction_deg: float | None = None


@dataclass
class Assignment:
    speaker_id: str
    confidence: float
    uncertain: bool
    is_new: bool


@dataclass
class SeparatedStream:
    audio: np.ndarray  # float32 mono 16 kHz
    t0: float
    t1: float
    energy: float = 0.0
    extra: dict = field(default_factory=dict)
