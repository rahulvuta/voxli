import pytest

from voxli.session import Session
from voxli.types import Speaker


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeIdentity:
    def __init__(self):
        self.sp = {"S1": Speaker(id="S1", label="Speaker A")}

    def rename(self, sid, name, source="user"):
        s = self.sp.get(sid)
        if s:
            s.name, s.name_source = name, source
        return s

    def speakers(self):
        return list(self.sp.values())

    def pending_merges(self):
        return []

    def pending_relabels(self):
        return []


class NoASR:
    name = "offline"
    async def start(self, cb): pass
    async def feed(self, pcm=b""): pass
    async def stop(self): pass


def make():
    out = []

    async def send(ev):
        out.append(ev)
    s = Session(send, asr=NoASR(), identity=FakeIdentity())
    return s, out


def sugg(auto, id="n1", name="Sarah"):
    return {"type": "name_suggestion", "id": id, "speaker_id": "S1", "name": name,
            "evidence_utterance_id": "u1", "kind": "self_intro", "auto_applied": auto}


def name_of(s):
    sp = s.identity.sp["S1"]
    return sp.name, sp.name_source


@pytest.mark.anyio
async def test_auto_applied_is_renamed_then_undo_restores_previous():
    s, out = make()
    s.identity.rename("S1", "Sam", "user")
    await s._on_suggestion(sugg(True))
    assert name_of(s) == ("Sarah", "auto")
    assert any(e["type"] == "speaker" and e["speaker"]["name"] == "Sarah" for e in out)
    await s.control({"type": "name_suggestion_response", "suggestion_id": "n1", "accept": False})
    assert name_of(s) == ("Sam", "user")
    assert out[-1]["type"] == "speaker" and out[-1]["speaker"]["name"] == "Sam"


@pytest.mark.anyio
async def test_undo_with_no_previous_name_clears_it():
    s, _ = make()
    await s._on_suggestion(sugg(True))
    await s.control({"type": "name_suggestion_response", "suggestion_id": "n1", "accept": False})
    assert name_of(s) == (None, None)


@pytest.mark.anyio
async def test_non_auto_suggestion_waits_for_accept_and_reject_changes_nothing():
    s, out = make()
    await s._on_suggestion(sugg(False))
    assert name_of(s) == (None, None) and out == []
    await s.control({"type": "name_suggestion_response", "suggestion_id": "n1", "accept": True})
    assert name_of(s) == ("Sarah", "suggested")
    s2, out2 = make()
    await s2._on_suggestion(sugg(False))
    await s2.control({"type": "name_suggestion_response", "suggestion_id": "n1", "accept": False})
    assert name_of(s2) == (None, None) and out2[-1]["type"] == "speaker"  # still emits an update


@pytest.mark.anyio
async def test_unknown_suggestion_id_is_a_bad_message():
    s, _ = make()
    with pytest.raises(ValueError):
        await s.control({"type": "name_suggestion_response", "suggestion_id": "zzz", "accept": True})


@pytest.mark.anyio
async def test_late_merge_remaps_utterances_and_resends_survivor():
    from voxli.types import Utterance
    s, out = make()
    s.identity.sp["S2"] = Speaker(id="S2", label="Speaker B")
    await s._sync_speakers()
    u = Utterance(id="u1", speaker_id="S2", speaker_confidence=1, speaker_uncertain=False, text="x", words=[],
                  start=0, end=1, is_final=True)
    s.history.append(u)
    del s.identity.sp["S2"]
    s.identity.pending_merges = lambda: [("S2", "S1")]
    out.clear()
    await s._sync_speakers()
    assert u.speaker_id == "S1"
    assert out[0] == {"type": "speaker_removed", "id": "S2", "merged_into": "S1"}
    assert out[1]["type"] == "speaker" and out[1]["speaker"]["id"] == "S1"
