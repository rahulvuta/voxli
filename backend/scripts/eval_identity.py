"""Identity evaluation. Writes eval/out/identity.md.

1. Calibration: same- vs different-speaker cosine similarity (ECAPA vs WeSpeaker), thresholds.
2. Conversations: Deepgram's own diarization labels vs Voxli identity on the SAME turns.

All audio is SYNTHETIC (macOS `say`); see make_identity_clips.py. Run: uv run python scripts/eval_identity.py
"""
import itertools
from collections import deque
import json
import random
import time
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf
from scipy.optimize import linear_sum_assignment

from voxli import config
from voxli.identity import engine as E
from voxli.identity.embed import Ecapa

ROOT = config.ROOT
CLIPS = ROOT / "eval" / "clips" / "identity"
OUT = ROOT / "eval" / "out"
TWINS = [("Eddy", "Reed"), ("Flo", "Shelley")]            # `say` voices that are nearly the same voice
MAIN = ["Samantha", "Daniel", "Karen", "Rishi", "Moira", "Tessa", "Fred", "Ralph", "Kathy", "Junior",
        "Grandpa", "Rocko", "Albert", "Sandy"]
CONVS = {  # name -> voices
    "easy4": ["Samantha", "Daniel", "Karen", "Rishi"],
    "similar4": ["Junior", "Kathy", "Fred", "Ralph"],       # two similar-sounding pairs
    "twins3": ["Flo", "Shelley", "Samantha"],               # a near-identical pair: expect "?" or a merge
}
md: list[str] = []


def p(s: str = "") -> None:
    print(s)
    md.append(s)


def table(head, rows):
    p("| " + " | ".join(head) + " |")
    p("|" + "---|" * len(head))
    for r in rows:
        p("| " + " | ".join(str(c) for c in r) + " |")
    p()


def load(v: str, i: int) -> np.ndarray:
    return sf.read(CLIPS / f"{v}_{i}.wav", dtype="float32")[0]


# ---------------------------------------------------------------------------- 1. calibration
def eer(same, diff) -> float:
    th = np.linspace(-1, 1, 2001)
    far = np.array([(diff >= t).mean() for t in th])
    frr = np.array([(same < t).mean() for t in th])
    return float(far[np.argmin(abs(far - frr))])


def models():
    from pyannote.audio import Model
    import torch
    wes = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM", cache_dir=str(ROOT / "backend/models_cache/hf")).eval()

    def wespeaker(x):
        with torch.no_grad():
            return wes(torch.from_numpy(x)[None, None])[0].numpy()
    return {"ECAPA-TDNN (speechbrain)": Ecapa(), "WeSpeaker ResNet34 (pyannote)": wespeaker}


def unit(x):
    return x / np.linalg.norm(x)


