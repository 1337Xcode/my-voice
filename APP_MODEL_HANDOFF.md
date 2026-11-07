# App team handoff — S1 speech model v1

Updated: 2026-11-07. This document describes the existing trained model and the
current code. No retraining or inference was performed during this handoff repair.

## What is ready

The S1 English speech-to-text model has completed training and saved validation
and test evaluation. Use this frozen adapter for App integration:

| Item | Value |
| --- | --- |
| Adapter | `s1-whisper-lora-v1` |
| Base model | `openai/whisper-large-v3-turbo` |
| Modal volume | `speech-models` |
| Adapter directory in worker | `/models/s1-whisper-lora-v1` |
| Modal app name in code | `speech-whisper` |
| Code | `speech/app.py`, with `speech/checks.py` |
| Runtime | Modal A10G GPU; English transcription |
| Training | 45 clips, 5 validation clips; 8 epochs; checkpoint from epoch 6 |
| Adapter settings | LoRA rank 32, lr 1e-4, batch 4, accumulation 2 |

This is speech recognition for one speaker, not language translation, speaker
separation, a noise-removal model, or TTS. The adapter requires the base model;
it is not a standalone Android/Expo model. All evaluated S1 recordings are quiet.

## Existing invocation: CLI / Python worker

From the repository's `speech` directory, use a Python environment with Modal
installed and authenticated to the team workspace containing `speech-models`:

```bash
pip install modal
modal setup
modal run app.py::transcribe --model s1-whisper-lora-v1 --file /absolute/path/to/recording.m4a
```

This performs inference and can incur cloud charges. It does **not** train.
Do not run `train` or `upload` for App integration. Do not overwrite the frozen adapter.
Use `--model stock` only for an intentional baseline comparison; do not silently
switch users to another model on errors.

The existing worker method in `app.py` is:

```python
Transcriber(adapter="s1-whisper-lora-v1").run.remote(audio_bytes, suffix)
# returns (candidates: list[str], model_ms: int)
```

This is a Modal Python method used by the local entrypoint, **not an HTTP endpoint**.
The repository does not currently provide a verified deployed URL, authentication
contract, or React Native fetch integration. Declaring `modal.App(...)` does not
establish that a persistent service has been deployed. The integration owner must
expose the worker through an authenticated server endpoint and verify deployment.
Never embed Modal credentials in the mobile app.

## Input and output contract

- Input: one speaker's English recording, complete utterance, **0 < duration ≤ 30 s**.
- The CLI reads the file's bytes and actual extension, e.g. `.m4a` or `.wav`.
  The worker uses ffmpeg to decode, downmix to mono and resample to 16 kHz.
  Do not send base64 text as though it were raw audio bytes.
- Empty, undecodable, and >30-second clips fail. The App should cap recordings
  and offer retry/re-record instead of silently discarding audio.
- Output list: 1–5 strings. Index 0 is beam-search top-1 (5 beams); remaining
  strings are sampled alternatives, deduplicated and **not confidence-ranked**.
- Top-1 may be empty. Treat that as no usable transcription and ask for retry.
  Never assume there are exactly five candidates or that any candidate is correct.
- `model_ms` measures transcription after model loading/audio conversion. The CLI
  also prints round-trip time including upload/cold start. Neither has a recorded
  latency benchmark in the handoff; do not promise “1–2 seconds” yet.
- The current CLI prints human-readable output; do not parse stdout as the App API.

## Proposed App API contract — to implement, not currently deployed

A small server wrapper can accept `POST /transcribe` with multipart audio and a
request ID, then map the worker tuple into JSON. The server should pin the adapter
rather than let arbitrary client input select model paths.

Example response shape (illustrative, not a measured inference output):

```json
{
  "request_id": "example-001",
  "model": "s1-whisper-lora-v1",
  "text": "Please bring me some water.",
  "alternatives": ["Please bring some water."],
  "model_ms": 1200,
  "requires_confirmation": true
}
```

`alternatives` excludes top-1. Do not invent a confidence percentage. The wrapper
must provide stable errors for invalid audio, duration exceeded, timeout and
service failure; the App must preserve typed input and allow retry. Resolve the
actual URL, auth mechanism, upload-size limit and timeout with the integration
owner before connecting the App. These are not supplied by the training artifacts.

