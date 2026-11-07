"""Scoring a new version against the active one and promoting it only when spec 9.3's rule says it is better."""

import logging
import time
from typing import Callable

import httpx

from voice.clips.selection import FrozenTestSet
from voice.config import MODELS_ROOT, MissingKey, optional, require
from voice.evaluation.asr_eval import record_version_scores, score_model, version_folder
from voice.training.registry import active_scores, save_registry, should_promote, write_status

log = logging.getLogger("voice.training")

DEFAULT_SERVER_URL = "https://xc0d3--my-voice-speech-web.us-east.modal.run"
# A cold serving container loads its models before it answers, so allow it time.
RELOAD_TIMEOUT_S = 120
RELOAD_ATTEMPTS = 2


def notify_server(speaker: str) -> str:
    """Asks the serving container to reload the volume and swap adapters; returns a plain outcome line."""
    url = f"{optional('SERVER_URL', DEFAULT_SERVER_URL).rstrip('/')}/internal/reload"
    headers = {"Authorization": f"Bearer {require('INTERNAL_TOKEN', 'the reload call after a promotion')}"}
    for attempt in range(RELOAD_ATTEMPTS):
        try:
            response = httpx.post(url, params={"speaker": speaker}, headers=headers, timeout=RELOAD_TIMEOUT_S)
        except httpx.HTTPError as error:
            outcome = f"server unreachable ({error.__class__.__name__})"
        else:
            if response.status_code < 400:
                return "server reloaded"
            if response.status_code in (401, 403):
                return "server refused the reload: INTERNAL_TOKEN is wrong or missing on one side"
            outcome = f"server answered {response.status_code}: {response.text[:200]}"
            if response.status_code != 429 and response.status_code < 500:
                return outcome
        time.sleep(2**attempt)
    return outcome


def ensure_baseline(whisper, registry: dict, speaker: str, frozen: FrozenTestSet) -> dict:
    """The active model's scores on this test set (stock while none is active), re-scored if the set changed."""
    current = active_scores(registry)
    if current is not None and current.get("test_set") == frozen.id:
        return current
    if registry.get("active"):
        entry = registry["versions"][registry["active"]]
        record_version_scores(entry, *score_model(whisper, speaker, frozen, str(version_folder(entry))))
        return entry
    registry["stock"] = score_model(whisper, speaker, frozen, None)[0]
    return registry["stock"]


def active_label(registry: dict) -> str:
    """The active model as he sees it: 'v<N>' or 'stock'."""
    if not registry.get("active"):
        return "stock"
    return f"v{registry['versions'][registry['active']]['version']}"


def evaluate_and_decide(whisper, registry: dict, name: str, speaker: str, frozen: FrozenTestSet, commit: Callable[[], None]) -> dict:
    """Scores the new version, promotes it if it beats the active model, saves the registry and reports the status."""
    baseline = ensure_baseline(whisper, registry, speaker, frozen)
    entry = registry["versions"][name]
    record_version_scores(entry, *score_model(whisper, speaker, frozen, str(MODELS_ROOT / entry["path"])))
    promote, reason = should_promote(entry, baseline)
    kept = active_label(registry)
    entry["status"], entry["decision"] = ("promoted" if promote else "not_better"), reason
    if promote:
        registry["active"] = name
    save_registry(registry)
    commit()
    log.info("%s %s: %s", name, entry["status"], reason)
    summary = {"version": name, "metrics": entry["metrics"], "mean_wer": entry["mean_wer"], "baseline_mean_wer": baseline["mean_wer"], "reason": reason}
    if promote:
        try:
            summary["reload"] = notify_server(speaker)
        except MissingKey as error:
            summary["reload"] = str(error)
        status = write_status(speaker, "promoted", f"Your model v{entry['version']} is ready", **summary)
    else:
        status = write_status(speaker, "not_better", f"Not better yet; keeping {kept}", **summary)
    commit()
    return status
