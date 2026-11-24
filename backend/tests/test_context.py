import asyncio
import copy
import json

import httpx

from voxli.context.engine import CUES, ContextEngine
from voxli.context.guard import verbatim_guard
from voxli.types import Speaker, Utterance


def U(i, spk, text, s, e):
    return Utterance(id=i, speaker_id=spk, speaker_confidence=1, speaker_uncertain=False, text=text,
                     words=[], start=s, end=e, is_final=True)


def engine(reply, status=200, delay=0, **kw):
    """Engine whose HTTP layer returns `reply` (dict -> JSON content, str -> raw content)."""
    sent = []

    async def handler(req):
        sent.append(json.loads(req.content))
        if delay:
            await asyncio.sleep(delay)
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(status, json={"choices": [{"message": {"content": content}}], "usage": {"cost": 1e-5}})

    eng = ContextEngine(api_key="test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)
    eng.sent = sent
    return eng


def run(c):
    return asyncio.run(c)


H = [U("u1", "S1", "Are we still meeting at noon?", 0, 2), U("u2", "S2", "Yes, noon works.", 2.2, 3.5)]


def test_annotations_validated_and_ids_only():
    out = {"annotations": [{"utterance_id": "u2", "reply_to": "u1", "interrupts": "u9", "thread_id": "t1", "incomplete": False}], "names": []}
    ev = run(engine(out).on_final(H[1], H[:1]))
    assert ev == [{"type": "annotation", "utterance_id": "u2", "reply_to": "u1", "interrupts": None, "thread_id": "t1", "incomplete": False}]
    assert verbatim_guard(ev, H) == []


def test_interrupt_marks_target_incomplete_and_rejects_forward_or_same_speaker():
    h = [U("u1", "S1", "So what I wanted to say was", 0, 2), U("u2", "S2", "Sorry, quick question", 1.8, 3)]
    out = {"annotations": [{"utterance_id": "u2", "reply_to": None, "interrupts": "u1", "thread_id": None, "incomplete": False}], "names": []}
    ev = run(engine(out).on_final(h[1], h[:1]))
    assert [(e["utterance_id"], e["interrupts"], e["incomplete"]) for e in ev] == [("u2", "u1", False), ("u1", None, True)]
    same = [U("u1", "S1", "a", 0, 1), U("u2", "S1", "b", 1, 2)]
    out["annotations"][0]["interrupts"] = "u1"
    assert run(engine(out).on_final(same[1], same[:1])) == []


def test_failures_return_no_events():
    for e in (engine("not json"), engine({"annotations": "x"}), engine({}, status=500), engine({}, delay=0.3, timeout=0.05),
              ContextEngine(api_key="")):
        assert run(e.on_final(H[1], H[:1])) == []


def test_self_intro_auto_applied_and_name_must_be_in_text():
    h = [U("u1", "S1", "Hi, I'm Sarah.", 0, 1)]
    out = {"annotations": [], "names": [{"utterance_id": "u1", "name": "Sarah", "kind": "self_intro", "target_speaker_id": None}]}
    ev = run(engine(out).on_final(h[0], []))
    assert len(ev) == 1 and ev[0]["auto_applied"] and ev[0]["speaker_id"] == "S1" and ev[0]["kind"] == "self_intro"
    assert verbatim_guard(ev, h) == []
    out["names"][0]["name"] = "Maria"  # hallucinated
    assert run(engine(out).on_final(h[0], [])) == []


def test_name_prefilter_skips_name_rules():
    e = engine({"annotations": [], "names": []})
    run(e.on_final(H[1], H[:1]))
    assert "self_intro" not in e.sent[0]["messages"][0]["content"]
    e2 = engine({"annotations": [], "names": []})
    run(e2.on_final(U("u3", "S1", "I'm Dana", 5, 6), []))
    assert "self_intro" in e2.sent[0]["messages"][0]["content"]
    assert CUES.search("this is my friend Sarah") and not CUES.search("Yes, noon works.")


def test_introduced_goes_to_next_different_speaker_not_auto():
    u1, u2, u3 = U("u1", "S1", "This is my friend Sarah.", 0, 2), U("u2", "S1", "She just moved here.", 2, 3), U("u3", "S2", "Nice to meet you all.", 3.5, 5)
    out = {"annotations": [], "names": [{"utterance_id": "u1", "name": "Sarah", "kind": "introduced", "target_speaker_id": None}]}
    e = engine(out)
    assert run(e.on_final(u1, [])) == []
    assert run(e.on_final(u2, [u1])) == []
    ev = run(e.on_final(u3, [u1, u2]))
    assert [(x["type"], x["speaker_id"], x["name"], x["auto_applied"], x["evidence_utterance_id"]) for x in ev if x["type"] == "name_suggestion"] == [("name_suggestion", "S2", "Sarah", False, "u1")]


def test_correction_targets_validated_speaker():
    e = engine({"annotations": [], "names": [{"utterance_id": "u2", "name": "Sara", "kind": "correction", "target_speaker_id": "S1"}]})
    e._named["S1"] = "Sarah"
    h = [U("u1", "S1", "I'm Sarah", 0, 1), U("u2", "S2", "No, it's Sara, no h.", 1, 2)]
    ev = run(e.on_final(h[1], h[:1]))
    assert ev[0]["speaker_id"] == "S1" and ev[0]["kind"] == "correction" and not ev[0]["auto_applied"]


def test_in_flight_calls_coalesce():
    async def go():
        e = engine({"annotations": [], "names": []}, delay=0.1, timeout=2)
        a = asyncio.create_task(e.on_final(H[0], []))
        await asyncio.sleep(0.01)
        b = await e.on_final(H[1], H[:1])  # skipped
        await a
        await e.on_final(U("u3", "S1", "ok", 4, 5), H)
        return e
    e = run(go())
    assert len(e.sent) == 2 and "u2" in e.sent[1]["messages"][1]["content"].split("annotate:")[1]


def test_verbatim_guard_rejects_text_fields_and_bad_ids():
    ev = [{"type": "annotation", "utterance_id": "u1", "reply_to": None, "interrupts": None, "thread_id": None, "incomplete": False, "text": "rewritten"},
          {"type": "annotation", "utterance_id": "zz", "reply_to": None, "interrupts": None, "thread_id": "a long sentence", "incomplete": False},
          {"type": "catch_up", "items": [{"speaker_id": "S2", "utterance_ids": ["u1"], "summary": "x"}]}]
    assert len(verbatim_guard(ev, H)) == 3


def test_engine_never_mutates_history():
    before = copy.deepcopy(H)
    e = engine({"annotations": [{"utterance_id": "u2", "reply_to": "u1", "interrupts": None, "thread_id": "t1", "incomplete": False}], "names": []})
    run(e.on_final(H[1], H[:1]))
    run(e.catch_up(H, [], 60))
    assert H == before


def test_catch_up_validates_and_falls_back():
    sp = [Speaker("S1", "Speaker A", "Ann"), Speaker("S2", "Speaker B")]
    good = {"items": [{"speaker_id": "S2", "utterance_ids": ["u2", "u1"], "summary": "agrees " * 20},
                      {"speaker_id": "S1", "utterance_ids": ["u1"], "summary": "asks about noon"}]}
    r = run(engine(good).catch_up(H, sp, 60))
    assert [i["utterance_ids"] for i in r["items"]] == [["u1"], ["u2"]] and len(r["items"][1]["summary"].split()) <= 15
    assert [i["summary"] for i in r["items"]][0] == "asks about noon"
    r = run(engine("garbage").catch_up(H, sp, 60))  # fallback: verbatim groups, no summary
    assert [(i["speaker_id"], i["utterance_ids"], i["summary"]) for i in r["items"]] == [("S1", ["u1"], ""), ("S2", ["u2"], "")]
    assert run(engine({}).catch_up([], sp, 60))["items"] == []


def test_suggest_replies():
    r = run(engine({"options": ["Noon works for me.", " ", "Can we make it 12:30?", "Sounds good!", "extra"]}).suggest_replies(H, []))
    assert r == {"type": "reply_suggestions", "options": ["Noon works for me.", "Can we make it 12:30?", "Sounds good!"]}
    assert run(engine("nope").suggest_replies(H, []))["options"] == []
