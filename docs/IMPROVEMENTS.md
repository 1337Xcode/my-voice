# Improvements beyond the spec

Each was kept only after it was measured against the spec's own approach. Numbers are real runs on the deployed
server or on Modal GPUs; "words understood" is 100 minus WER on held-out test sentences, never trained on.

## Personal model for S1 (spec 9.3, as specified)

Not an improvement on the spec, but the result it exists for: his first personal model, trained on 50 of his clips.

| Condition (n clips) | Stock Whisper | His model v1 |
| --- | --- | --- |
| Quiet (10) | 48.2% | 79.0% |
| Real noisy recordings (4) | 22.9% | 65.7% |
| Babble 5 dB (10) | 19.8% | 61.7% |
| Babble 0 dB (10) | 0.0% | 24.7% |

## App-to-app calls by code

**What:** besides Twilio phone calls (spec 13), his app has a 6-digit call code and a link. Anyone opens it in a browser
(iPhone Safari included), taps Call, and his app rings with an iPhone-style incoming-call screen. They hear only the
clear voice and see each sentence large; he sees their words as captions; "Working it out…" replaces dead air.
**Why:** works with no phone numbers, no Twilio account and no cost, and the other person reads his sentences as well
as hearing them. Verified end to end in two browsers against the live server.

## Speculative recognition

**What:** when he pauses for 300 ms, the recognisers start on the audio so far; if he doesn't resume, that result is
used when the turn ends (by silence or Done).
**Measured:** live S1 turns finished recognition 27–378 ms after the end of speech, against 720–1,000 ms without.

## Gate evidence and wording

**What:** the gate is told, per candidate, how many search beams ended on it and its word confidence, and gets the
active model's measured accuracy on his held-out sentences as a base rate. A hand-written prior ("rank 1 is often
wrong for him") and a penalty for sentences "from nowhere" were replaced by that measured data.
**Measured (Jev, same real recogniser outputs):** probability on correct sentences rose from 0.45 / 0.20 / 0.34 to
0.83 / 0.70 / 0.73, while a real two-way confusion stayed correct (0.84 "flat white" vs 0.15 "fat white"). Live P1 turns
went from "say again" on correct sentences to speaking them at 0.92 and 0.96.

## Gate calibration applied live (spec 15.4, completed)

The replay sets his live speak threshold through the server, so the threshold always matches his current model.
S1: 0.80 (34 clips; wrong-but-spoken under 2% at or above it). P1: 0.76 for Jev. gpt-6-luna needed 0.98 because its
probabilities are near 0 or 1 even when wrong, which is why Jev stays the default.

## "Tell the app" through Jev

**What:** his spoken request is mapped onto a fixed list of allowed changes by Jev's calibrated choice with "none of
these", instead of free-form generation.
**Measured:** "make the text bigger" → text size bigger (p 1.0); "always check with me first" → check first (0.97);
"talk a bit slower please" → slower (0.99); "can I have a flat white please" → no change (1.0).

## Warm connections and a one-hour repair cache

**What:** the TypeSafe, ElevenLabs and Anthropic connections are opened when the app says hello; the repair prompt
cache lasts an hour. **Measured:** a cold first Jev call took over 1.5 s (its timeout); warm calls 140–390 ms. Haiku
repair: first call over 1.2 s, then 735–860 ms.

## CTranslate2 decoder

**What:** Whisper decoding through CTranslate2 (float16) instead of transformers. **Measured on P1 (A10G, 10 clips per
condition):** 140 ms per clip instead of 706 ms (5 beams). Quiet WER identical; babble differs by one word on 10 clips,
in near-ties that flip both ways. It also fixes a real defect: transformers 5.22 returns the same top hypothesis five
times for Whisper n-best, so the gate and repair only ever saw one guess. CTranslate2 returns 4–5 distinct ones.
His models are re-scored with the new decoder so promotion is judged exactly as he is heard.

## Phone captions

**What:** on a real call the other person's speech arrived as one 30-second segment (line noise kept resetting the
pause). Captions now need two speech windows in a row to count as speech, cut long lines at a 300 ms pause, caption
the last line when the call ends, and log why a caption was dropped (never the words).
