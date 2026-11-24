from types import SimpleNamespace as T

from voxli.asr.local_parakeet import tokens_to_words


def test_tokens_group_into_words_with_offset_and_mean_confidence():
    toks = [T(text=" Hel", start=0.0, end=0.2, confidence=1.0), T(text="lo", start=0.2, end=0.4, confidence=0.5),
            T(text=" there", start=0.5, end=0.9, confidence=0.9), T(text=".", start=0.9, end=0.95, confidence=0.9)]
    w = tokens_to_words(toks, t0=10.0)
    assert [x.w for x in w] == ["Hello", "there."]
    assert (w[0].start, w[0].end, w[1].end) == (10.0, 10.4, 10.95)
    assert w[0].conf == 0.75
