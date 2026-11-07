"""Reading the team's clips.csv (spec 12.3): their columns and ids unchanged, audio found in the team folder layout."""

from voice.clips.records import ClipRecord
from voice.clips.team_import import copy_results, find_audio, read_team_rows

CSV = (
    "id,speaker,text,file,split,condition,ok,notes\n"
    "P1_r001,P1,We talked of the side show in the circus.,practice/P1_r001.m4a,train,quiet,yes,Harvard list 7 #1\n"
    'P1_t08,P1,"It snowed, rained, and hailed the same morning.",practice/P1_t08.m4a,test,quiet,no,retake needed\n'
    "S1_t01,S1,The birch canoe slid on the smooth planks.,raw/S1_t01.m4a,test,noisy,yes,\n"
)


def test_rows_keep_team_ids_split_condition_and_ok(tmp_path):
    (tmp_path / "clips.csv").write_text(CSV, encoding="utf-8")
    rows = read_team_rows(tmp_path / "clips.csv", "P1")
    assert [row["id"] for row in rows] == ["P1_r001", "P1_t08"]
    record = ClipRecord(**rows[1], source="import", trust="read")
    assert (record.text, record.split, record.condition, record.ok) == ("It snowed, rained, and hailed the same morning.", "test", "quiet", False)


def test_audio_is_found_by_relative_path_then_by_name_in_the_volume_folders(tmp_path):
    (tmp_path / "practice").mkdir()
    (tmp_path / "incoming").mkdir()
    (tmp_path / "practice" / "P1_r001.m4a").write_bytes(b"x")
    (tmp_path / "incoming" / "P1_t08.m4a").write_bytes(b"x")
    search = [tmp_path / "incoming", tmp_path / "wav"]
    assert find_audio("practice/P1_r001.m4a", tmp_path, search) == tmp_path / "practice" / "P1_r001.m4a"
    assert find_audio("practice/P1_t08.m4a", tmp_path, search) == tmp_path / "incoming" / "P1_t08.m4a"
    assert find_audio("practice/P1_t09.m4a", tmp_path, search) is None


def test_listener_and_test_log_results_are_copied_to_eval(tmp_path, monkeypatch):
    import voice.storage as storage

    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path / "data")
    results = tmp_path / "results"
    results.mkdir()
    for name in ("listeners.csv", "test_log.csv", "notes.txt"):
        (results / name).write_text("id\n", encoding="utf-8")
    assert copy_results(results, "S1") == ["listeners.csv", "test_log.csv"]
    assert (tmp_path / "data" / "S1" / "eval" / "listeners.csv").is_file()