Recommended user flow: record → upload → show recognized text → user edits or
confirms → approved TTS speaks. If an LLM offers a rewritten sentence, retain the
original transcript and require confirmation of the changed meaning before TTS.
Keep TTS playback and microphone recording from overlapping during the first demo.
The model does not currently provide speaker isolation.

## Results that can be reported

| Split | Recordings | Stock WER | Adapted WER |
| --- | ---: | ---: | ---: |
| Validation, quiet | 5 | 50.0% | 14.7% |
| Final test, quiet | 14 | 60.3% | 24.1% |

The 14 test recordings cover **10 distinct sentences**, including 4 quiet retakes.
Relative test WER reduction is approximately 60%, calculated from rounded scores.
WER is word edit errors / reference words; 24.1% WER is not “75.9% accuracy”.
These are small-sample, single-speaker, quiet read-speech results. No noisy,
telephone-call, spontaneous-conversation or other-speaker evaluation is claimed.
Do not use final-test scores to choose additional variants of this model.

Evidence:

- `results/scores_test_v2.csv`: corrected current quiet results.
- `results/S1__s1-whisper-lora-v1__test.csv`: individual predictions.
- `results/S1__s1-whisper-lora-v1__test.json`: evaluation metadata.
- `results/provenance/s1-whisper-lora-v1.train_config.json`: original
  training configuration and full epoch history, downloaded read-only from Modal.
- `DATA_REVIEW.json`: user confirmation that all S1 recordings were
  individually checked and reference texts are correct, tied to file hashes.
  Historical “ok assumed” CSV notes are superseded by this confirmation.

## Provenance repair and version boundaries

The trained model's code hash starts `e36a9b9d3cb5`. Its original training dataset
hash starts `8e537e98c38a`; the corrected final-test dataset hash starts
`ef9e6bbe1c90`. The test labels/IDs were corrected after training; no weights were
changed for that correction.

The previous metadata merger overwrote the training dataset hash with the
current evaluation dataset hash. Code now saves `training_dataset_sha256` and
`evaluation_dataset_sha256` separately, retaining `dataset_sha256` as an
**evaluation** compatibility alias. Existing S1 JSON exports were repaired using
the original Modal training config; original exports are archived. Original
prediction CSVs, evaluation timestamps and executed-code hashes were not changed.

The local source hash changes with this repair. Old results remain historical
outputs of the earlier code, not outputs of a newly executed pipeline. The strict
`score` command will reject old code hashes; do not change those hashes to force
acceptance. Use the existing corrected score table for this handoff. No new
training or re-evaluation is required solely for this metadata repair.

## Integration acceptance checklist / ownership

| Owner | Next action | Done when |
| --- | --- | --- |
| Model owner | Provide this repo and access to the existing model volume | Integration owner can locate the frozen adapter |
| Integration/server owner | Wrap/deploy the existing worker with auth | Actual endpoint, request/response and error cases tested |
| App owner | Record/upload, show editable text and alternatives, confirm before TTS | Android/Expo end-to-end test works on a fresh utterance |
| App + integration owners | Measure first and subsequent requests | Cold/warm end-to-end timings recorded; waiting/retry UI tested |
| App + model owners | Check empty audio, >30 s, denied mic permission, network failure | No guessed text spoken; user has a recovery path |

This handoff does not claim the API, Android end-to-end run, latency benchmark,
or TTS integration is already complete. No model retraining is needed for these
integration tasks.

## This repository's layout

Run the inference command above from `speech/`. Existing audio lives at `audio/`
and the local data directory is the repository root. The original training
workspace used `raw/` paths. All 64 S1 audio files and transcript/split/condition
values have been checked against that workspace and match. Original CSV and
review records are preserved under `results/provenance/`; dataset hashes in old
results refer to the original layout and must not be changed to match this clone.
No data upload or re-evaluation is required for consuming the trained model.
The pipeline source is copied unchanged; commands for this checkout explicitly
supply `--data-dir ..` when needed. See `speech/README.md`.
