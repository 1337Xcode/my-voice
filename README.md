# my-voice: S1 recordings

Speaker `S1` recordings for fine-tuning and testing the speech model. Private repo: do not make public,
and do not copy the audio anywhere except our Drive and Modal account.

| Path | What |
| --- | --- |
| `audio/` | 64 phone recordings (m4a) |
| `clips.csv` | Clip list used by the training pipeline (`file` paths point into `audio/`) |
| `clips_from_data.csv` | Data's original sheet, unchanged |

## Changes from Data's sheet (pending Data's confirmation)

- Rows `r31`–`r40` (files `S1_t01`–`S1_t10`) were marked `train`, but `t01`–`t04` used the same
  sentences as `test`, which is a train/test leak. In `clips.csv` they are the 10 quiet test sentences
  `S1_t01`–`S1_t10`, and `S1_t01n`–`S1_t04n` are their noisy versions.
- `ok` was blank on every row; set to `yes` with a note.
- Result: 50 train (`S1_r041`–`S1_r090`), 10 quiet test, 4 noisy test, no sentence overlap.
