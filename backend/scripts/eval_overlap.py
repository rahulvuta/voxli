"""Overlap separation eval -> eval/out/overlap.md.

Synthetic two-voice mixtures from macOS `say` (A starts at 0, B starts so they overlap for 1/2/3 s, equal level).
Per mixture and method (none / tiger / mossformer2) we transcribe each output stream with OpenRouter nova-3 and report
  cpWER  : concatenated-permutation WER of the 2 reference sentences vs the method's streams (no separation = 1 stream)
  SI-SDRi: mean over both talkers of SI-SDR(est) - SI-SDR(mixture), best permutation
  RTF    : wall seconds per second of audio on this machine (warm model)
Run: cd backend && uv run python scripts/eval_overlap.py [--rebuild] [--models mossformer2,tiger]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import itertools
import json
import platform
import re
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import jiwer
import numpy as np
import soundfile as sf
import torch

from voxli import config
from voxli.overlap.processor import run_model, si_sdr

ROOT = config.ROOT
CLIPS = ROOT / "eval" / "clips" / "overlap"
OUT = ROOT / "eval" / "out"
SR = 16000
SENT = [
    "The weather forecast says it will rain heavily tomorrow morning.",
    "Please remember to bring the signed documents to the meeting.",
    "My sister just moved into a small apartment downtown.",
    "We should order pizza and watch the football game tonight.",
    "The new library opens next Monday near the train station.",
    "I think the museum closes at five on Sundays.",
    "She bought fresh vegetables from the market this afternoon.",
    "Our flight to Chicago leaves early on Friday morning.",
]
# (voice A, sentence A, voice B, sentence B); every pair is run at overlaps 1, 2, 3 s. Kathy+Samantha = same-gender pair.
PAIRS = [("Samantha", 0, "Daniel", 1), ("Karen", 2, "Fred", 3), ("Moira", 4, "Ralph", 5), ("Kathy", 6, "Samantha", 7)]
OVERLAPS = [1.0, 2.0, 3.0]


def tts(voice: str, text: str) -> np.ndarray:
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["say", "-v", voice, "-o", f"{d}/a.aiff", text], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", f"{d}/a.aiff", "-ar", str(SR), "-ac", "1", f"{d}/a.wav"], check=True)
        x, _ = sf.read(f"{d}/a.wav", dtype="float32")
    return x / (np.sqrt((x ** 2).mean()) + 1e-9) * 0.05  # equal RMS


def build() -> list[dict]:
    CLIPS.mkdir(parents=True, exist_ok=True)
    man = []
    for va, ia, vb, ib in PAIRS:
        a, b = tts(va, SENT[ia]), tts(vb, SENT[ib])
        for ov in OVERLAPS:
            off = max(0, len(a) - int(ov * SR))
            n = max(len(a), off + len(b))
            sa, sb = np.zeros(n, np.float32), np.zeros(n, np.float32)
            sa[: len(a)], sb[off: off + len(b)] = a, b
            name = f"{va}-{vb}_ov{ov:.0f}s"
            sf.write(CLIPS / f"{name}.wav", sa + sb, SR)
            sf.write(CLIPS / f"{name}_A.wav", sa, SR)
            sf.write(CLIPS / f"{name}_B.wav", sb, SR)
            man.append(dict(name=name, synthetic=True, voices=[va, vb], refs=[SENT[ia], SENT[ib]], overlap_s=ov,
                            duration_s=n / SR, a_span=[0, len(a) / SR], b_span=[off / SR, (off + len(b)) / SR]))
    (CLIPS / "manifest.json").write_text(json.dumps(man, indent=1))
    return man


def transcribe(x: np.ndarray, cache: dict) -> str:
    buf = io.BytesIO()
    sf.write(buf, x.astype(np.float32), SR, format="WAV", subtype="PCM_16")
    key = hashlib.sha1(buf.getvalue()).hexdigest()
    if key not in cache:
        for attempt in range(3):
            r = httpx.post("https://openrouter.ai/api/v1/audio/transcriptions", timeout=60,
                           json={"model": "deepgram/nova-3", "input_audio": {"data": base64.b64encode(buf.getvalue()).decode(), "format": "wav"}, "language": "en"},
                           headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"})
            if r.status_code == 200:
                cache[key] = r.json().get("text", "")
                break
            time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"transcription failed: HTTP {r.status_code}")
    return cache[key]


def norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9' ]", " ", s.lower()).split())


def cpwer(refs: list[str], hyps: list[str]) -> float:
    """min over assignments of the hypothesis streams to the references; ref = refs joined, hyp = streams joined in that order."""
    hyps = (hyps + [""] * 2)[:2]
    best = 9.0
    for perm in itertools.permutations(range(2)):
        r = " ".join(norm(refs[i]) for i in range(2))
        h = " ".join(norm(hyps[p]) for p in perm)
        best = min(best, jiwer.wer(r, h))
    return best


def sisdri(est: np.ndarray, refs: list[np.ndarray], mix: np.ndarray) -> float:
    base = [si_sdr(mix, r) for r in refs]
    return max(np.mean([si_sdr(est[p[i]], refs[i]) - base[i] for i in range(2)]) for p in itertools.permutations(range(2)))


def degrade(refs: list[np.ndarray], seed: int) -> tuple[np.ndarray, list[np.ndarray]]:
    """Per-talker synthetic room impulse response (RT60 ~0.4 s) + white noise at 10 dB SNR."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(0.5 * SR)) / SR
    out = []
    for r in refs:
        rir = rng.standard_normal(len(t)) * np.exp(-6.9 * t / 0.4)  # -60 dB at 0.4 s
        rir[0] = 3 * np.abs(rir).max()  # direct path
        out.append(np.convolve(r, rir)[: len(r)].astype(np.float32))
    mix = out[0] + out[1]
    return mix + rng.standard_normal(len(mix)).astype(np.float32) * np.sqrt((mix ** 2).mean() / 10), out


