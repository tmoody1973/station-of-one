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


def test_runlog_appends_to_existing_file(tmp_path):  # steps run one CLI call at a time
    with RunLog(tmp_path / "run_log.json", run_id="x").step("scrape", "Apify"):
        pass
    with RunLog.open(tmp_path / "run_log.json", run_id="x").step("judge", "TypeSafe Jev"):
        pass
    names = [s["name"] for s in json.loads((tmp_path / "run_log.json").read_text())["steps"]]
    assert names == ["scrape", "judge"]


def test_rerun_step_replaces_its_entry(tmp_path):  # control room showed "Build the page" twice
    with RunLog(tmp_path / "run_log.json", run_id="x").step("page", "Code"):
        pass
    with RunLog.open(tmp_path / "run_log.json", run_id="x").step("page", "Code"):
        pass
    assert [s["name"] for s in json.loads((tmp_path / "run_log.json").read_text())["steps"]] == ["page"]


def test_total_seconds_is_sum_of_steps(tmp_path):  # control room showed build time 0:00
    log = RunLog(tmp_path / "run_log.json", run_id="x")
    log.steps = []
    from station.runlog import StepRecord
    log.steps += [StepRecord("scrape", "Apify", "done", 90.0), StepRecord("voice", "Gemini TTS", "done", 22.5)]
    log.save()
    assert json.loads((tmp_path / "run_log.json").read_text())["total_seconds"] == 112.5
