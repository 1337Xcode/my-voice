"""Candidate merging and de-duplication (spec 8.5)."""

from voice.gate.candidates import Hypothesis, MemoryHit, PhraseMatch, build_candidates, normalise


def test_normalise_ignores_case_punctuation_brackets_and_spacing():
    assert normalise("  Can I have a flat white,   please? ") == "can i have a flat white please"
    assert normalise("I’d like [music] a TEA.") == "id like a tea"
    assert normalise("...") == ""


def test_merge_keeps_every_source_and_prefers_the_phrase_text():
    nbest = [Hypothesis("can I have a fat white please", -0.4), Hypothesis("can I have a flat white please", -0.6)]
    phrases = [PhraseMatch("p11", "Can I have a flat white, please?", 0.21, 0.82, 0.4)]
    memory = [MemoryHit("Can I have a flat white please.", 0.91, 3)]
    candidates = build_candidates(nbest, phrases, memory, ["Can I have a flat white, please?"])
    assert [c.id for c in candidates] == ["c1", "c2"]
    flat = candidates[0]
    assert flat.text == "Can I have a flat white, please?"
    assert flat.sources == ["asr", "phrase", "memory", "repair"]
    assert flat.agree == 4
    assert (flat.asr_rank, flat.asr_logprob) == (2, -0.6)
    assert (flat.phrase_id, flat.phrase_score, flat.phrase_margin) == ("p11", 0.82, 0.4)
    assert (flat.memory_similarity, flat.memory_count) == (0.91, 3)
    fat = candidates[1]
    assert (fat.text, fat.sources, fat.asr_rank, fat.phrase_score) == ("can I have a fat white please", ["asr"], 1, None)


def test_duplicate_hypotheses_keep_the_best_rank_and_its_text():
    nbest = [Hypothesis("Thank you very much.", -0.2), Hypothesis("thank you very much", -0.3)]
    [only] = build_candidates(nbest, [], [])
    assert (only.text, only.asr_rank, only.asr_logprob, only.sources) == ("Thank you very much.", 1, -0.2, ["asr"])


def test_at_most_ten_candidates_most_agreed_then_most_trusted_first():
    nbest = [Hypothesis(f"sentence number {i}", -float(i)) for i in range(1, 6)]
    phrases = [PhraseMatch(f"p{i}", f"phrase number {i}", 0.3, 0.3, 0.1) for i in range(1, 6)]
    repairs = ["sentence number 5", "repair one", "repair two"]
    candidates = build_candidates(nbest, phrases, [], repairs)
    assert len(candidates) == 10
    assert candidates[0].text == "sentence number 5" and candidates[0].agree == 2
    assert [c.id for c in candidates] == [f"c{i}" for i in range(1, 11)]
    texts = [c.text for c in candidates]
    assert texts[6:] == ["repair one", "repair two", "sentence number 1", "sentence number 2"]  # ranks 3 and 4 dropped


def test_empty_text_is_dropped():
    assert build_candidates([Hypothesis("  ", -1.0)], [], []) == []