def calibrate():
    p("## 1. Embedding choice and thresholds (synthetic `say` voices)\n")
    clips = {(v, i): load(v, i) for v in MAIN + [t for pr in TWINS for t in pr] for i in range(8)}
    dur = {k: len(x) / 16000 for k, x in clips.items()}
    ms = models()
    ecapa = ms["ECAPA-TDNN (speechbrain)"]
    rows, embs = [], {}
    for name, fn in ms.items():
        emb = {k: unit(fn(x)) for k, x in clips.items()}
        embs[name] = emb
        keys = [k for k in emb if k[0] in MAIN and dur[k] >= 0.8]
        same, diff, hard = [], [], []
        for a, b in itertools.combinations(keys, 2):
            s = float(emb[a] @ emb[b])
            (same if a[0] == b[0] else diff).append(s)
        t = time.perf_counter()
        for _ in range(5):
            fn(clips[("Daniel", 3)])
        ms_ = (time.perf_counter() - t) / 5 * 1000
        # hardest non-twin pair by mean cross similarity
        cent = {v: unit(np.mean([emb[(v, i)] for i in range(2, 8)], 0)) for v in MAIN}
        hp = sorted(((float(cent[a] @ cent[b]), a, b) for a, b in itertools.combinations(MAIN, 2)), reverse=True)[:3]
        rows.append([name, f"{np.mean(same):.2f}", f"{np.mean(diff):.2f}", f"{np.max(diff):.2f}",
                     f"{eer(np.array(same), np.array(diff)) * 100:.1f}%", ", ".join(f"{a}/{b} {s:.2f}" for s, a, b in hp),
                     f"{ms_:.0f}"])
    table(["model", "same mean", "diff mean", "diff max", "EER (segment pairs >=0.8 s)", "most similar distinct pairs (centroid cos)", "CPU ms / 4 s clip"], rows)

    emb = embs["ECAPA-TDNN (speechbrain)"]
    p("Same-speaker vs different-speaker cosine, ECAPA. Each segment is scored against the centroid of the other "
      "segments of each speaker (leave-one-out), which is exactly what `assign` does. Rows crop the segment to the length shown.\n")
    rows = []
    for L in (None, 1.2, 0.8, 0.5):
        same, diff = [], []
        for (v, i) in [k for k in clips if k[0] in MAIN and dur[k] >= 1.5]:
            x = clips[(v, i)] if L is None else clips[(v, i)][: int(L * 16000)]
            e = emb[(v, i)] if L is None else unit(ecapa(x))
            for w in MAIN:
                c = unit(sum(emb[(w, j)] for j in range(8) if j != i and not (w == v and j == i) and dur[(w, j)] >= 1.5))
                (same if w == v else diff).append(float(e @ c))
        same, diff = np.array(same), np.array(diff)
        rows.append(["full" if L is None else f"{L} s", len(same), f"{same.mean():.2f}", f"{np.percentile(same, 5):.2f}", f"{same.min():.2f}",
                     f"{diff.mean():.2f}", f"{np.percentile(diff, 95):.2f}", f"{np.percentile(diff, 99):.2f}", f"{diff.max():.2f}",
                     f"{(same >= E.T_HI).mean() * 100:.0f}%", f"{(diff >= E.T_HI).mean() * 100:.1f}%", f"{(diff < E.T_LO).mean() * 100:.0f}%"])
    table(["segment", "n same", "same mean", "same p5", "same min", "diff mean", "diff p95", "diff p99", "diff max",
           f"same >= T_HI", "diff >= T_HI (wrong accept)", "diff < T_LO"], rows)
    p("Near-identical synthetic voices (centroid cosine): " + ", ".join(
        f"{a}/{b} {float(unit(np.mean([emb[(a, i)] for i in range(2, 8)], 0)) @ unit(np.mean([emb[(b, i)] for i in range(2, 8)], 0))):.2f}"
        for a, b in TWINS) + ". These are the same `say` voice with different pitch/rate, so they are not a fair test of separability; reported as a limit.\n")

    # split-half centroid similarity -> T_MERGE
    sh, dd = [], []
    for v in MAIN:
        a, b = unit(sum(emb[(v, i)] for i in (1, 3, 5, 7))), unit(sum(emb[(v, i)] for i in (2, 4, 6, 0)))
        sh.append(float(a @ b))
    for a, b in itertools.combinations(MAIN, 2):
        dd.append(float(unit(sum(emb[(a, i)] for i in range(8))) @ unit(sum(emb[(b, i)] for i in range(8)))))
    p(f"Centroid-vs-centroid (merge test): same speaker split in halves min {min(sh):.2f} / mean {np.mean(sh):.2f}; "
      f"different speakers max {max(dd):.2f} / p95 {np.percentile(dd, 95):.2f}.\n")
    p(f"**Chosen**: T_HI = {E.T_HI}, T_LO = {E.T_LO}, T_MERGE = {E.T_MERGE} (merge only after {E.MERGE_MIN_N} confident segments each), "
      f"weak-evidence cut-off {E.SHORT} s.\n")
    return ecapa, emb


# ---------------------------------------------------------------------------- 2. conversations
def build_conv(name: str, voices: list[str]):
    rng = random.Random(name)
    turns = [(v, i) for v in voices for i in range(8)]
    rng.shuffle(turns)
    audio, truth, t = [], [], 0.0
    for v, i in turns:
        x = load(v, i)
        gap = np.zeros(int(rng.uniform(0.3, 0.8) * 16000), np.float32)
        audio += [x, gap]
        truth.append({"speaker": v, "clip": f"{v}_{i}", "start": t, "end": t + len(x) / 16000})
        t += (len(x) + len(gap)) / 16000
    wav = np.concatenate(audio)
    sf.write(CLIPS / f"conv_{name}.wav", wav, 16000)
    (CLIPS / f"conv_{name}.json").write_text(json.dumps(truth, indent=1))
    return CLIPS / f"conv_{name}.wav", truth


