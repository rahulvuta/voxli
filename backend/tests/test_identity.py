"""Identity engine tests. Logic tests use a fake 4-d embedder (the audio *is* the embedding);
the stability test runs real ECAPA on synthetic `say` clips from eval/clips/identity/."""
import json

import numpy as np
import pytest
import soundfile as sf

from voxli.config import ROOT
from voxli.identity.engine import IdentityEngine

CLIPS = ROOT / "eval" / "clips" / "identity"


def vec(*x):
    v = np.array(x, dtype=np.float32)
    return v / np.linalg.norm(v)


def seg(v, secs=2.0):
    """audio whose first 4 samples carry the (fake) embedding; the rest is non-silent filler."""
    return np.concatenate([v, np.full(int(secs * 16000) - len(v), 0.01, np.float32)])


def fake_engine(tmp_path):
    return IdentityEngine(embed=lambda a: a[:4] / np.linalg.norm(a[:4]), memory_path=tmp_path / "vm.json")


A, B, FAR = vec(1, 0, 0, 0), vec(0, 1, 0, 0), vec(0, 0, 1, 0)
MID = vec(0.55, 0.835, 0, 0)  # cos 0.55 to A: between T_LO and T_HI


def feed(eng, v, n=3, secs=2.0, **kw):
    return [eng.assign(seg(v, secs), 0, secs, **kw) for _ in range(n)]


def test_same_voice_keeps_id_and_new_voice_gets_new_id(tmp_path):
    eng = fake_engine(tmp_path)
    a1, a2 = feed(eng, A, 2)
    b1 = feed(eng, B, 1)[0]
    a3 = feed(eng, A, 1)[0]
    assert a1.is_new and not a2.is_new and b1.is_new
    assert a1.speaker_id == a2.speaker_id == a3.speaker_id != b1.speaker_id
    assert not a3.uncertain
    assert [s.label for s in eng.speakers()] == ["Speaker A", "Speaker B"]
    assert [s.color_index for s in eng.speakers()] == [0, 1]


def test_uncertain_zone_guesses_but_flags_and_does_not_pollute(tmp_path):
    eng = fake_engine(tmp_path)
    feed(eng, A, 3)
    c_before = eng._voices["S1"].centroid.copy()
    a = feed(eng, MID, 1)[0]
    assert a.speaker_id == "S1" and a.uncertain and not a.is_new
    assert np.allclose(eng._voices["S1"].centroid, c_before)
    assert len(eng.speakers()) == 1


def test_two_agreeing_in_between_segments_found_a_new_speaker(tmp_path):
    eng = fake_engine(tmp_path)
    feed(eng, A, 3)
    first, second = feed(eng, MID, 2)
    assert first.uncertain and not first.is_new
    assert second.is_new and second.speaker_id == "S2" and not second.uncertain


def test_short_segments_are_weak_evidence(tmp_path):
    eng = fake_engine(tmp_path)
    assert eng.assign(seg(A, 0.6), 0, 0.6).speaker_id == "UNKNOWN"      # nobody known yet: no new speaker
    feed(eng, A, 3), feed(eng, B, 3)
    r = eng.assign(seg(FAR, 0.6), 0, 0.6)                                # unlike everyone: still no new speaker
    assert r.speaker_id == "UNKNOWN" and r.uncertain and len(eng.speakers()) == 2
    r = eng.assign(seg(A, 0.6), 0, 0.6)                                  # matches, but short => capped, flagged
    assert r.speaker_id == "S1" and r.confidence <= 0.6
    assert eng.assign(seg(A, 0.2), 0, 0.2).speaker_id == "UNKNOWN"       # too short to embed at all


def test_hint_breaks_ties_for_short_segments(tmp_path):
    eng = fake_engine(tmp_path)
    feed(eng, A, 3, hint="0"), feed(eng, B, 3, hint="1")
    both = vec(1, 1, 0, 0)  # equally close to both speakers
    assert eng.assign(seg(both, 0.6), 0, 0.6, hint="1").speaker_id == "S2"
    assert eng.assign(seg(both, 0.6), 0, 0.6, hint="0").speaker_id == "S1"


def test_mute_windows(tmp_path):
    eng = fake_engine(tmp_path)
    eng.add_mute_window(10.0, 12.0)
    assert eng.is_muted(11.0, 11.5) and eng.is_muted(9.0, 10.5) and eng.is_muted(11.9, 13.0)
    assert not eng.is_muted(8.0, 10.0) and not eng.is_muted(12.0, 13.0)


