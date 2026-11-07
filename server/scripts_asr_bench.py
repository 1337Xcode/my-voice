"""Benchmarks the serving recogniser on real recordings on the serving GPU: n-best output and milliseconds per stage.

Run: cd server && modal run scripts_asr_bench.py --speaker P1 --limit 6
"""

import modal

from main import data_volume, models_volume, secret, serve_image

app = modal.App("my-voice-asr-bench")


@app.function(image=serve_image, gpu="A10G", volumes={"/data": data_volume, "/models": models_volume}, secrets=[secret], timeout=900)
def bench(speaker: str, limit: int, adapter: str = "", beams: int = 8, compiled: bool = False) -> list[dict]:
    """Decodes up to `limit` of the speaker's wavs and returns text, n-best and timing for each."""
    import csv
    import time
    from pathlib import Path

    from voice.asr.whisper import load_whisper
    from voice.audio.pcm import read_audio

    whisper = load_whisper("cuda")
    if compiled:
        whisper.model.generation_config.cache_implementation = "static"
        whisper.model.forward = __import__("torch").compile(whisper.model.forward, mode="reduce-overhead", fullgraph=False)
    if adapter:
        whisper.set_adapter(f"/models/{adapter}")
    rows = list(csv.DictReader(open(f"/data/{speaker}/clips.csv", encoding="utf-8")))[:limit]
    for _ in range(3 if compiled else 1):  # warm-up (compilation happens here)
        whisper.nbest(read_audio(Path(f"/data/{speaker}/wav/{rows[0]['id']}.wav")), beams=beams)
    results = []
    for row in rows:
        audio = read_audio(Path(f"/data/{speaker}/wav/{row['id']}.wav"))
        started = time.perf_counter()
        recognition = whisper.nbest(audio, beams=beams)
        results.append({"id": row["id"], "seconds": round(audio.size / 16000, 2), "ms": round((time.perf_counter() - started) * 1000), "split": whisper.last_split_ms,
                        "reference": row["text"], "nbest": [h.text for h in recognition.hypotheses], "no_speech": recognition.no_speech_probability})
    return results


@app.local_entrypoint()
def main(speaker: str = "P1", limit: int = 6, adapter: str = "", beams: int = 8, compiled: bool = False):
    for row in bench.remote(speaker, limit, adapter, beams, compiled):
        print(f"{row['id']} {row['seconds']}s {row['ms']}ms {row['split']} no_speech={row['no_speech']}\n  ref: {row['reference']}\n  " + "\n  ".join(row["nbest"]))
