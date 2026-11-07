"""Imports the team's recordings: their clips.csv rows and audio become our clip records."""

import csv
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from voice.clips.convert import convert_to_clip
from voice.clips.records import ClipRecord, audio_path, load_clips, save_clip
from voice.storage import speaker_dir

TEAM_COLUMNS = ("id", "speaker", "text", "file", "split", "condition", "ok", "notes")
# Result files the Data teammate produces, kept for the Results screen (listeners, Akoli, test logs).
RESULT_PATTERNS = ("listeners*.csv", "test_log*", "akoli*.csv")


@dataclass
class ImportReport:
    """What one import did."""

    imported: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    missing_audio: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    results_copied: list[str] = field(default_factory=list)


def read_team_rows(csv_path: Path, speaker: str) -> list[dict]:
    """The CSV's rows for this speaker, with the team's eight columns only."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [{column: (row.get(column) or "").strip() for column in TEAM_COLUMNS} for row in csv.DictReader(handle)]
    return [row for row in rows if row["id"] and row["speaker"] == speaker]


def find_audio(file_field: str, root: Path, search_dirs: list[Path]) -> Path | None:
    """The row's audio: its path relative to the team folder, else its file name in any search folder."""
    candidates = [root / file_field] + [folder / Path(file_field).name for folder in search_dirs]
    return next((path for path in candidates if file_field and path.is_file()), None)


def import_row(row: dict, source: Path, existing: ClipRecord | None) -> bool:
    """Copies the original to raw/, converts it, and appends the record if anything changed. True if appended."""
    speaker = row["speaker"]
    raw = speaker_dir(speaker) / "raw" / source.name
    raw.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != raw.resolve():
        shutil.copy2(source, raw)
    duration = convert_to_clip(raw, audio_path(speaker, row["id"]))
    record = ClipRecord(**{**row, "file": source.name}, source="import", trust="read", duration_s=duration)
    if existing is not None:
        # Keep what the app decided about this clip (exclusion) and when it first arrived.
        record.excluded, record.created_at = existing.excluded, existing.created_at
        if record.model_dump(exclude={"duration_s"}) == existing.model_dump(exclude={"duration_s"}):
            return False
    save_clip(record)
    return True


def copy_results(results_dir: Path, speaker: str) -> list[str]:
    """Copies listener, Akoli and test-log files into the speaker's eval folder."""
    if not results_dir.is_dir():
        return []
    eval_dir = speaker_dir(speaker) / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    copied = sorted({path for pattern in RESULT_PATTERNS for path in results_dir.glob(pattern) if path.is_file()})
    for path in copied:
        shutil.copy2(path, eval_dir / path.name)
    return [path.name for path in copied]


def import_team_folder(speaker: str, root: Path, search_dirs: list[Path]) -> ImportReport:
    """Imports every row of `root/clips.csv` for the speaker, team ids, split, condition and ok unchanged."""
    report = ImportReport()
    existing = load_clips(speaker)
    for row in read_team_rows(root / "clips.csv", speaker):
        source = find_audio(row["file"], root, search_dirs)
        if source is None:
            report.missing_audio.append(row["id"])
            continue
        try:
            appended = import_row(row, source, existing.get(row["id"]))
        except ValueError as error:
            report.failed[row["id"]] = str(error)
            continue
        (report.imported if appended else report.unchanged).append(row["id"])
    report.results_copied = copy_results(root / "results", speaker)
    return report
