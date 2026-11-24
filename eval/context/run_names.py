"""Eval of the context engine: names (precision/recall/false-name), reply/interrupt annotation, verbatim guard.

Run: cd backend && uv run python ../eval/context/run_names.py [--models a b] [--limit N]
Writes eval/out/context.md. Calls the real ContextEngine (same prompts/validation as production) on OpenRouter.
"""
import argparse
import asyncio
import copy
import json
import statistics as st
from pathlib import Path

from voxli.context.engine import ContextEngine
from voxli.context.guard import verbatim_guard
from voxli.types import Utterance

HERE = Path(__file__).parent
OUT = HERE.parent / "out" / "context.md"
MODELS = ["anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5"]
PROD_TIMEOUT = 4.0


def load(name):
    return [json.loads(l) for l in (HERE / name).read_text().splitlines() if l.strip()]


def utt(d):
    return Utterance(id=d["id"], speaker_id=d["speaker"], speaker_confidence=1, speaker_uncertain=False,
                     text=d["text"], words=[], start=d["start"], end=d["end"], is_final=True)


async def run_names(model, items, sem):
    res, events, snippets = [], [], []  # events/snippets: one list per item

    async def one(it):
        async with sem:
            e = ContextEngine(model=model, timeout=30)
            hist, evs = [], []
            for d in it["utts"]:
                u = utt(d)
                evs += await e.on_final(u, list(hist))
                hist.append(u)
            await e.aclose()
            return it, hist, evs, e.calls

    calls = []
    for it, hist, evs, c in await asyncio.gather(*(one(i) for i in items)):
        pred = {(x["speaker_id"], x["name"].lower(), x["kind"]) for x in evs if x["type"] == "name_suggestion"}
        auto = {(x["speaker_id"], x["name"].lower()) for x in evs if x["type"] == "name_suggestion" and x["auto_applied"]}
        res.append((it, pred, auto))
        events.append(evs)
        snippets.append(hist)
        calls += c
    return res, events, snippets, calls


async def run_replies(model, items, sem):
    async def one(it):
        async with sem:
            e = ContextEngine(model=model, timeout=30)
            us = [utt(d) for d in it["utts"]]
            ti = next(i for i, u in enumerate(us) if u.id == it["target"])
            e._done.update(u.id for u in us[:ti])  # only the target needs annotating
            before = copy.deepcopy(us)
            evs = await e.on_final(us[ti], us[:ti])
            await e.aclose()
            assert us == before  # never mutated
            return it, us, evs, e.calls

    out = await asyncio.gather(*(one(i) for i in items))
    rows = []
    for it, us, evs, calls in out:
        a = next((x for x in evs if x["type"] == "annotation" and x["utterance_id"] == it["target"]),
                 {"reply_to": None, "interrupts": None, "incomplete": False})
        x = it["expect"]
        rows.append((it, a, a["reply_to"] in x["reply_to"], a["interrupts"] == x["interrupts"], a["incomplete"] == x["incomplete"]))
    return rows, [(evs, us) for _, us, evs, _ in out], [c for *_, calls in out for c in calls]


