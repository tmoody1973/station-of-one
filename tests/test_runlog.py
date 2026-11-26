import json

import pytest

from station.runlog import RunLog


def test_runlog_records_seconds_and_counts(tmp_path):
    log = RunLog(tmp_path / "run_log.json", run_id="2026-11-27T09")
    with log.step("scrape", "Apify") as s:
        s.counts["posts"] = 164
    data = json.loads((tmp_path / "run_log.json").read_text())
    step = data["steps"][0]
    assert (step["name"], step["tool"], step["status"], step["counts"]) == ("scrape", "Apify", "done", {"posts": 164})
    assert step["seconds"] >= 0 and data["run_id"] == "2026-11-27T09"


def test_runlog_marks_failed_step_and_reraises(tmp_path):
    log = RunLog(tmp_path / "run_log.json", run_id="x")
    with pytest.raises(RuntimeError):
        with log.step("voice", "Gemini TTS"):
            raise RuntimeError("boom")
    step = json.loads((tmp_path / "run_log.json").read_text())["steps"][0]
    assert step["status"] == "failed" and "boom" in step["notes"][0]


def test_runlog_repaired_status_kept(tmp_path):
    log = RunLog(tmp_path / "run_log.json", run_id="x")
    with log.step("scrape", "Apify") as s:
        s.status = "repaired"
        s.notes.append("Retried once, then used the source's RSS feed.")
    assert json.loads((tmp_path / "run_log.json").read_text())["steps"][0]["status"] == "repaired"
