"""A1 evidence: WER + latency + cost of ASR options on the SYNTHETIC clips in eval/clips/.

    cd backend && uv run python scripts/eval_asr.py [--clips id1,id2] [--skip deepgram_live,parakeet_mlx]

Engines:
  deepgram_live   Deepgram nova-3 streaming WebSocket, audio sent in real time (100 ms chunks)
  or:<model>      OpenRouter POST /api/v1/audio/transcriptions (whole clip, batch): deepgram/nova-3,
                  nvidia/parakeet-tdt-0.6b-v3, openai/whisper-large-v3-turbo
  parakeet_mlx    local parakeet-tdt-0.6b-v3 on Apple Silicon (MLX), batch
Writes eval/out/asr.md and eval/out/asr.json. Keys come from voxli.config and are never printed.
Cost: OpenRouter returns usage.cost per call (recorded); Deepgram live and local use PRICES below.
Limits: synthetic TTS speech (cleaner than real speech), one run per cell unless --repeat.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import statistics
import time
from pathlib import Path

import httpx
import jiwer
import soundfile as sf
import websockets

from voxli import config

ROOT = config.ROOT
CLIPS = ROOT / "eval" / "clips"
OUT = ROOT / "eval" / "out"
OR_MODELS = ["deepgram/nova-3", "nvidia/parakeet-tdt-0.6b-v3", "openai/whisper-large-v3-turbo"]
DEFAULT_CLIPS = ["turns_2spk", "cafe_4spk", "noisy_cafe_babble_snr10", "noisy_cafe_babble_snr5",
                 "noisy_turns_pink_snr10", "overlap_2spk_2s", "selfintro_sarah", "introduced_marcus"]
# USD per audio minute. Deepgram live: pay-as-you-go streaming Nova-3 list price, see docs/EVIDENCE.md for the URL
# and the date it was read. Local = $0 marginal (own hardware).
PRICES = {"deepgram_live": 0.0048, "parakeet_mlx": 0.0}

# ---------- text normalisation (TTS says "twenty five dollars"; ASR may write "$25") ----------
_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _int_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + _int_words(n % 100))
    return str(n)


def normalize(s: str) -> str:
    s = s.lower().replace("’", "'")
    s = re.sub(r"\$(\d+)", lambda m: f"{m.group(1)} dollars", s)
    s = re.sub(r"(\d{1,2}):(\d{2})", lambda m: f"{m.group(1)} {'oh ' + m.group(2)[1] if m.group(2)[0] == '0' else m.group(2)}", s)
    s = re.sub(r"\d+", lambda m: _int_words(int(m.group())), s)
    s = s.replace("-", " ")
    s = re.sub(r"\bok\b", "okay", s)
    s = re.sub(r"[^a-z' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def wer(ref: str, hyp: str) -> float:
    r, h = normalize(ref), normalize(hyp)
    return jiwer.wer(r, h) if h else 1.0


# ---------- engines ----------
async def deepgram_live(path: Path):
    """Stream in real time. Returns (text, metrics). Latency = wall-clock arrival of a result minus the
    audio time at which the transcribed words had ended (so 0 would be 'instant')."""
    x, sr = sf.read(path, dtype="int16")
    if x.ndim > 1:
        x = x[:, 0]
    pcm = x.tobytes()
    url = ("wss://api.deepgram.com/v1/listen?model=nova-3&encoding=linear16&sample_rate=16000&channels=1"
           "&interim_results=true&smart_format=true&punctuate=true&endpointing=300&utterance_end_ms=1000")
    finals, final_lat, first_word_lat, arrivals, t0 = [], [], [], [], None

    async def reader(ws):
        async for msg in ws:
            m = json.loads(msg)
            if m.get("type") != "Results":
                continue
            alt = m["channel"]["alternatives"][0]
            if not alt["transcript"].strip():
                continue
            now = time.monotonic() - t0
            end_audio = m["start"] + m["duration"]
            if not first_word_lat and alt.get("words"):
                # first caption delay: arrival minus the audio time the first word STARTED (word 'end' of a
                # first interim is unreliable: seen 2.7 s for a word that ended at ~1 s)
                first_word_lat.append(now - alt["words"][0]["start"])
            arrivals.append(now)
            if m.get("is_final"):
                finals.append(alt["transcript"])
                final_lat.append(now - end_audio)

    async with websockets.connect(url, additional_headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"}) as ws:
        rd = asyncio.create_task(reader(ws))
        t0 = time.monotonic()
        step = 3200  # 100 ms of int16 mono
        for i in range(0, len(pcm), step):
            await ws.send(pcm[i: i + step])
            await asyncio.sleep(max(0.0, t0 + (i + step) / 32000 - time.monotonic()))
        await ws.send(json.dumps({"type": "CloseStream"}))
        await asyncio.wait_for(rd, timeout=15)
    return " ".join(finals), {
        "first_word_latency_s": first_word_lat[0] if first_word_lat else None,
        "interim_interval_med_s": statistics.median([b - a for a, b in zip(arrivals, arrivals[1:])]) if len(arrivals) > 1 else None,
        "final_latency_med_s": statistics.median(final_lat) if final_lat else None,
        "final_latency_p90_s": sorted(final_lat)[int(0.9 * (len(final_lat) - 1))] if final_lat else None}


async def openrouter(model: str, path: Path, client: httpx.AsyncClient):
    b64 = base64.b64encode(path.read_bytes()).decode()
    t = time.monotonic()
    for attempt in range(3):
        r = await client.post("https://openrouter.ai/api/v1/audio/transcriptions",
                              headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
                              json={"model": model, "input_audio": {"data": b64, "format": "wav"}, "language": "en"})
        if r.status_code == 200:
            break
        await asyncio.sleep(2 * (attempt + 1))
    r.raise_for_status()
    j = r.json()
    return j["text"], {"request_s": time.monotonic() - t, "cost_usd": (j.get("usage") or {}).get("cost")}


_pk = None


def parakeet_local(path: Path):
    global _pk
    # M5 + macOS 26 + MLX 0.32: default Metal kernels fail to load; pipeline agent's workaround (docs/dev-log/pipeline.md)
    import os
    os.environ.setdefault("MLX_METAL_GPU_ARCH", "applegpu_g16s")
    from parakeet_mlx import from_pretrained
    if _pk is None:
        _pk = from_pretrained("mlx-community/parakeet-tdt-0.6b-v3")
    t = time.monotonic()
    try:
        res = _pk.transcribe(str(path))
    except RuntimeError:  # MLX Metal kernel failed to load on this machine (seen: steel_gemm_fused_nax); CPU is slower
        import mlx.core as mx
        mx.set_default_device(mx.cpu)
        t = time.monotonic()
        res = _pk.transcribe(str(path))
    return res.text, {"request_s": time.monotonic() - t, "cost_usd": 0.0}


# ---------- runner ----------
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default=",".join(DEFAULT_CLIPS))
    ap.add_argument("--skip", default="")
    ap.add_argument("--only", default="", help="re-run only these engines and merge into existing asr.json")
    ap.add_argument("--repeat", type=int, default=1, help="repeat each cell N times (latency/WER variance)")
    a = ap.parse_args()
    skip = set(a.skip.split(","))
    if a.only:
        skip |= {e for e in ["deepgram_live", "parakeet_mlx"] + [f"or:{m}" for m in OR_MODELS]} - set(a.only.split(","))
    man = {c["id"]: c for c in json.loads((CLIPS / "manifest.json").read_text())["clips"]}
    ids = a.clips.split(",")
    engines = (["deepgram_live"] if "deepgram_live" not in skip else []) + \
              [f"or:{m}" for m in OR_MODELS if f"or:{m}" not in skip] + \
              (["parakeet_mlx"] if "parakeet_mlx" not in skip else [])
    rows = []  # one per (engine, clip, repeat)

    async with httpx.AsyncClient(timeout=180) as client:
        async def run(eng, cid, rep):
            c, p = man[cid], CLIPS / man[cid]["file"]
            try:
                if eng == "deepgram_live":
                    text, m = await deepgram_live(p)
                elif eng.startswith("or:"):
                    text, m = await openrouter(eng[3:], p, client)
                else:
                    text, m = await asyncio.to_thread(parakeet_local, p)
                err = None
            except Exception as e:  # keep going; record the failure honestly
                text, m, err = "", {}, f"{type(e).__name__}: {str(e)[:120]}"
            if eng in PRICES and "cost_usd" not in m:
                m["cost_usd"] = PRICES[eng] * c["duration_s"] / 60
            rows.append({"engine": eng, "clip": cid, "rep": rep, "dur_s": c["duration_s"], "wer": wer(c["reference_text"], text) if not err else None,
                         "hyp": text, "ref": c["reference_text"], "error": err, **m})
            print(f"{eng:36s} {cid:26s} WER={rows[-1]['wer'] if err is None else 'ERR'}", flush=True)

        # Deepgram live clips stream concurrently (each is its own real-time socket, so wall time = longest clip)
        jobs = [(e, cid, r) for r in range(a.repeat) for e in engines for cid in ids]
        live = [j for j in jobs if j[0] == "deepgram_live"]
        sem = asyncio.Semaphore(3)

        async def guarded(j):
            async with sem:
                await run(*j)
        await asyncio.gather(*(run(*j) for j in live), *(guarded(j) for j in jobs if j[0].startswith("or:")))
        for j in jobs:  # local model: sequential, so timings are not contended by the other engines
            if j[0] == "parakeet_mlx":
                await run(*j)

    OUT.mkdir(parents=True, exist_ok=True)
    if a.only and (OUT / "asr.json").exists():
        rows = [r for r in json.loads((OUT / "asr.json").read_text()) if r["engine"] not in a.only.split(",")] + rows
    (OUT / "asr.json").write_text(json.dumps(rows, indent=1))
    (OUT / "asr.md").write_text(render(rows, ids, man))
    print((OUT / "asr.md").read_text())


def render(rows, ids, man):
    engs = list(dict.fromkeys(r["engine"] for r in rows))
    L = ["# ASR comparison (SYNTHETIC macOS-`say` clips; WER after normalisation, lower is better)", "",
         f"Generated {time.strftime('%Y-%m-%d %H:%M')} by backend/scripts/eval_asr.py. Clips are text-to-speech, not real speech: "
         "absolute WERs are optimistic; use the table for relative comparison only.", "",
         "| clip | dur (s) | " + " | ".join(engs) + " |", "|---|---|" + "---|" * len(engs)]
    for cid in ids:
        cells = []
        for e in engs:
            w = [r["wer"] for r in rows if r["engine"] == e and r["clip"] == cid and r["wer"] is not None]
            cells.append(f"{100 * statistics.mean(w):.1f}%" if w else "ERR")
        L.append(f"| {cid} | {man[cid]['duration_s']} | " + " | ".join(cells) + " |")
    L += ["", "## Summary per engine", "",
          "| engine | mean WER (all) | mean WER (clean: turns/names) | mean WER (noisy) | latency | audio min | cost USD (this run) | $/audio-hour |",
          "|---|---|---|---|---|---|---|---|"]
    for e in engs:
        er = [r for r in rows if r["engine"] == e and r["wer"] is not None]
        if not er:
            L.append(f"| {e} | ERR | | | | | | |")
            continue
        m = lambda rs: f"{100 * statistics.mean(r['wer'] for r in rs):.1f}%" if rs else "-"
        clean = [r for r in er if man[r["clip"]]["kind"] in ("turn_taking", "names", "multi_speaker")]
        noisy = [r for r in er if man[r["clip"]]["kind"] == "noisy"]
        if e == "deepgram_live":
            fw = [r["first_word_latency_s"] for r in er if r.get("first_word_latency_s") is not None]
            fl = [r["final_latency_med_s"] for r in er if r.get("final_latency_med_s") is not None]
            iv = [r["interim_interval_med_s"] for r in er if r.get("interim_interval_med_s")]
            lat = (f"live: first caption {statistics.median(fw):.2f}s after first word starts, update every ~{statistics.median(iv):.2f}s, "
                   f"final-result median {statistics.median(fl):.2f}s after speech end") if fw else "-"
        else:
            tot = sum(r["request_s"] for r in er)
            lat = f"batch: {tot / sum(r['dur_s'] for r in er):.3f} s per audio-s (whole clip, not streaming)"
        mins = sum(r["dur_s"] for r in er) / 60
        cost = sum(r.get("cost_usd") or 0 for r in er)
        L.append(f"| {e} | {m(er)} | {m(clean)} | {m(noisy)} | {lat} | {mins:.1f} | {cost:.4f} | {cost / mins * 60:.2f} |")
    L += ["", "## Notes / limits",
          "- `deepgram_live` is streamed in real time; the other cloud engines get the whole clip (batch) so their latency is request time, not live latency.",
          "- WER is computed over the clip's concatenated reference text; diarization is not scored here (see identity eval).",
          "- Overlap clip: references contain both speakers, so any single-stream ASR loses one of them by construction.",
          "- Prices: OpenRouter-reported `usage.cost` per call; Deepgram live list price $0.0048/min (deepgram.com/pricing, read 2026-11-24; diarization add-on not included).", "",
          "## Worst hypotheses (for error analysis)", ""]
    for r in sorted([r for r in rows if r["wer"] is not None], key=lambda r: -r["wer"])[:6]:
        L += [f"- `{r['engine']}` / `{r['clip']}` WER {100 * r['wer']:.0f}%: _{r['hyp'][:160]}_"]
    return "\n".join(L)


if __name__ == "__main__":
    asyncio.run(main())
