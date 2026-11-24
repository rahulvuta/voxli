import asyncio

import numpy as np
import pytest

from voxli.asr.failover import FailoverASR
from voxli.audio import AudioBuffer
from voxli.config import SAMPLE_RATE
from voxli.types import ASRResult, Word


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Fake:
    """Engine double. Subclasses set `name`, `fail_connect`."""
    name = "fake"
    fail_connect = False

    def __init__(self):
        self.t0, self.reuse_ids, self.fed, self.stopped = 0.0, [], 0, False
        self.dead, self.error, self.idle = asyncio.Event(), None, True
        self.last_msg = 1e18  # "always just heard from it" unless a test overrides

    async def start(self, on_result):
        if self.fail_connect:
            raise ConnectionError("down")
        self.on_result = on_result

    async def feed(self, pcm):
        self.fed += len(pcm) // 2

    async def stop(self):
        self.stopped = True


def result(seg, start, end, final):
    return ASRResult(text="x", words=[Word("x", start, end)], start=start, end=end, is_final=final,
                     provider="fake", segment_id=seg)


def make(primary, fallback, noise=True, seconds=6.0, **kw):
    buf = AudioBuffer()
    rng = np.random.default_rng(0)
    x = (rng.normal(0, 3000 if noise else 0, int(seconds * SAMPLE_RATE))).astype("<i2")
    buf.append(x.tobytes())
    statuses, got = [], []

    async def on_status(s, m=None):
        statuses.append(s)

    async def on_result(r):
        got.append(r)

    return FailoverASR(buf, on_status, primary=primary, fallback=fallback, **kw), statuses, got, buf


async def on_result_noop(r):
    pass


async def until(cond, timeout=5.0):
    end = asyncio.get_running_loop().time() + timeout
    while not cond():
        assert asyncio.get_running_loop().time() < end, "timed out"
        await asyncio.sleep(0.02)


@pytest.mark.anyio
async def test_primary_unreachable_uses_fallback_with_all_audio():
    class P(Fake):
        name, fail_connect = "deepgram", True
    fbs = []

    class F(Fake):
        name = "local"
        def __init__(self):
            super().__init__(); fbs.append(self)
    asr, statuses, _, buf = make(P, F, retry_s=100)
    await asr.start(on_result_noop)
    await until(lambda: fbs and fbs[0].fed == buf.total)
    assert statuses == ["reconnecting", "local"] and fbs[0].t0 == 0.0
    await asr.stop()


@pytest.mark.anyio
async def test_primary_dies_mid_segment_replays_gap_and_reuses_segment_id():
    prims, fbs = [], []

    class P(Fake):
        name = "deepgram"
        def __init__(self):
            super().__init__(); prims.append(self)

    class F(Fake):
        name = "local"
        def __init__(self):
            super().__init__(); fbs.append(self)
    asr, statuses, got, buf = make(P, F, retry_s=100)
    await asr.start(on_result_noop)
    await until(lambda: prims and prims[0].fed == buf.total)
    await prims[0].on_result(result("p-0", 0.5, 1.5, True))   # committed up to 1.5 s
    await prims[0].on_result(result("p-1", 2.0, 3.0, False))  # open when the connection dies
    prims[0].error = "boom"; prims[0].dead.set()
    await until(lambda: fbs and fbs[0].fed > 0 and fbs[0].fed == buf.total - int(2.0 * SAMPLE_RATE))
    assert fbs[0].t0 == 2.0 and fbs[0].reuse_ids == ["p-1"]
    assert statuses == ["deepgram", "reconnecting", "local"]
    await asr.stop()


@pytest.mark.anyio
async def test_stale_results_from_dropped_engine_are_ignored():
    prims = []

    class P(Fake):
        name = "deepgram"
        def __init__(self):
            super().__init__(); prims.append(self)

    class F(Fake):
        name = "local"
    asr, _, _, buf = make(P, F, retry_s=100)
    seen = []

    async def on_result(r):
        seen.append(r.segment_id)
    await asr.start(on_result)
    await until(lambda: prims and asr.state == "deepgram")
    prims[0].dead.set()
    await until(lambda: asr.state == "local")
    await prims[0].on_result(result("late", 0, 1, True))
    assert seen == []
    await asr.stop()


@pytest.mark.anyio
async def test_silent_primary_while_audio_has_speech_triggers_failover():
    class P(Fake):
        name = "deepgram"
        def __init__(self):
            super().__init__(); self.last_msg = 0.0  # never answers

    class F(Fake):
        name = "local"
    asr, statuses, _, _ = make(P, F, silence_s=0.4, retry_s=100)
    await asr.start(on_result_noop)
    await until(lambda: "local" in statuses)
    assert statuses == ["deepgram", "reconnecting", "local"]
    await asr.stop()


@pytest.mark.anyio
async def test_switches_back_to_primary_when_it_recovers():
    prims, fbs = [], []

    class P(Fake):
        name = "deepgram"
        def __init__(self):
            super().__init__(); prims.append(self); self.fail_connect = len(prims) == 1

    class F(Fake):
        name = "local"
        def __init__(self):
            super().__init__(); fbs.append(self)
    asr, statuses, _, buf = make(P, F, retry_s=1)
    await asr.start(on_result_noop)
    await until(lambda: statuses[-1:] == ["deepgram"] and "local" in statuses)
    assert fbs[0].stopped and asr.active is prims[1]
    assert prims[1].t0 * SAMPLE_RATE == fbs[0].fed  # continues exactly where the fallback stopped
    await asr.stop()
