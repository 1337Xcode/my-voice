"""The Results screen's data: words understood per system, learning over versions, live use, calibration."""

import csv
import io
from typing import Callable
import statistics

from voice.evaluation.wer import wer_percent, words_understood
from voice.turns.record import load_turns

HEADLINE_CONDITIONS = ("quiet", "babble_5db")
# Spoken sentences he then rejected count as wrong; picks and typing count as asks.
ASKED_ACTIONS = ("pick", "again")


def _cell(metrics: dict, condition: str) -> dict | None:
    entry = metrics.get(condition)
    return {"words_understood": entry["words_understood"], "n": entry["n"]} if entry else None


def model_rows(registry: dict) -> list[dict]:
    """Stock Whisper and each scored version, with words understood per headline condition."""
    rows = []
    if registry.get("stock"):
        rows.append({"system": "Stock Whisper", "kind": "stock", **{c: _cell(registry["stock"]["metrics"], c) for c in HEADLINE_CONDITIONS}})
    for name, entry in sorted(registry.get("versions", {}).items(), key=lambda item: item[1].get("version", 0)):
        if entry.get("metrics"):
            label = f"His model {name.rsplit('-', 1)[-1]}" + (" (active)" if name == registry.get("active") else "")
            rows.append({"system": label, "kind": "model", "version": name, **{c: _cell(entry["metrics"], c) for c in HEADLINE_CONDITIONS}})
    return rows


def _read_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig")
    return [{k.strip().lower(): (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(io.StringIO(text))]


def listener_rows(raw_csv: bytes | None, references: dict[str, str]) -> list[dict]:
    """New listeners (ids starting L, averaged) and the familiar listener (F) from the imported listeners.csv (quiet clips)."""
    if not raw_csv:
        return []
    by_listener: dict[str, list[tuple[str, str]]] = {}
    for row in _read_csv(raw_csv):
        listener = row.get("listener") or row.get("listener_id") or ""
        heard = row.get("hypothesis") or row.get("transcript") or row.get("heard") or ""
        if row.get("id") in references and listener:
            by_listener.setdefault(listener, []).append((references[row["id"]], heard))
    rows = []
    for label, prefix in (("New listeners", "L"), ("Familiar listener", "F")):
        groups = [pairs for name, pairs in by_listener.items() if name.upper().startswith(prefix)]
        if groups:
            scores = [words_understood(wer_percent([r for r, _ in g], [h for _, h in g])) for g in groups]
            rows.append({"system": label, "kind": "listener", "quiet": {"words_understood": round(statistics.mean(scores), 1), "n": sum(map(len, groups))}, "babble_5db": None})
    return rows


def live_use(speaker: str) -> dict:
    """Speed and safety from his real turns: median/p95 times, how often it asked, how often a spoken sentence was wrong."""
    turns = [t for t in load_turns(speaker) if t.get("action") and t.get("action") != "ignored" and t.get("mode") != "them"]

    def percentiles(key: str) -> dict:
        values = sorted(t[key] for t in turns if isinstance(t.get(key), (int, float)))
        if not values:
            return {"median": None, "p95": None, "n": 0}
        return {"median": int(statistics.median(values)), "p95": int(values[min(len(values) - 1, int(0.95 * len(values)))]), "n": len(values)}

    spoken = [t for t in turns if t.get("action") == "speak"]
    return {"turns": len(turns), "ms_end_to_text": percentiles("ms_end_to_text"), "ms_end_to_audio": percentiles("ms_end_to_audio"),
            "ask_rate": round(sum(t.get("action") in ASKED_ACTIONS for t in turns) / len(turns), 3) if turns else None,
            "wrong_spoken_rate": round(sum(t.get("outcome") == "rejected" for t in spoken) / len(spoken), 3) if spoken else None,
            "correction_rate": round(sum(t.get("outcome") in ("picked", "typed") for t in turns) / len(turns), 3) if turns else None}


def results(speaker: str, read: Callable[[str, str, object], object], read_bytes: Callable[[str, str], bytes | None]) -> dict:
    """Everything the Results screen shows, from real data only, read as the jobs last committed it."""
    registry = read("models", f"{speaker}/registry.json", {})
    frozen = read("data", f"{speaker}/eval/test_set.json", {})
    references = frozen.get("texts", {})
    pipeline = read("data", f"{speaker}/eval/pipeline_results.json", {})
    versions = [{"version": name, "quiet": _cell(e["metrics"], "quiet"), "babble_5db": _cell(e["metrics"], "babble_5db")}
                for name, e in sorted(registry.get("versions", {}).items(), key=lambda item: item[1].get("version", 0)) if e.get("metrics")]
    calibration = {p: {k: v for k, v in r.items() if k != "per_clip"} for p, r in pipeline.get("providers", {}).items()}
    listeners = listener_rows(read_bytes("data", f"{speaker}/eval/listeners.csv"), references)
    return {"headline": listeners + model_rows(registry), "learning": versions, "live": live_use(speaker),
            "calibration": calibration, "test_set": {"clips": len(frozen.get("all_ids", [])), "conditions": {k: len(v) for k, v in frozen.get("conditions", {}).items()}},
            "footnote": "Words understood = 100 minus word error rate on his held-out test sentences, never trained on."}
