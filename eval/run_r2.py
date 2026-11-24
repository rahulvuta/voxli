"""R2/R3 end-to-end runs: stream SYNTHETIC clips through the real Session via backend/scripts/replay.py
(real time) and score the events against eval/clips/manifest.json ground truth.

    cd backend && uv run python ../eval/run_r2.py            # all cases, writes eval/out/r2_r3.md + .json
    cd backend && uv run python ../eval/run_r2.py --only turns_2spk_run1

Per case: WER of final utterances vs reference, speaker accuracy (best label->speaker mapping),
label flips, '?' count, confident-wrong count, name events, overlap groups, status sequence, latency.
Speaker accuracy is per final utterance, matched to the ground-truth segment with the most time overlap.
Limits: synthetic TTS speech; one run per case unless a repeat is listed; utterances (ASR segments) do not
always align one-to-one with scripted turns.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import jiwer
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
from eval_asr import normalize  # noqa: E402

CLIPS = ROOT / "eval" / "clips"
OUT = ROOT / "eval" / "out"
# id, clip, group, extra replay args, env overrides, what we expect
CASES = [
    ("turns_2spk_run1", "turns_2spk", "R2 ordinary 1", [], {}, "8 turns captioned, WER<=5%, 2 labels, 0 flips, 0 confident-wrong"),
    ("selfintro_sarah", "selfintro_sarah", "R2 ordinary 2", [], {}, "name 'Sarah' attached to the speaker who said 'I'm Sarah' (auto-applied)"),
    ("turns_2spk_run2", "turns_2spk", "R2 repeat", [], {}, "same as run1 (repeatability: WER and labels within noise)"),
    ("noisy_cafe_babble_snr5", "noisy_cafe_babble_snr5", "R2 demanding", [], {}, "4 speakers, babble at 5 dB SNR + an interruption: WER<=15%, no confident-wrong labels ('?' allowed)"),
    ("overlap_2spk_2s", "overlap_2spk_2s", "R2 demanding (overlap)", [], {}, "both speakers' sentences shown, same overlap_group"),
    ("fail_bad_deepgram_key", "turns_2spk", "R3 failure 1a: ASR service unavailable", [], {"DEEPGRAM_API_KEY": "invalid-key-for-test"}, "status goes local, captions still appear (WER near normal)"),
    ("fail_deepgram_dropped_mid_stream", "turns_2spk", "R3 failure 1b: connection lost mid-stream", ["--kill-dg-at", "8"], {}, "status reconnecting -> local, no gap in captions"),
    ("fail_mono_mic_dupmono", "stereo_dupmono", "R3 failure 2: phone gives duplicated mono", [], {}, "no direction invented (direction_deg null), no crash"),
]


def score(clip: dict, events: list[dict]) -> dict:
    summ = next((e for e in reversed(events) if e["type"] == "replay_summary"), {})
    by_id: dict[str, dict] = {}
    for e in events:
        if e["type"] == "utterance" and e["utterance"]["text"].strip():
            by_id[e["utterance"]["id"]] = e["utterance"]  # last version of each id wins
    finals = sorted([u for u in by_id.values() if u["is_final"]], key=lambda u: u["start"])
    live = [u for u in finals if u.get("source") != "separated"]
    hyp = " ".join(u["text"] for u in live)  # WER on the live stream only: separated utterances re-state words
    ref = clip["reference_text"]
    r, h = normalize(ref), normalize(hyp)
    wer = jiwer.wer(r, h) if h else 1.0
    # word recall of the reference over ALL final utterances (live + separated): did every speaker's words show up?
    from collections import Counter as C
    hits = lambda txt: sum((C(r.split()) & C(normalize(txt).split())).values()) / max(1, len(r.split()))
    recall_all = hits(" ".join(u["text"] for u in finals))
    recall_live = hits(hyp)
    segs = clip["segments"]

    def truth(u):
        best = max(segs, key=lambda s: min(s["end"], u["end"]) - max(s["start"], u["start"]))
        return best["speaker"] if min(best["end"], u["end"]) - max(best["start"], u["start"]) > 0 else None
    pairs = [(truth(u), u) for u in finals if u.get("source") != "separated"]
    pairs = [(t, u) for t, u in pairs if t]
    labels = sorted({u["speaker_id"] for _, u in pairs})
    trues = sorted({t for t, _ in pairs})
    acc = confwrong = flips = None
    if pairs:
        cnt = Counter((t, u["speaker_id"]) for t, u in pairs if not u["speaker_uncertain"])
        import numpy as np
        M = np.array([[cnt[(t, l)] for l in labels] for t in trues])
        ri, ci = linear_sum_assignment(-M)
        mp = {trues[i]: labels[j] for i, j in zip(ri, ci)}
        right = sum(1 for t, u in pairs if not u["speaker_uncertain"] and mp.get(t) == u["speaker_id"])
        acc = right / len(pairs)
        confwrong = sum(1 for t, u in pairs if not u["speaker_uncertain"] and mp.get(t) != u["speaker_id"])
        flips = 0
        for t in trues:
            seq = [u["speaker_id"] for tt, u in pairs if tt == t and not u["speaker_uncertain"]]
            flips += sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    names = [(e["speaker"]["id"], e["speaker"]["name"], e["speaker"]["name_source"]) for e in events
             if e["type"] == "speaker" and e["speaker"].get("name")]
    return {
        "finals": len(finals), "wer": wer, "recall_live": recall_live, "recall_all": recall_all,
        "finals_raw": [{k: u.get(k) for k in ("id", "text", "start", "end", "speaker_id", "speaker_uncertain", "source", "overlap_group")} for u in finals], "hyp": hyp[:300], "speaker_acc": acc, "confident_wrong": confwrong,
        "label_flips": flips, "uncertain": sum(u["speaker_uncertain"] for _, u in pairs), "n_scored": len(pairs),
        "labels_used": len(labels), "true_speakers": len(trues),
        "names": sorted(set(names)), "suggestions": [(e["name"], e["kind"], e["auto_applied"]) for e in events if e["type"] == "name_suggestion"],
        "overlap_groups": len({u["overlap_group"] for u in by_id.values() if u["overlap_group"]}),
        "separated_utts": sum(1 for u in finals if u.get("source") == "separated"),
        "directions": sorted({round(u["direction_deg"]) for u in finals if u.get("direction_deg") is not None}),
        "status": summ.get("status"), "errors": summ.get("errors"),
        "first_word_ms_after_word_ends": summ.get("first_word_latency_ms_after_speech_onset"),
        "final_lag_ms_median": summ.get("final_lag_ms_median"),
    }


async def run_case(case, man, sem):
    cid, clip, group, args, env, expect = case
    async with sem:
        t = time.monotonic()
        p = await asyncio.create_subprocess_exec(
            "uv", "run", "python", "scripts/replay.py", str(CLIPS / man[clip]["file"]), "--realtime", "--tail", "8", *args,
            cwd=ROOT / "backend", env={**os.environ, **env}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:  # a hung replay must not hang the whole eval: audio length + 150 s of slack
            out, err = await asyncio.wait_for(p.communicate(), man[clip]["duration_s"] + 150)
        except asyncio.TimeoutError:
            p.kill()
            out, err = await p.communicate()
            err = b"TIMEOUT (replay exceeded audio length + 150 s)" + err[-200:]
    events = []
    for line in out.decode().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    res = {"id": cid, "clip": clip, "group": group, "expect": expect, "wall_s": round(time.monotonic() - t, 1),
           "returncode": p.returncode, **score(man[clip], events)}
    if p.returncode:
        res["stderr_tail"] = err.decode()[-300:]
    print(f"{cid:34s} rc={p.returncode} WER={res['wer']:.3f} acc={res['speaker_acc']}", flush=True)
    return res


def fmt(x, pct=True):
    return "-" if x is None else (f"{100 * x:.0f}%" if pct else str(x))


def render(rs):
    L = ["# R2 / R3 end-to-end results (SYNTHETIC clips, real-time replay through the real Session)", "",
         f"Generated {time.strftime('%Y-%m-%d %H:%M')} by eval/run_r2.py. Clips are macOS `say` TTS (see eval/clips/manifest.json). "
         "Speaker accuracy = share of final utterances whose label matches the ground-truth speaker under the best label mapping; "
         "'?' utterances are not counted correct but are not confident errors.", "",
         "| case | group | expected | WER (live stream) | ref-word recall live -> live+separated | speaker acc | '?' | confident-wrong | label flips | labels/true | first caption after speech onset | final lag (median) | status sequence | other |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rs:
        other = []
        if r["names"]:
            other.append("names " + ", ".join(f"{i}={n}({s})" for i, n, s in r["names"]))
        if r["suggestions"]:
            other.append("suggestions " + ", ".join(f"{n}/{k}/auto={a}" for n, k, a in r["suggestions"]))
        if r["overlap_groups"]:
            other.append(f"{r['overlap_groups']} overlap group(s), {r['separated_utts']} separated utts")
        other.append(f"dir={r['directions']}" if r["directions"] else "dir=none")
        if r["errors"]:
            other.append("errors: " + "; ".join(r["errors"])[:80])
        if r["returncode"]:
            other.append(f"REPLAY FAILED rc={r['returncode']}")
        L.append(f"| {r['id']} | {r['group']} | {r['expect']} | {100 * r['wer']:.1f}% | {100 * r['recall_live']:.0f}% -> {100 * r['recall_all']:.0f}% | {fmt(r['speaker_acc'])} ({r['n_scored']} utts) | {r['uncertain']} | "
                 f"{r['confident_wrong']} | {r['label_flips']} | {r['labels_used']}/{r['true_speakers']} | "
                 f"{r['first_word_ms_after_word_ends']} ms | {r['final_lag_ms_median']} ms | {' -> '.join(r['status'] or [])} | {'; '.join(other)} |")
    L += ["", "## Hypotheses (first 300 chars)", ""] + [f"- `{r['id']}`: _{r['hyp']}_" for r in rs]
    return "\n".join(L)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--parallel", type=int, default=3)
    a = ap.parse_args()
    man = {c["id"]: c for c in json.loads((CLIPS / "manifest.json").read_text())["clips"]}
    cases = [c for c in CASES if not a.only or c[0] in a.only.split(",")]
    sem = asyncio.Semaphore(a.parallel)
    rs = list(await asyncio.gather(*(run_case(c, man, sem) for c in cases)))
    if a.only and (OUT / "r2_r3.json").exists():  # merge: keep earlier rows for cases not re-run
        old = {r["id"]: r for r in json.loads((OUT / "r2_r3.json").read_text())}
        old.update({r["id"]: r for r in rs})
        rs = [old[c[0]] for c in CASES if c[0] in old]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "r2_r3.json").write_text(json.dumps(rs, indent=1, default=str))
    (OUT / "r2_r3.md").write_text(render(rs))
    print((OUT / "r2_r3.md").read_text())


if __name__ == "__main__":
    asyncio.run(main())
