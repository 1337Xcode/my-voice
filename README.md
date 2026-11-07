# my-voice: S1 speech model and recordings

Speaker `S1` recordings for fine-tuning and testing the speech model. Private repo: do not make public,
and do not copy the audio anywhere except our Drive and Modal account.

| Path | What |
| --- | --- |
| `audio/` | 64 phone recordings (m4a) |
| `clips.csv` | Clip list used by the training pipeline (`file` paths point into `audio/`) |
| `clips_from_data.csv` | Data's original sheet, unchanged |

## Data corrections and confirmed review

- Rows `r31`–`r40` (files `S1_t01`–`S1_t10`) were marked `train`, but `t01`–`t04` used the same
  sentences as `test`, which is a train/test leak. In `clips.csv` they are the 10 test sentences
  `S1_t01`–`S1_t10`.
- Data's `t01`–`t04` were labelled `noisy`, but every recording was made in quiet. They are second
  quiet takes of test sentences 1–4, renamed `S1_t01b`–`S1_t04b` (retake naming; an `n` suffix means noisy).
- There are no noisy recordings. The model has not been tested in noise.
- `ok` was originally blank and imported as `yes`. On 2026-11-07 the user confirmed that all recordings were individually checked and transcripts are correct. `DATA_REVIEW.json` records that confirmation against file hashes and supersedes the historical pending notes.
- Result: 50 train (`S1_r041`–`S1_r090`), 14 quiet test clips (10 sentences, 4 recorded twice), no sentence overlap.

## Model handoff

Read [APP_MODEL_HANDOFF.md](APP_MODEL_HANDOFF.md) first. The frozen adapter is
`s1-whisper-lora-v1` on Modal's `speech-models` volume; no retraining is needed.

| Path | Purpose |
| --- | --- |
| `speech/` | Modal pipeline, validation helpers and local tests |
| `APP_MODEL_HANDOFF.md` | Model identity, invocation, proposed App API, integration checklist |
| `results/` | S1 validation and final-test predictions and score tables |
| `results/provenance/` | Original training config, original workspace CSV and review evidence |
| `DATA_REVIEW.json` | Reviewed S1 file hashes and verified repository mapping |

Training used 45 clips with 5 validation clips. All 14 final test recordings are
quiet and cover 10 distinct sentences (4 retakes). Saved test WER: stock 60.3%,
adapted 24.1%. There is no noisy evaluation or verified App endpoint yet.

The code/result provenance fix did not change weights or rerun inference.
Historical code/data hashes are preserved. The original workspace used different
file paths; do not relabel its hashes as hashes of this repository's layout.