def shared_clips():
    """Clips made by the eval agent (eval/clips/manifest.json): turn-taking, cafe with an interruption, noisy variants."""
    mf = ROOT / "eval" / "clips" / "manifest.json"
    if not mf.exists():
        return
    for c in json.loads(mf.read_text())["clips"]:
        if c["kind"] in ("turn_taking", "multi_speaker", "noisy") and (mf.parent / c["file"]).exists():
            yield c["id"], mf.parent / c["file"], [{"speaker": x["speaker"], "start": x["start"], "end": x["end"]} for x in c["segments"]]


def deepgram(name: str, path: Path) -> list[dict]:
    cache = OUT / f"identity_deepgram_{name}.json"
    if not cache.exists():
        r = httpx.post("https://api.deepgram.com/v1/listen?model=nova-3&diarize=true&smart_format=true",
                       headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}", "Content-Type": "audio/wav"},
                       content=path.read_bytes(), timeout=120)
        r.raise_for_status()
        cache.write_text(json.dumps(r.json()["results"]["channels"][0]["alternatives"][0]["words"]))
    return json.loads(cache.read_text())


def dg_label(words, a, b):
    sp = [w["speaker"] for w in words if a <= (w["start"] + w["end"]) / 2 <= b]
    return str(max(set(sp), key=sp.count)) if sp else None


def score(truth, labels, uncertain=None):
    """accuracy under the best label->speaker mapping, plus label flips and confident-wrong turns."""
    uncertain = uncertain or [False] * len(truth)
    ts, ls = sorted({r["speaker"] for r in truth}), sorted({l for l in labels if l is not None})
    m = np.zeros((len(ls), len(ts)))
    for r, l, u in zip(truth, labels, uncertain):
        if l is not None and not u:
            m[ls.index(l), ts.index(r["speaker"])] += 1
    ri, ci = linear_sum_assignment(-m) if len(ls) else ([], [])
    mapping = {ls[i]: ts[j] for i, j in zip(ri, ci)}
    ok = [mapping.get(l) == r["speaker"] for r, l in zip(truth, labels)]
    certain = [not u for u in uncertain]
    flips = 0
    for s in ts:
        seq = [(l, u) for r, l, u in zip(truth, labels, uncertain) if r["speaker"] == s and not u]
        flips += sum(a[0] != b[0] for a, b in zip(seq, seq[1:]))
    n = len(truth)
    return {"turns": n, "acc_all": sum(o and c for o, c in zip(ok, certain)) / n,
            "shown with a label": sum(certain) / n,
            "acc_shown": sum(o for o, c in zip(ok, certain) if c) / max(1, sum(certain)),
            "confident-wrong turns": sum((not o) and c for o, c in zip(ok, certain)),
            "label flips": flips, "labels used": len({l for l, c in zip(labels, certain) if c and l != "UNKNOWN"}), "true speakers": len(ts)}