def lat(calls):
    ls = sorted(c["latency"] for c in calls)
    if not ls:
        return "n/a"
    return (f"{st.median(ls):.2f}s median, {ls[int(.9 * (len(ls) - 1))]:.2f}s p90, "
            f"{100 * sum(l <= PROD_TIMEOUT for l in ls) // len(ls)}% within {PROD_TIMEOUT:.0f}s, {sum(not c['ok'] for c in calls)} failed")


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=MODELS)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    names, replies = load("names.jsonl")[: a.limit], load("replies.jsonl")[: a.limit]
    sem = asyncio.Semaphore(4)
    md = ["# Context AI evaluation (Card 4)", "",
          f"Hand-labeled sets: `eval/context/names.jsonl` ({len(names)} items, synthetic text written by us, not real speech) and "
          f"`eval/context/replies.jsonl` ({len(replies)} snippets). Each item runs through the production `ContextEngine.on_final` "
          "utterance by utterance (same prompt, validation, auto-apply and introduced-to-next-speaker rules). "
          "Prices are OpenRouter list prices per 1M tokens (in/out).", ""]
    summary, detail, guard_notes = [], [], []
    for m in a.models:
        nres, nev, nsn, ncalls = await run_names(m, names, sem)
        rrows, rev, rcalls = await run_replies(m, replies, sem)
        tp = sum(len(p & {(g["speaker"], g["name"].lower(), g["kind"]) for g in it["expect"]}) for it, p, _ in nres)
        npred = sum(len(p) for _, p, _ in nres)
        ngold = sum(len(it["expect"]) for it, _, _ in nres)
        negs = [(it, p) for it, p, _ in nres if not it["expect"]]
        false_items = sum(bool(p) for _, p in negs)
        gold_pairs = lambda it: {(g["speaker"], g["name"].lower()) for g in it["expect"]}  # noqa: E731
        bad_auto = sum(len(au - gold_pairs(it)) for it, _, au in nres)
        wrong_names = sum(len({(s, n) for s, n, _ in p} - gold_pairs(it)) for it, p, _ in nres)
        cost = sum(c["cost"] or 0 for c in ncalls + rcalls)
        calls = ncalls + rcalls
        viol = [v for evs, h in zip(nev, nsn) for v in verbatim_guard(evs, h)] + [v for evs, us in rev for v in verbatim_guard(evs, us)]
        n_ev = sum(len(e) for e in nev) + sum(len(e) for e, _ in rev)
        cats = {}
        for it, p, _ in nres:
            g = {(x["speaker"], x["name"].lower(), x["kind"]) for x in it["expect"]}
            c = cats.setdefault(it["cat"], [0, 0, 0, 0])  # tp, gold, pred, items
            c[0] += len(p & g); c[1] += len(g); c[2] += len(p); c[3] += 1
        ra = [sum(r[i] for r in rrows) for i in (2, 3, 4)]
        summary.append((m, tp, npred, ngold, false_items, len(negs), wrong_names, bad_auto, ra, calls, cost, len(viol), n_ev))
        d = [f"## {m}", "", "Per category (TP / gold / predicted):", ""] + [f"- {k}: {v[0]}/{v[1]}/{v[2]} over {v[3]} items" for k, v in cats.items()]
        d += ["", "Name misses and false names:"]
        for it, p, _ in nres:
            g = {(x["speaker"], x["name"].lower(), x["kind"]) for x in it["expect"]}
            if p != g:
                d.append(f"- {it['id']} [{it['cat']}] \"{' / '.join(u['text'] for u in it['utts'])}\" missed={sorted(g - p)} extra={sorted(p - g)}")
        d += ["", "Reply/interrupt misses:"]
        for it, an, ok1, ok2, ok3 in rrows:
            if not (ok1 and ok2 and ok3):
                d.append(f"- {it['id']} target {it['target']}: got reply_to={an['reply_to']} interrupts={an['interrupts']} incomplete={an['incomplete']}; expected {it['expect']}")
        detail += d + [""]
        guard_notes += viol
    md += ["## Names: model comparison", "",
           "| model | precision | recall | false-name items (negatives with any name) | wrong names / predictions | wrong auto-applied | latency (all calls) | cost |",
           "|---|---|---|---|---|---|---|---|"]
    for m, tp, npred, ngold, fi, nneg, wn, ba, ra, calls, cost, nv, ne in summary:
        md.append(f"| {m} | {pct(tp, npred)} ({tp}/{npred}) | {pct(tp, ngold)} ({tp}/{ngold}) | {pct(fi, nneg)} ({fi}/{nneg}) | "
                  f"{pct(wn, npred)} ({wn}/{npred}) | {ba} | {lat(calls)} | ${cost:.4f} |")
    md += ["", "Precision/recall count exact (speaker, name, kind) events. Precision counts the kind too, so a right name with the wrong kind is both a miss and a false event.", "",
           "## Reply / interrupt / incomplete annotation (target utterance only)", "",
           "| model | reply_to correct | interrupts correct | incomplete correct |", "|---|---|---|---|"]
    for m, *_, ra, calls, cost, nv, ne in [(s[0], *s[1:]) for s in summary]:
        n = len(replies)
        md.append(f"| {m} | {pct(ra[0], n)} ({ra[0]}/{n}) | {pct(ra[1], n)} ({ra[1]}/{n}) | {pct(ra[2], n)} ({ra[2]}/{n}) |")
    md += ["", "## Verbatim guard", ""]
    for s in summary:
        md.append(f"- {s[0]}: {s[11]} violations across {s[12]} emitted events (events carry only ids, thread labels, names present in the evidence text; utterance text never mutated, asserted per snippet).")
    # adversarial: a model that tries to rewrite text / invent ids / hallucinate names
    h = [Utterance("u1", "S1", 1, False, "Hi, I'm Sarah", [], 0, 1, True)]
    bad = [{"type": "annotation", "utterance_id": "u1", "reply_to": None, "interrupts": None, "thread_id": None, "incomplete": False, "text": "Hello, I am Sarah"},
           {"type": "annotation", "utterance_id": "u9", "reply_to": None, "interrupts": None, "thread_id": None, "incomplete": False},
           {"type": "annotation", "utterance_id": "u1", "reply_to": None, "interrupts": None, "thread_id": "the speaker greets", "incomplete": False},
           {"type": "name_suggestion", "id": "n1", "speaker_id": "S1", "name": "Maria", "evidence_utterance_id": "u1", "kind": "self_intro", "auto_applied": True},
           {"type": "catch_up", "items": [{"speaker_id": "S1", "utterance_ids": ["u1"], "summary": "x", "text": "Hi, I'm Sarah"}]}]
    md.append(f"- Adversarial check (rewritten text field, unknown id, free-text thread, hallucinated name, extra catch-up field): {len(verbatim_guard(bad, h))}/{len(bad)} rejected.")
    if guard_notes:
        md += ["", "Violations seen:"] + [f"- {v}" for v in guard_notes]
    md += [""] + detail
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(md) + "\n")
    print("\n".join(md[: 14 + 2 * len(summary)]))


asyncio.run(main())