def test_manual_merge_and_rename(tmp_path):
    eng = fake_engine(tmp_path)
    feed(eng, A, 2), feed(eng, B, 2)
    eng.rename("S2", "Sarah")
    eng.merge("S2", "S1")
    assert [s.id for s in eng.speakers()] == ["S1"] and eng.speakers()[0].name == "Sarah"
    # B's voice now belongs to S1; the next new voice never reuses S2
    assert feed(eng, B, 1)[0].speaker_id == "S1"
    assert feed(eng, FAR, 1)[0].speaker_id == "S3"


def test_auto_merge_when_two_speakers_converge(tmp_path):
    eng = fake_engine(tmp_path)
    near = vec(0.9, 0.436, 0, 0)  # cos 0.9 to A
    s1, s2 = eng._make(A, 2.0), eng._make(near, 2.0)
    for _ in range(2):
        eng._voices[s1].add(A, 2.0), eng._voices[s2].add(near, 2.0)
    assert eng.pending_merges() == []
    eng.assign(seg(A), 0, 2.0)
    assert eng.pending_merges() == [("S2", "S1")] and eng.pending_merges() == []
    assert [s.id for s in eng.speakers()] == ["S1"]


def test_voice_memory_roundtrip_forget_and_off_by_default(tmp_path):
    path = tmp_path / "vm.json"
    eng = fake_engine(tmp_path)
    feed(eng, A, 3), feed(eng, B, 3)
    assert not path.exists()                                   # off by default: nothing on disk
    eng.set_voice_memory(True)
    eng.rename("S1", "Sarah")
    data = json.loads(path.read_text())
    assert [r["name"] for r in data["speakers"]] == ["Sarah", None]
    assert set(data["speakers"][0]) == {"name", "name_source", "n", "centroid"}  # embeddings only

    later = fake_engine(tmp_path)                              # a new session
    later.set_voice_memory(True)
    assert [s.name for s in later.speakers()] == ["Sarah", None]
    r = later.assign(seg(A), 0, 2.0)
    assert r.speaker_id == "S1" and not r.is_new and not r.uncertain

    later.forget_all()
    assert later.speakers() == [] and not path.exists()

    eng.set_voice_memory(True)
    eng.set_voice_memory(False)                                # turning it off also deletes the file
    assert not path.exists()


@pytest.fixture(scope="module")
def ecapa():
    if not (CLIPS / "Daniel_3.wav").exists():
        pytest.skip("run backend/scripts/make_identity_clips.py first")
    from voxli.identity.embed import Ecapa
    return Ecapa()


def test_real_voices_stable_across_turns(ecapa, tmp_path):
    voices = ["Samantha", "Daniel", "Rishi", "Moira"]
    eng = IdentityEngine(embed=ecapa, memory_path=tmp_path / "vm.json")
    seen: dict[str, set[str]] = {v: set() for v in voices}
    for turn in (3, 5, 2, 7, 4, 6):        # 6 turns; the voices take turns each round
        for v in voices:
            x = sf.read(CLIPS / f"{v}_{turn}.wav", dtype="float32")[0]
            a = eng.assign(x, 0, len(x) / 16000)
            seen[v].add(a.speaker_id)
    ids = {v: max(seen[v], key=lambda i: i != "UNKNOWN") for v in voices}
    assert len(set(ids.values())) == 4                       # four voices -> four identities
    assert len(eng.speakers()) == 4
    # after the first rounds, each voice maps to exactly one id
    assert all(len(seen[v] - {"UNKNOWN"}) == 1 for v in voices), seen


def test_match_is_read_only():
    import numpy as np
    from voxli.identity.engine import IdentityEngine
    rng = np.random.default_rng(0)
    vecs = {"a": rng.normal(size=192), "b": rng.normal(size=192)}
    eng = IdentityEngine(embed=lambda x: (lambda v: v / np.linalg.norm(v))(vecs["a"] if x[0] > 0 else vecs["b"]))
    a = np.full(16000 * 2, 0.1, dtype=np.float32)
    b = np.full(16000 * 2, -0.1, dtype=np.float32)
    assert eng.match(a).speaker_id == "UNKNOWN"  # no voices yet, and match must not create one
    eng.assign(a, 0, 2)
    n = len(eng.speakers())
    assert eng.match(a).speaker_id == "S1" and not eng.match(a).uncertain
    assert eng.match(b).speaker_id == "UNKNOWN" and len(eng.speakers()) == n
