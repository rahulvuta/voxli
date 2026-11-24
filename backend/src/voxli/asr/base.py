"""ASR engine interface. Owner: pipeline agent."""
from __future__ import annotations

from typing import Awaitable, Callable, Protocol

from ..types import ASRResult

OnResult = Callable[[ASRResult], Awaitable[None]]


class ASREngine(Protocol):
    name: str

    async def start(self, on_result: OnResult) -> None: ...
    async def feed(self, pcm_mono_int16: bytes) -> None: ...
    async def stop(self) -> None: ...


class NullASR:
    """Stub: produces nothing. Replaced by Deepgram live + local Parakeet fallback."""
    name = "offline"

    async def start(self, on_result: OnResult) -> None:
        self.on_result = on_result

    async def feed(self, pcm_mono_int16: bytes) -> None:
        pass

    async def stop(self) -> None:
        pass
