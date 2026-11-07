# Improvements beyond the spec

Each was kept only after it was measured against the spec's own approach. Numbers are real runs on the deployed
server or on Modal GPUs; "words understood" is 100 minus WER on held-out test sentences, never trained on.

## Personal model for S1 (spec 9.3)

His personal models, trained on his 50 training clips; 14 more are kept for testing and never trained on.
v2 lets training run longer (see "Longer training" below). One `eval_asr` run with the serving decoder:

| Condition (n clips) | Stock Whisper | v1 (spec defaults) | v2 (active) |
| --- | --- | --- | --- |
| Quiet (10) | 49.4% | 76.5% | 77.8% |
| Real noisy recordings (4) | 22.9% | 65.7% | 68.6% |
| Babble 5 dB (10) | 22.2% | 61.7% | 56.8% |
| Babble 0 dB (10) | 0.0% | 24.7% | 30.9% |

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

## Speech enhancement (spec 18: kept only if his error drops)

**Question:** does cleaning the microphone audio before Whisper lower his word error, especially with people talking nearby?
**Answer: no. No enhancer is adopted; Whisper hears the raw audio.** Every denoiser tried made the personal model's error
higher, most of them much higher, in quiet and in babble. Seen from the numbers: his consonant cues are what these models
remove or smear, and the remaining babble then triggers extra words.

**Method.** Each enhancer cleans every frozen test clip, then the stock model and the speaker's active personal adapter decode
it exactly as serving does (A10G, beam search). WER is `voice.evaluation.wer` (spec 15.2), corpus WER per condition; "mean WER" is
the mean over the frozen conditions, as the registry computes it. P1 uses `p1-whisper-lora-v2`, S1 uses `s1-whisper-lora-v1`.
Test clips: quiet 10 (about 80 reference words, so one word is about 1.3 points), real noisy 4 (S1 only; P1 has none), babble 5 dB 10,
babble 0 dB 10. The "pooled" columns add 3 extra babble draws (new seeds) of the same 10 sentences, so 40 clips per cell; the draws
share sentences, so they reduce babble-mixing noise, not sentence noise. Repeating the stock decode gave identical text on both
speakers, so each cell was run once. Run: `cd server && modal run scripts_enhance_eval.py::evaluate --speaker P1` (then `S1`);
timing with `::latency`; an implementation check (SI-SDR against the clean clip) with `::sanity`.

**Candidates** (all in `server/voice/audio/enhance.py`, `load_enhancer(name, device)`; all installed and ran): an 80 Hz causal
high-pass; loudness normalisation to -23 LUFS; both together; `noisereduce` 3.0.3 spectral gating (its torch implementation on the GPU,
stationary and non-stationary); DeepFilterNet 3 (`deepfilternet` 0.5.6) and a "soft" variant that may remove at most 12 dB;
SpeechBrain MetricGAN+ (`speechbrain/metricgan-plus-voicebank`); SpeechBrain SepFormer WHAM! 16 kHz enhancement.

**Personal model, WER % (lower is better), P1:**

| enhancer | ms per 6 s | quiet | babble 5db | babble 0db | mean WER | babble 5 dB pooled | babble 0 dB pooled | stock mean |
|---|---|---|---|---|---|---|---|---|
| none | 0 | 7.6 | 22.8 | 57.0 | **29.1** | 23.4 | 56.3 | 39.2 |
| highpass | 0.8 | 8.9 | 25.3 | 62.0 | **32.1** | 24.7 | 59.2 | 40.1 |
| loudnorm | 2.6 | 7.6 | 21.5 | 55.7 | **28.3** | 24.0 | 55.7 | 41.4 |
| highpass_loudnorm | 3.4 | 7.6 | 22.8 | 62.0 | **30.8** | 23.7 | 59.2 | 39.7 |
| noisereduce_stationary | 4.5 | 12.7 | 44.3 | 79.8 | **45.6** | 38.3 | 79.8 | 52.3 |
| noisereduce_nonstationary | 4.7 | 16.5 | 38.0 | 119.0 | **57.8** | 45.3 | 92.4 | 64.6 |
| deepfilternet3 | 43 | 11.4 | 68.3 | 119.0 | **66.2** | 82.0 | 111.4 | 70.9 |
| deepfilternet3_soft | 44 | 6.3 | 27.9 | 70.9 | **35.0** | 29.4 | 63.9 | 58.2 |
| metricgan_plus | 12.9 | 12.7 | 67.1 | 98.7 | **59.5** | 58.5 | 97.8 | 78.5 |
| sepformer_wham16k | 193 | 44.3 | 120.2 | 131.7 | **98.7** | 118.0 | 126.3 | 95.8 |
**Personal model, WER %, S1** (noisy real = 4 clips):

