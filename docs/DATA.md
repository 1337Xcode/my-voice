# Data

What each speaker's recordings are, what was checked, and how problems were handled. Speakers are named only by id.

## S1

**Source.** The team's private recordings repo (one commit, 2026-11-07): `clips.csv` (the team contract's eight
columns), `clips_from_data.csv` (the Data teammate's original sheet) and 64 phone recordings in `audio/`. Imported with
`modal run jobs.py::import_team --speaker S1 --folder <clips.csv + audio/>`; the same 64 files (identical hashes)
were already in `speech-data/S1/incoming/`. No listener, test-log or other-system results exist yet.

**Splits and counts** (frozen test set `ee8e3c5d30`):

| Split | Condition | Clips | Sentences |
| --- | --- | --- | --- |
| train | quiet | 50 | Harvard lists 2-6, each once |
| test | quiet | 10 | Harvard list 1 |
| test | noisy_real | 4 | List 1 sentences 1-4, a second, separate take |
| test | babble_5db, babble_0db | 10 each | The quiet test takes mixed with the babble bank (fixed seed per clip) |

5.3 minutes of audio in total; clips last 3.6 to 6.5 s.

**Checks** (ffprobe, ffmpeg decode, Silero VAD, hashes; nothing in the repo was executed):

- Contract: the eight columns, speaker `S1` on every row, unique ids, every row's audio present and every file listed.
- Audio: all 64 are AAC m4a, 48 kHz stereo, and decode. No clipping, no silent or cut-off take (speech found in every
  file, at least 0.19 s of lead-in and 0.20 s of tail), peaks between -18 and -6.5 dBFS.
- Labels: all 64 match the Harvard sentences exactly. For 49 of the 50 training clips, a model that never saw the
  clip (5-fold cross-validation) transcribes it closer to its own label than to any other; the 50th (`S1_r080`, 5 words)
  comes out as "Most wide keeps chips in size" for "Mesh wire keeps chicks inside". No sign of recordings shifted
  against the list.
- Duplicates: no repeated audio (file and decoded-PCM hashes all distinct), no sentence in both train and test,
  no sentence twice in train. The noisy test takes correlate weakly (0.11-0.19) with the quiet takes, so they are
  separate recordings, not the quiet ones with noise added.

**Issues and handling:**

| Issue | Handling |
| --- | --- |
| The Data sheet had list 1 (`r31`-`r40`) in train while 4 of those sentences were the noisy test set: a train/test leak | The repo's `clips.csv` already moves list 1 to test; used as is. Nothing left to exclude from training |
| `ok` was blank in the Data sheet and set to `yes` with "confirm with Data" | All 64 kept: no defect found. Data should still confirm by listening |
| `S1_r084` (train) has the most background noise (SNR estimate 6.5 dB) | Kept; real noise in a training clip does no harm |
| `noisy_real` has 4 clips, and their noise floor measures like the quiet takes (about -42 dBFS) | Kept as its own condition; read it as "a second take", and always quote n |
| Test takes are about 5 dB louder at source than training takes | No action: import peak-normalises every clip |
