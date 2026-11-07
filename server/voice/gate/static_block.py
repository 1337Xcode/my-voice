"""The static prompt prefix shared by every gate and repair call: guidance, sound note, phrase bank, vocabulary."""

from rapidfuzz.distance import Levenshtein

from voice.gate.candidates import normalise
from voice.gate.memory import EXPLICIT_SOURCES, load_pairs
from voice.phrases.bank import load_bank
from voice.storage import models_dir, read_json, speaker_dir

# The default note, used until there are enough corrections to measure his own pattern.
DEFAULT_NOTE = (
    "The recogniser most often confuses consonants made with the tongue (t, d, n, l, s, z, k, g, r, sh, ch); "
    "vowels and lip sounds (p, b, m, f, v, w) are more reliable."
)
# The note is recomputed from his corrections in blocks of this many, so the prefix (and its cache) stays stable between blocks.
CORRECTIONS_PER_UPDATE = 30
SOUND_CLASSES = {
    "tongue-tip consonants (t, d, n, l, s, z, r)": set("tdnlszr"),
    "back-of-tongue consonants (k, g, hard c)": set("kgcqx"),
    "lip consonants (p, b, m, f, v, w)": set("pbmfvw"),
    "vowels": set("aeiouy"),
}

GUIDANCE = """You help one speaker be understood. A speech recogniser trained on his own voice listens to him; its output is noisy because his consonants are hard to recognise. For each turn you get candidate sentences gathered from several sources, and you judge which one he actually said.

How to read the evidence:
- Recogniser hypotheses come ranked 1 to 5, each with how many of the recogniser's search beams ended on it and its word confidence (the average probability of its words). Most beams agreeing at high confidence means the recogniser is sure; split beams or low confidence mean it was guessing, and then the right sentence may be rank 2 or 3 or a blend of several hypotheses. How often the recogniser is right for him is measured below on his own held-out sentences: use that as the base rate.
- A phrase match means the audio sounded like one of his saved phrases, compared against his own recordings of it. A score near 1 with a clear margin over the runner-up is strong evidence. A saved phrase that also appears among the hypotheses is stronger still.
- A memory candidate is a sentence he has confirmed before, at least twice, when the recogniser heard something similar to what it heard now. The higher the similarity and the count, the stronger.
- A repair is a sentence an error-correction model rebuilt from the hypotheses. It is a suggestion, not evidence on its own; it counts when it agrees with other sources or clearly fits the conversation.
- Agreement between independent sources is the strongest single signal.
- The conversation so far, when there is one, tells you what he is likely to say next: a candidate that answers what was just said, or continues his last sentence, is more likely. With no conversation yet, or a change of subject, judge by the evidence alone; he may read text aloud or say something unexpected.
- He speaks everyday British English: short practical sentences in shops, cafés, on the phone, getting around and at home. Grammatical, sensible sentences are far more likely than odd ones; a hypothesis with a strange word in it is usually a misheard version of a common sentence.

How the recogniser goes wrong with his speech:
- Consonants shaped by the tongue blur into each other: t, d and n swap; s, z, sh and th swap; k and g swap; l and r often become w or vanish.
- Consonants at the end of a word often disappear, so "cold" can come out as "coal" or "code", and "card" as "car".
- Consonant clusters lose a sound: "street" can become "seet" and "please" can become "pease".
- Vowels, word count and rhythm are more reliable than consonants, so a candidate with the right number of syllables and the right vowels deserves weight even when its consonants differ from the hypotheses.
- Short function words (a, the, to, of, and) are often dropped or swapped by the recogniser; they rarely change which sentence he meant.

Choosing:
- Choose the sentence he most likely said, given all of the above.
- Being wrong out loud is far worse than asking him again. If no candidate is clearly likely, put the probability on "none". Never favour a sentence just because it is the only fluent one.
- Spread probability across candidates honestly when the evidence is split between them.

Worked examples (made up, to show the reasoning):
1. Hypotheses: "I need a mow men" (rank 1, log-probability -0.9), "I need a moment" (rank 2, -1.0). Phrase match: "I need a moment." (score 0.81, margin 0.35). The phrase match and hypothesis 2 agree and rank 1 is not a real sentence: "I need a moment." is very likely.
2. Conversation: the other person asked "Would you like it to take away?". Hypotheses: "yes peas" (rank 1), "yes please" (rank 2), "chase please" (rank 3). "Yes, please." answers the question and matches rank 2: very likely.
3. Hypotheses: "the bus is lake" (rank 1, -0.5), "the bus is late" (rank 2, -0.6). Memory: he has confirmed "The bus is late." 4 times when the recogniser heard something similar (similarity 0.92). Memory and rank 2 agree: very likely.
4. Hypotheses: "can we go the sore" (rank 1, -1.6), "can be cold door" (rank 2, -1.7), "cat be gold or" (rank 3, -1.9). No phrase match, no memory, nothing in the conversation points anywhere. The hypotheses disagree and the recogniser was guessing: put most of the probability on none.
5. Hypotheses: "see you later" (rank 1, -0.2) and "see you lady" (rank 2, -0.8), phrase match "See you later." (score 0.9). Everything agrees: very likely, even with no conversation.

Where he talks: at the counter of a café or shop, ordering and paying; on the phone, booking or asking about an order; on buses and trains and at stations; at home with family and friends; meeting new people. Expect requests, short answers (yes, no, thank you), questions about time, place and price, and polite openings and closings."""