| enhancer | ms per 6 s | quiet | noisy real | babble 5db | babble 0db | mean WER | babble 5 dB pooled | babble 0 dB pooled | stock mean |
|---|---|---|---|---|---|---|---|---|---|
| none | 0 | 21.0 | 34.3 | 38.3 | 75.3 | **42.2** | 44.1 | 70.1 | 80.1 |
| highpass | 0.8 | 22.2 | 22.9 | 37.0 | 76.5 | **39.7** | 42.3 | 70.7 | 80.1 |
| loudnorm | 2.6 | 21.0 | 34.3 | 38.3 | 72.8 | **41.6** | 43.8 | 69.1 | 79.2 |
| highpass_loudnorm | 3.4 | 23.5 | 22.9 | 37.0 | 75.3 | **39.7** | 43.2 | 70.4 | 79.7 |
| noisereduce_stationary | 4.5 | 30.9 | 34.3 | 59.3 | 84.0 | **52.1** | 60.2 | 85.5 | 85.4 |
| noisereduce_nonstationary | 4.7 | 29.6 | 51.4 | 66.7 | 106.2 | **63.5** | 69.8 | 101.5 | 87.3 |
| deepfilternet3 | 43 | 29.6 | 28.6 | 104.9 | 119.8 | **70.7** | 104.6 | 127.5 | 96.1 |
| deepfilternet3_soft | 44 | 24.7 | 17.1 | 50.6 | 91.4 | **46.0** | 56.5 | 84.0 | 83.9 |
| metricgan_plus | 12.9 | 50.6 | 40.0 | 95.1 | 123.5 | **77.3** | 97.5 | 123.2 | 110.3 |
| sepformer_wham16k | 193 | 50.6 | 74.3 | 148.2 | 164.2 | **109.3** | 131.2 | 149.4 | 130.2 |
Latency is the median of 20 runs on 6 s of speech, A10G, GPU warm (`::latency`). Real time is met by everything except SepFormer (193 ms, fp32;
target 60 ms); DeepFilterNet 3 is 43 ms including resampling 16 to 48 kHz and back.

**Verdict by the rule** (lower mean WER, quiet WER up by no more than 1 point, personal model):
- DeepFilterNet 3, MetricGAN+, SepFormer, both `noisereduce` modes: fail. Quiet error rises 4 to 37 points (P1; 9 to 30 for S1) and babble error rises
  with it (P1 mean 29.1 to 45.6-98.7). They hurt the stock model as well (P1 mean 39.2 to 78.5 and 95.8 for MetricGAN+ and SepFormer).
- High-pass (and high-pass plus loudness): fail. S1 mean falls 42.2 to 39.7, but only through the 4 real noisy clips (34.3 to 22.9, four words), while
  quiet rises 1.2 points (2.5 with loudness) and pooled babble does not move (70.1 to 70.7 at 0 dB). On P1 the mean rises 29.1 to 32.1 (quiet +1.3).
- DeepFilterNet 3 soft: fail. Quiet P1 improves one word (7.6 to 6.3) and S1 real noisy 34.3 to 17.1, but babble gets worse (P1 pooled 0 dB 56.3 to 63.9, S1 70.1 to 84.0) and
  the means rise (29.1 to 35.0; 42.2 to 46.0).
- Loudness normalisation alone: passes the letter of the rule (mean 29.1 to 28.3, 42.2 to 41.6, quiet unchanged) but not the
  spirit: the gain is under one word, the pooled babble cells move both ways (P1 5 dB 23.4 to 24.0), and Whisper's log-mel features
  are close to loudness-invariant. Not adopted; it is harmless if a live microphone ever proves too quiet.

**Implementation check.** Against the clean clip (SI-SDR, dB) only DeepFilterNet 3 raises quality on white noise at 10 dB
(10.0 to 11.5, soft 13.2); on babble none does (5 dB: 5.0 to 4.2 at best). Babble is speech, so enhancers meant for noise keep
it or damage the target voice; this is why gating cannot help the case that matters here.

