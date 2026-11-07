# Existing S1 model: inference and integration

Start with [the App handoff](../APP_MODEL_HANDOFF.md). The trained adapter is
`speech-models:/s1-whisper-lora-v1` on the team's Modal workspace. This repository
contains its Python pipeline and saved evaluation evidence; weights remain on Modal.

## Inference only (no training)

From this directory, using a Python environment with Modal installed:

```bash
pip install modal
modal setup
modal run app.py::transcribe --model s1-whisper-lora-v1 --file ../audio/S1_t01.m4a
```

This is cloud inference and can incur charges. It is not an HTTP API. The App
integration owner must wrap/deploy the worker and provide an authenticated endpoint.
Do not put Modal tokens in the mobile app. Input duration must be >0 and <=30s;
output is top-1 plus up to four unranked sampled alternatives. See the handoff for
confirmation, errors, TTS and latency requirements.

## Repository-specific data paths

The source was copied unchanged from the model workspace. Its default
`--data-dir ../hack-speech` belongs to that original workspace, not this checkout.
For any future upload/baseline/evaluate/score invocation from `speech/`, explicitly
use `--data-dir ..`. The existing `clips.csv` points to `audio/`.

Do not upload, train or rerun final tests merely to integrate the existing model.
Upload would replace the data-volume manifest with this checkout's different path
layout. Historical result hashes belong to the original workspace; the frozen
CSV and user review are included under `results/provenance/`. Do not rewrite old
hashes to bypass strict result checks. The provenance repair changed local source
hashes but did not rerun inference; use the saved score tables for this handoff.

## Local checks (no cloud calls)

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile app.py checks.py
```

These checks validate guards and provenance logic, not a deployed endpoint or
Android integration. The existing frozen adapter needs no retraining.
