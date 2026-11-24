"""Stream a wav file through the real Session and print every server event as one JSON line.

    uv run python scripts/replay.py ../eval/clips/turns_2spk.wav --realtime
    DEEPGRAM_API_KEY=bad uv run python scripts/replay.py clip.wav --realtime      # force local fallback
    uv run python scripts/replay.py clip.wav --realtime --kill-dg-at 6            # drop Deepgram mid-stream

Each line is the event plus `_t` (wall seconds since replay start). The last line is
{"type":"replay_summary", ...} with first-word latency (meaningful only with --realtime).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from voxli.config import SAMPLE_RATE  # noqa: E402
from voxli.asr.local_parakeet import warm_up  # noqa: E402
from voxli.session import Session  # noqa: E402

CHUNK_S = 0.1


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--realtime", action="store_true", help="pace audio at 1x (needed for latency numbers)")
    ap.add_argument("--no-interim", action="store_true", help="do not print interim utterances")
    ap.add_argument("--kill-dg-at", type=float, help="close the Deepgram socket at this audio time (s)")
    ap.add_argument("--tail", type=float, default=4.0, help="seconds to wait after the audio ends")
    args = ap.parse_args()

    x, sr = sf.read(args.wav, dtype="float32", always_2d=True)
    if sr != SAMPLE_RATE:
        x = resample_poly(x, SAMPLE_RATE, sr, axis=0).astype(np.float32)
    x = x[:, :2]
    pcm = (x.clip(-1, 1) * 32767).astype("<i2")
    pcm = np.concatenate([pcm, np.zeros((int(1.5 * SAMPLE_RATE), pcm.shape[1]), "<i2")])  # let endpointing fire

    events: list[dict] = []
    t_start = time.monotonic()

    async def send(ev: dict) -> None:
        ev = {**ev, "_t": round(time.monotonic() - t_start, 3)}
        events.append(ev)
        if not (args.no_interim and ev["type"] == "utterance" and not ev["utterance"]["is_final"]):
            print(json.dumps(ev), flush=True)

    lag = {"max": 0.0}

    async def watch_loop() -> None:  # a blocked event loop would starve the websockets: report it
        while True:
            t = time.monotonic()
            await asyncio.sleep(0.05)
            lag["max"] = max(lag["max"], time.monotonic() - t - 0.05)

    monitor = asyncio.create_task(watch_loop())
    warm = asyncio.create_task(warm_up())  # the server preloads the on-device model at startup; do the same
    s = Session(send, channels=x.shape[1])
    await s.start()
    step, killed = int(CHUNK_S * SAMPLE_RATE), False
    t_start = time.monotonic()  # audio position p is "spoken" at wall time p
    for i in range(0, len(pcm), step):
        if args.realtime:
            await asyncio.sleep(max(0.0, t_start + i / SAMPLE_RATE - time.monotonic()))
        if args.kill_dg_at is not None and not killed and i / SAMPLE_RATE >= args.kill_dg_at:
            eng = getattr(s.asr, "active", None)
            if eng is not None and eng.name == "deepgram":
                await eng._ws.close()
                killed = True
        await s.feed(pcm[i:i + step].tobytes())
    await asyncio.sleep(args.tail)
    await s.stop()
    monitor.cancel()
    warm.cancel()

    utts = [e["utterance"] for e in events if e["type"] == "utterance" and e["utterance"]["text"].strip()]
    summary: dict = {"type": "replay_summary", "realtime": args.realtime, "audio_s": round(len(x) / SAMPLE_RATE, 2),
                     "finals": sum(u["is_final"] for u in utts), "max_event_loop_lag_ms": round(lag["max"] * 1000),
                     "status": [e["asr"] for e in events if e["type"] == "status"],
                     "errors": [e["message"] for e in events if e["type"] == "error"]}
    first = next(((e["_t"], e["utterance"]) for e in events if e["type"] == "utterance"
                  and e["utterance"]["text"].strip() and e["utterance"]["words"]), None)
    if first and args.realtime:
        t, u = first
        # the first interim's timestamps can be unstable: take the word's end from the first final instead
        fin = next((e["utterance"] for e in events if e["type"] == "utterance" and e["utterance"]["is_final"]
                    and e["utterance"]["words"]), u)
        w = fin["words"][0]
        summary["first_word_latency_ms_after_word_ends"] = round((t - w["end"]) * 1000)
        summary["first_word_latency_ms_after_speech_onset"] = round((t - w["start"]) * 1000)
        lags = [(e["_t"] - e["utterance"]["end"]) * 1000 for e in events
                if e["type"] == "utterance" and e["utterance"]["is_final"] and e["utterance"]["text"].strip()]
        summary["final_lag_ms_median"] = round(statistics.median(lags)) if lags else None
    print(json.dumps(summary), flush=True)
    print(f"first-word latency: {summary.get('first_word_latency_ms_after_word_ends', 'n/a (use --realtime)')} ms "
          f"after the word ends; finals={summary['finals']}; asr status: {' -> '.join(summary['status'])}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