def conversations(embed) -> None:
    p("## 2. Deepgram diarization vs Voxli identity, same turns\n")
    p("Conversations are built from `say` clips (turn boundaries known): our own three plus the eval agent's `turns_2spk`, `cafe_4spk` (with an interruption) and noisy variants. Deepgram: prerecorded API, nova-3, diarize=true on the whole file "
      "(its best case: it sees all the audio at once; live streaming diarization has less context). Its label for a turn is the majority speaker "
      "of the words inside it. Voxli: `IdentityEngine.assign` on the same audio slice, in time order, **with no hint** (pure voiceprint) and "
      "**with Deepgram's label as hint**. Accuracy uses the best label-to-speaker mapping (Hungarian). A turn Voxli marks `?` counts as "
      "not-correct in the first accuracy column but is not a confident error. 'Label flips' = times one true speaker's consecutive "
      "labelled turns got different labels.\n")
    embed(np.full(16000, 0.01, np.float32))  # warm-up so one-off torch init is not counted as latency
    rows, lat = [], []
    scenarios = [(n, *build_conv(n, v)) for n, v in CONVS.items()] + list(shared_clips())
    for name, path, truth in scenarios:
        wav = sf.read(path, dtype="float32")[0]
        words = deepgram(name, path)
        res = {"Deepgram diarization": score(truth, [dg_label(words, r["start"], r["end"]) for r in truth])}
        for tag, use_hint in (("Voxli (no hint)", False), ("Voxli (+ Deepgram hint)", True)):
            eng = E.IdentityEngine(embed=embed, memory_path=ROOT / "eval/out/.unused")
            labels, unc = [], []
            for r in truth:
                h = dg_label(words, r["start"], r["end"]) if use_hint else None
                t = time.perf_counter()
                a = eng.assign(wav[int(r["start"] * 16000): int(r["end"] * 16000)], r["start"], r["end"], hint=h)
                lat.append((time.perf_counter() - t) * 1000)
                labels.append(a.speaker_id)
                unc.append(a.uncertain)
            merged = eng.pending_merges()
            res[tag] = score(truth, labels, unc) | {"auto-merges": len(merged)}
        for k, v in res.items():
            rows.append([name, k, v["turns"], f"{v['acc_all'] * 100:.0f}%",
                         f"{v['shown with a label'] * 100:.0f}%", f"{v['acc_shown'] * 100:.0f}%", v["confident-wrong turns"],
                         v["label flips"], f"{v['labels used']} / {v['true speakers']}"])
    table(["conversation", "method", "turns", "accuracy (all turns)", "turns with a label", "accuracy of shown labels", "confident-wrong", "label flips", "labels used / true speakers"], rows)
    lat = np.array(lat)
    p(f"Latency of `assign` (embedding + matching, CPU, M-series Mac), {len(lat)} segments of 0.6-5.5 s: "
      f"median {np.median(lat):.0f} ms, p95 {np.percentile(lat, 95):.0f} ms, max {lat.max():.0f} ms.\n")


def sweep(clips_emb) -> None:
    """Threshold choice on 45 random 4- and 6-speaker conversations (every clip once, shuffled)."""
    p("### Threshold sweep (45 random conversations of 4-6 of the 14 voices, every clip used once)\n")
    rng = random.Random(0)
    convs = []
    for n, k in ((30, 4), (15, 6)):
        for _ in range(n):
            t = [(v, i) for v in rng.sample(MAIN, k) for i in range(8)]
            rng.shuffle(t)
            convs.append(t)
    saved = (E.T_HI, E.T_LO, E.T_MERGE)
    rows = []
    for thi, tlo, pool in [(0.55, 0.4, True), (0.60, 0.4, True), (0.65, 0.4, True), (0.70, 0.4, True), (0.75, 0.4, True),
                           (0.65, 0.45, True), (0.65, 0.4, False)]:
        E.T_HI, E.T_LO = thi, tlo
        shown = wrong = total = cnt_err = 0
        for t in convs:
            cur = [None]
            eng = E.IdentityEngine(embed=lambda a: clips_emb[cur[0]], memory_path=OUT / ".unused")
            if not pool:
                eng._pool = deque(maxlen=0)
            labels, unc = [], []
            for k in t:
                cur[0] = k
                a = eng.assign(load(*k), 0, 0)
                labels.append(a.speaker_id)
                unc.append(a.uncertain)
            r = score([{"speaker": k[0]} for k in t], labels, unc)
            total += r["turns"]
            shown += round(r["shown with a label"] * r["turns"])
            wrong += r["confident-wrong turns"]
            cnt_err += abs(r["labels used"] - r["true speakers"])
        rows.append([thi, tlo, "on" if pool else "off", f"{shown / total * 100:.0f}%", f"{wrong / shown * 100:.1f}%", f"{cnt_err / len(convs):.2f}"])
    E.T_HI, E.T_LO, E.T_MERGE = saved
    table(["T_HI", "T_LO", "new-speaker pool", "turns with a label", "confident-wrong (of labelled)", "speaker-count error / conversation"], rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    p("# Voxli identity evaluation\n")
    p("All audio is **synthetic** (macOS `say` voices, not human speech). Real voices vary more across a session (emotion, distance, noise), "
      "so absolute numbers are optimistic; use them for relative comparison and sanity-checking thresholds.\n")
    embed, emb = calibrate()
    sweep(emb)
    conversations(embed)
    (OUT / "identity.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