**Caveats.** Small test sets (the quiet cell is 10 sentences); S1's real noisy cell is 4 clips, and it is the only place where a
front end helped. Worth re-measuring when 20 or more real noisy clips exist (`noisy_real` is built from team `t01n` clips). Krisp and
Hush (spec 18) are not covered. Build notes for anyone re-running: `deepfilterlib` has no Python 3.12 wheel so the image builds it from
source with Rust and needs `git` (DeepFilterNet's logger calls it); there is no torchaudio for torch 2.15, so SpeechBrain runs on
torchaudio 2.11 installed without dependencies; DeepFilterNet needs a shim for a removed torchaudio module (`install_torchaudio_shim`).

**If an enhancer is ever adopted:** apply it in `voice/turns/turn.py` on the captured turn audio, once, before the recogniser and the
phrase matcher (both then see the same audio), behind a per-speaker setting, and only for the model it was measured with.
Image additions: the `apt` and `pip` lines of `enhance_image` in `scripts_enhance_eval.py`.

## Longer early-stopping patience for small data (S1 v2)

**What:** the trainer's early stopping waits 5 epochs without a validation gain (spec 9.3: 3) and runs up to 25 epochs
(spec: 15). Everything else in 9.3 is unchanged: training from the base model each time, rank 32, learning rate 1e-4,
the same augmentation, the promotion rule and the registry. `server/voice/training/trainer.py`, tested in
`server/tests/test_training_early_stopping.py`.

**Why:** with 50 clips the validation set is 5 clips (4 inside a cross-validation fold), so validation WER jumps by whole
words from epoch to epoch. With patience 3 most runs stopped at epoch 3 to 5 on that noise; the best epochs with patience 5
were 4 to 20.

**How it was chosen (validation only, never the test set):** 5-fold cross-validation on his 50 training clips
(`server/scripts_train_cv.py`). Each fold trains the real trainer on 40 clips (36 train, 4 validation for early stopping),
then decodes the 10 held-out clips with the serving recogniser, clean and mixed with babble at 5 and 0 dB. Score: mean of
the three pooled WERs over all 50 held-out clips. One change at a time, 3 training seeds (1234, 1, 2) for every contender.

| Variant (one change from the spec defaults) | Seeds | CV mean WER per seed | Average |
| --- | --- | --- | --- |
| Spec defaults (patience 3, 15 epochs) | 3 | 68.5, 62.2, 71.7 | 67.4 |
| **Patience 5, 25 epochs** | 3 | 56.4, 53.3, 53.4 | **54.3** |
| Learning rate 2e-4 | 3 | 55.3, 64.1, 53.5 | 57.6 |
| LoRA rank 64 | 3 | 56.2, 65.7, 55.4 | 59.1 |
| No speed change | 3 | 52.9, 66.5, 68.0 | 62.5 |
| Babble p=0.8 at -5 to 15 dB | 1 | 62.4 | |
| P1's 10 trainable clips added | 1 | 62.8 | |
| Stronger SpecAugment (0.1) | 1 | 65.5 | |
| Learning rate 5e-5 | 1 | 68.7 | |
| No babble | 1 | 69.8 | |
| LoRA rank 16 | 1 | 70.6 | |
| Stock Whisper (no training) | | 94.2 | |

Every patience-5 seed beat every default seed (per condition, averaged over seeds: quiet 35.2 vs 43.7, babble 5 dB 53.0 vs
65.5, babble 0 dB 74.7 vs 93.1). On top of patience 5, a second change did not help: learning rate 2e-4 56.3, rank 64 55.3,
stronger babble 55.9, stronger SpecAugment 56.5, P1's 10 trainable clips added 56.9 (3 seeds each, against 54.3). Not testable here:
a vocabulary decoder prompt (S1 has no vocabulary list, and the serving decoder has no prompt), and warm-starting from the
teammate's S1 adapter (it was trained on all 50 training clips, so cross-validation would leak, and 9.3 trains from base).

**Test result (once, after the choice; promotion rule decided):** words understood on his frozen test set, scored in one
`eval_asr` run with the current 5-beam serving decode.

| Condition (n clips) | Stock | v1 (spec defaults) | v2 (patience 5) |
| --- | --- | --- | --- |
| Quiet (10) | 49.4% | 76.5% | 77.8% |
| Real noisy (4) | 22.9% | 65.7% | 68.6% |
| Babble 5 dB (10) | 22.2% | 61.7% | 56.8% |
| Babble 0 dB (10) | 0.0% | 24.7% | 30.9% |
| Mean WER | 84.1 | 42.8 | 41.5 |

v2 was promoted (mean WER 40.9 vs 42.8 in its scoring run; quiet better) and is active. The test set is 34 clips, so v2's
lead over v1 on test is within a few words and is not by itself evidence; the evidence for the change is the
cross-validation above. Training time for 45 clips went from 82 s (v1, 15 epochs) to 132 s (v2, 25 epochs); the trainer's
240 s budget still bounds a large set. The stock and v1 numbers in the table at the top of this file came from an earlier
8-beam decode; the ones here supersede them.
