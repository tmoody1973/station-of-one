import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from station import build as build_mod
from station.build import STEPS, acquire_lock, build, target_hour
from station.sprite import hold

CHI = ZoneInfo("America/Chicago")


def test_steps_in_spec_order():
    assert STEPS == ["scrape", "dedupe", "judge", "rundown", "write", "voice", "assemble", "story", "page", "publish", "archive", "finish", "radio"]


def test_target_hour_is_next_top_of_hour_from_48():
    assert target_hour(datetime(2026, 11, 27, 8, 48, tzinfo=CHI)) == datetime(2026, 11, 27, 9, 0, tzinfo=CHI)
    assert target_hour(datetime(2026, 11, 27, 9, 5, tzinfo=CHI)) == datetime(2026, 11, 27, 9, 0, tzinfo=CHI)


def test_lock_blocks_second_build(tmp_path):  # Review Focus 4
    lock = tmp_path / "build.lock"
    assert acquire_lock(lock) is True
    assert acquire_lock(lock) is False


def test_stale_lock_is_broken(tmp_path):
    lock = tmp_path / "build.lock"
    lock.write_text("123")
    old = time.time() - 1300
    os.utime(lock, (old, old))
    assert acquire_lock(lock, max_age_s=1200) is True


def fake_commands(calls, fail_at=None):
    def make(name):
        def cmd(run):
            calls.append(name)
            if name == "voice":
                (run / "voice.json").write_text(json.dumps({"paths": {"0": "a"}, "seconds": {}, "failed": [3]}))
            if name == fail_at:
                raise RuntimeError(f"{name} broke")
        return cmd
    return {n: make(n) for n in STEPS}


def test_build_survives_failed_story_chapter(tmp_path, monkeypatch):  # Review Focus 2
    calls = []
    monkeypatch.setattr(build_mod, "commands", lambda: fake_commands(calls))
    run = build(datetime(2026, 11, 27, 9, tzinfo=CHI), lock_path=tmp_path / "l", runs_root=tmp_path / "runs")
    assert calls == STEPS and run.name == "2026-11-27T09"
    assert json.loads((run / "voice.json").read_text())["failed"] == [3]
    assert not (tmp_path / "l").exists()


def test_failed_required_step_stops_and_logs(tmp_path, monkeypatch):
    calls, failures = [], []
    monkeypatch.setattr(build_mod, "commands", lambda: fake_commands(calls, fail_at="judge"))
    with pytest.raises(RuntimeError, match="judge broke"):
        build(datetime(2026, 11, 27, 9, tzinfo=CHI), lock_path=tmp_path / "l", runs_root=tmp_path / "runs",
              on_failure=lambda step, exc, run: failures.append(step) or False)
    assert calls == ["scrape", "dedupe", "judge"] and failures == ["judge"]
    assert not (tmp_path / "l").exists()


def test_on_failure_can_repair_and_continue(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(build_mod, "commands", lambda: fake_commands(calls, fail_at="dedupe"))
    build(datetime(2026, 11, 27, 9, tzinfo=CHI), lock_path=tmp_path / "l", runs_root=tmp_path / "runs",
          on_failure=lambda step, exc, run: True)
    assert calls == STEPS


def test_locked_build_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(build_mod, "commands", lambda: fake_commands([]))
    assert acquire_lock(tmp_path / "l")
    assert build(datetime(2026, 11, 27, 9, tzinfo=CHI), lock_path=tmp_path / "l", runs_root=tmp_path / "runs") is None


def test_hold_noop_without_socket(tmp_path):
    calls = []
    with hold("build", socket=tmp_path / "missing.sock", runner=lambda args: calls.append(args)):
        pass
    assert calls == []


def test_hold_sends_put_then_delete(tmp_path):
    sock = tmp_path / "api.sock"
    sock.write_text("")
    calls = []
    with hold("build", socket=sock, runner=lambda args: calls.append(args), interval_s=0.01):
        time.sleep(0.03)
    assert "PUT" in calls[0] and "http://sprite/v1/tasks/build" in calls[0]
    assert "DELETE" in calls[-1] and "http://sprite/v1/tasks/build" in calls[-1]


def test_rebuild_moves_old_run_log_aside(tmp_path, monkeypatch):  # 2 pm rebuild kept the morning's start time
    calls = []
    monkeypatch.setattr(build_mod, "commands", lambda: fake_commands(calls))
    run = tmp_path / "runs" / "2026-11-27T09"
    run.mkdir(parents=True)
    (run / "run_log.json").write_text('{"started_at": "old"}')
    build(datetime(2026, 11, 27, 9, tzinfo=CHI), lock_path=tmp_path / "l", runs_root=tmp_path / "runs")
    assert not (run / "run_log.json").exists() and (run / "run_log.prev.json").read_text() == '{"started_at": "old"}'


def test_hold_call_timeout_does_not_crash_build():
    # Nov 27: releasing the hold timed out after the 10 am newscast published and crashed the build.
    from station.sprite import _curl
    _curl(["sleep", "2"], timeout=0.1)  # must return, not raise
