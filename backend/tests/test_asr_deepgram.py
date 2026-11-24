import json

from voxli.asr.deepgram_live import DeepgramLive


def results(words, final, speech_final=False, speaker=0):
    ws = [{"word": w.strip(".?,").lower(), "punctuated_word": w, "start": s, "end": e, "confidence": 0.9, "speaker": speaker}
          for w, s, e in words]
    return {"type": "Results", "is_final": final, "speech_final": speech_final,
            "channel": {"alternatives": [{"transcript": " ".join(w for w, _, _ in words), "words": ws}]}}


def eng(t0=0.0):
    e = DeepgramLive(api_key="x")
    e.t0 = t0
    return e


def test_interim_to_final_keeps_segment_id_and_adds_offset():
    e = eng(t0=10.0)
    a = e.handle(results([("Hello", 0.1, 0.4)], final=False))[0]
    b = e.handle(results([("Hello", 0.1, 0.4), ("there.", 0.5, 0.9)], final=False))[0]
    fin = e.handle(results([("Hello", 0.1, 0.4), ("there.", 0.5, 0.9)], final=True, speech_final=True))[0]
    assert a.segment_id == b.segment_id == fin.segment_id
    assert not a.is_final and fin.is_final
    assert fin.text == "Hello there." and fin.words[0].start == 10.1 and fin.end == 10.9
    assert fin.speaker_hint == "0"
    nxt = e.handle(results([("Next", 1.2, 1.5)], final=False))[0]
    assert nxt.segment_id != fin.segment_id


def test_sentence_pause_splits_into_finals_without_resending_words():
    e = eng()
    # interim already spans two sentences: the completed one is finalized, the tail stays interim
    out = e.handle(results([("Hi.", 0.0, 0.3), ("Yes", 1.0, 1.2)], final=False))
    assert [(r.text, r.is_final) for r in out] == [("Hi.", True), ("Yes", False)]
    assert out[0].segment_id != out[1].segment_id
    # Deepgram later finalizes the same chunk: "Hi." must not be emitted again
    assert e.handle(results([("Hi.", 0.0, 0.3), ("Yes", 1.0, 1.2)], final=True)) == []
    tail = e.handle(results([("it", 1.3, 1.5)], final=False))
    assert [r.text for r in tail] == ["Yes it"] and tail[0].segment_id == out[1].segment_id


def test_utterance_end_flushes_open_segment_once():
    e = eng()
    e.handle(results([("Hello", 0.0, 0.3)], final=True))  # is_final but no speech_final
    out = e.handle({"type": "UtteranceEnd", "last_word_end": 0.3})
    assert [(r.text, r.is_final) for r in out] == [("Hello", True)]
    assert e.handle({"type": "UtteranceEnd"}) == []


def test_malformed_and_unknown_messages_are_ignored():
    e = eng()
    for bad in [None, [], "x", {"type": "Results"}, {"type": "Results", "channel": {"alternatives": []}},
                {"type": "Results", "channel": {"alternatives": [{"words": [{"word": "x"}]}]}},
                {"type": "SpeechStarted"}, {"type": "Metadata"}]:
        assert e.handle(bad) == []
    assert not e.dead.is_set()
    e.handle({"type": "Error", "description": "boom"})
    assert e.dead.is_set() and e.error == "boom"


def test_empty_interims_do_not_emit():
    assert eng().handle(results([], final=False)) == []
    json.dumps(results([], final=True))  # fixture sanity


def test_speaker_turn_splits_final_so_one_caption_holds_one_voice():
    e = eng()
    msg = results([("Tea", 0.0, 0.3), ("please.", 0.3, 0.6), ("Latte", 0.65, 0.9), ("for", 0.9, 1.0), ("me.", 1.0, 1.2)],
                  final=True, speech_final=True)
    for w in msg["channel"]["alternatives"][0]["words"][2:]:
        w["speaker"] = 1  # second voice starts right after a sentence end, with only a 50 ms gap
    out = e.handle(msg)
    assert [(r.text, r.speaker_hint) for r in out] == [("Tea please.", "0"), ("Latte for me.", "1")]
    # a label flip mid-sentence with no pause is diarization jitter, not a turn
    m2 = results([("so", 2.0, 2.2), ("then", 2.2, 2.4), ("we", 2.4, 2.5)], final=True, speech_final=True)
    m2["channel"]["alternatives"][0]["words"][1]["speaker"] = 1
    assert len(e.handle(m2)) == 1


def test_final_chunk_ending_a_sentence_is_released_without_speech_final():
    e = eng()
    out = e.handle(results([("Pass", 0.0, 0.2), ("the", 0.2, 0.3), ("sugar.", 0.3, 0.6)], final=True))
    assert [(r.text, r.is_final) for r in out] == [("Pass the sugar.", True)]
    # an unfinished sentence still waits for more words
    assert e.handle(results([("And", 1.0, 1.2), ("then", 1.2, 1.4)], final=True)) == []