def table(title: str, man: list[dict], models: list[str], cache: dict, cache_f: Path, rough: bool) -> str:
    res: dict[str, list[dict]] = {m: [] for m in ["none", *models]}
    runtime = {m: [0.0, 0.0] for m in models}  # [seconds, audio seconds]
    for i, it in enumerate(man):
        mix, _ = sf.read(CLIPS / f"{it['name']}.wav", dtype="float32")
        refs = [sf.read(CLIPS / f"{it['name']}_{k}.wav", dtype="float32")[0] for k in "AB"]
        if rough:
            mix, refs = degrade(refs, i)
        res["none"].append(dict(ov=it["overlap_s"], wer=cpwer(it["refs"], [transcribe(mix, cache)]), sdri=0.0))
        for m in models:
            t = time.perf_counter()
            est = run_model(m, mix)
            runtime[m][0] += time.perf_counter() - t
            runtime[m][1] += len(mix) / SR
            hyps = [transcribe(e / (np.abs(e).max() + 1e-9) * 0.5, cache) for e in est]
            res[m].append(dict(ov=it["overlap_s"], wer=cpwer(it["refs"], hyps), sdri=sisdri(est, refs, mix)))
            print(title[:6], it["name"], m, f"WER {res[m][-1]['wer']:.2f} SI-SDRi {res[m][-1]['sdri']:.1f}", flush=True)
        cache_f.write_text(json.dumps(cache))
    rows = []
    for m, rs in res.items():
        cell = lambda f: f"{np.mean([r['wer'] for r in rs if f(r)]) * 100:.0f}%"
        rtf = f"{runtime[m][0] / runtime[m][1]:.2f}" if m in runtime else "0"
        rows.append(f"| {'no separation' if m == 'none' else m} | {cell(lambda r: r['ov'] == 1)} | {cell(lambda r: r['ov'] == 2)} | {cell(lambda r: r['ov'] == 3)} | "
                    f"**{cell(lambda r: True)}** | {np.mean([r['sdri'] for r in rs]):.1f} dB | {rtf} |")
    return (f"## {title}\n\n| method | cpWER 1 s overlap | cpWER 2 s | cpWER 3 s | cpWER all | SI-SDRi | runtime (s per audio s) |\n|---|---|---|---|---|---|---|\n" + "\n".join(rows))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--models", default="mossformer2,tiger")
    args = ap.parse_args()
    man = json.loads((CLIPS / "manifest.json").read_text()) if (CLIPS / "manifest.json").exists() and not args.rebuild else build()
    models = args.models.split(",")
    OUT.mkdir(parents=True, exist_ok=True)
    cache_f = OUT / "overlap_asr_cache.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    for m in models:  # warm-up (weights load + first-call kernels) is excluded from timing
        run_model(m, 1e-3 * np.random.default_rng(0).standard_normal(3 * SR).astype(np.float32))
    tables = [table("Clean mixtures", man, models, cache, cache_f, False),
              table("Reverb (RT60 ~0.4 s, own RIR per talker) + white noise at 10 dB SNR", man, models, cache, cache_f, True)]
    md = f"""# Overlap separation eval (synthetic, `say` voices)

{len(man)} two-talker mixtures ({len(PAIRS)} voice pairs x overlaps {OVERLAPS} s, equal level). Each reference sentence is 3-4 s long, so the
overlapped region is 25-100% of the clip. cpWER = concatenated-permutation WER of both sentences vs the method's streams, transcribed with OpenRouter deepgram/nova-3.
Machine: {platform.platform()} ({platform.machine()}); models run on MPS (PyTorch {torch.__version__}); the Mac was shared with other jobs, so runtimes are upper bounds.
Both separators get the whole mixture (3-6 s), the size the pipeline sends (spans are capped at 6 s).

""" + "\n\n".join(tables) + "\n\nSynthetic TTS voices: real rooms, real microphones and 3+ talkers will be worse; see docs/dev-log/overlap.md.\n"
    (OUT / "overlap.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