def _class_of(letter: str) -> str | None:
    """The sound class a letter belongs to, or None for spaces, h, j and digits."""
    return next((name for name, letters in SOUND_CLASSES.items() if letter in letters), None)


def articulation_stats(pairs: list[tuple[str, str]]) -> dict[str, tuple[int, int]]:
    """Per sound class, (letters the recogniser got wrong, letters seen) in the meant text, aligning heard against meant."""
    stats = {name: [0, 0] for name in SOUND_CLASSES}
    for heard, meant in pairs:
        meant_n, heard_n = normalise(meant), normalise(heard)
        for op in Levenshtein.opcodes(meant_n, heard_n):
            for letter in meant_n[op.src_start:op.src_end]:
                name = _class_of(letter)
                if name:
                    stats[name][1] += 1
                    stats[name][0] += op.tag in ("replace", "delete")
    return {name: (wrong, seen) for name, (wrong, seen) in stats.items()}


def note_from_stats(stats: dict[str, tuple[int, int]]) -> str:
    """Turns per-class error counts into a one-sentence fact about which sounds the recogniser gets wrong."""
    rates = sorted(((wrong / seen, name) for name, (wrong, seen) in stats.items() if seen), reverse=True)
    worst = [(rate, name) for rate, name in rates[:2] if rate > 0]
    if not worst or len(rates) < 2:
        return DEFAULT_NOTE
    listed = ", then ".join(f"{name} ({rate:.0%} of them)" for rate, name in worst)
    best_rate, best = rates[-1]
    return (f"Measured from his corrections, the recogniser most often gets these sounds wrong: {listed}; "
            f"{best} are the most reliable ({best_rate:.0%} wrong).")


def corrections(speaker: str) -> list[tuple[str, str]]:
    """His explicit corrections where the recogniser's top guess differed from what he meant, oldest first."""
    return [(pair["heard"], pair["meant"]) for pair in load_pairs(speaker)
            if pair["source"] in EXPLICIT_SOURCES and normalise(pair["heard"]) != normalise(pair["meant"])]


def articulation_note(speaker: str) -> str:
    """The sound note: the default until 30 corrections, then measured from complete blocks of 30."""
    pairs = corrections(speaker)
    usable = len(pairs) - len(pairs) % CORRECTIONS_PER_UPDATE
    return note_from_stats(articulation_stats(pairs[:usable])) if usable else DEFAULT_NOTE


def vocabulary(speaker: str) -> list[str]:
    """Names, places and words he uses, from vocab.json (a list, or a dict of lists)."""
    stored = read_json(speaker_dir(speaker) / "vocab.json", [])
    groups = stored.values() if isinstance(stored, dict) else [stored]
    return [word.strip() for group in groups if isinstance(group, list) for word in group
            if isinstance(word, str) and word.strip()]


def recogniser_note(speaker: str) -> str:
    """The active model's measured accuracy on his held-out quiet sentences, as one factual sentence."""
    registry = read_json(models_dir(speaker) / "registry.json", {})
    active = registry.get("active")
    entry = registry.get("versions", {}).get(active, {}) if active else registry.get("stock", {})
    quiet = (entry.get("metrics") or {}).get("quiet")
    if not quiet:
        return "not measured yet."
    name = active or "the stock model"
    return f"{name} gets {quiet['words_understood']:.0f}% of words right on {quiet['n']} of his held-out sentences recorded in quiet."


def build_static_block(speaker: str) -> str:
    """The full static prefix for this speaker; identical across turns until his bank, vocabulary or note changes."""
    phrases = "\n".join(f"- {phrase.text}" for phrase in load_bank(speaker))
    words = ", ".join(vocabulary(speaker)) or "(none saved yet)"
    return (f"{GUIDANCE}\n\nAbout his sounds: {articulation_note(speaker)}\n\n"
            f"His saved phrases (he says these often):\n{phrases}\n\n"
            f"Names, places and words he uses: {words}")
