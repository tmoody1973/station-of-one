import json
import subprocess

from station import manager
from station.manager import FALLBACKS, ask_manager, claude_command, on_failure, prompt
from station.runlog import RunLog


def reply(text):
    return lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"result": text}), "")


def test_prompt_lists_options_and_error(tmp_path):
    p = prompt("dedupe", "KeyError: 'url'", tmp_path)
    assert "KeyError: 'url'" in p and '"retry"' in p and '"skip"' in p and "one sentence" in p


def test_claude_command_has_no_tools():
    cmd = claude_command("hi")
    assert cmd[:2] == ["claude", "-p"] and cmd[cmd.index("--tools") + 1] == "" and "--max-turns" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"


def test_parses_action_and_note():
    d = ask_manager("dedupe", "p", runner=reply('Sure. {"action": "skip", "note": "Dedupe failed, so every post stood alone."}'),
                    base_url="https://gw")
    assert (d.action, d.note) == ("skip", "Dedupe failed, so every post stood alone.")


def test_unknown_action_falls_back_to_first_option():
    d = ask_manager("dedupe", "p", runner=reply('{"action": "delete everything", "note": "x"}'), base_url="https://gw")
    assert d.action == FALLBACKS["dedupe"][0]


def test_manager_timeout_does_not_block_build():
    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 60)
    d = ask_manager("scrape", "p", runner=boom, base_url="https://gw")
    assert d.action == "retry" and "unavailable" in d.note


def _failed_log(run, step):
    log = RunLog(run / "run_log.json", run_id=run.name)
    try:
        with log.step(step, "Code"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass


def test_retry_success_marks_step_repaired_with_note(tmp_path, monkeypatch):
    _failed_log(tmp_path, "page")
    monkeypatch.setattr(manager, "ask_manager", lambda step, p, **kw: manager.ManagerDecision("retry", "Retried the page build once."))

    def fake_page(run):
        with RunLog.open(run / "run_log.json", run_id=run.name).step("page", "Code"):
            pass
    monkeypatch.setattr(manager, "commands", lambda: {"page": fake_page})
    assert on_failure("page", RuntimeError("boom"), tmp_path) is True
    step = json.loads((tmp_path / "run_log.json").read_text())["steps"][-1]
    assert step["status"] == "repaired" and "Retried the page build once." in step["notes"]


def test_retry_that_fails_again_stops_the_build(tmp_path, monkeypatch):
    _failed_log(tmp_path, "judge")
    monkeypatch.setattr(manager, "ask_manager", lambda step, p, **kw: manager.ManagerDecision("retry", "Retried."))

    def still_broken(run):
        raise RuntimeError("still broken")
    monkeypatch.setattr(manager, "commands", lambda: {"judge": still_broken})
    assert on_failure("judge", RuntimeError("boom"), tmp_path) is False
    step = json.loads((tmp_path / "run_log.json").read_text())["steps"][-1]
    assert step["status"] == "failed" and any("Retried." in n and "still broken" in n for n in step["notes"])


def test_skip_dedupe_writes_singleton_clusters(tmp_path, monkeypatch):
    _failed_log(tmp_path, "dedupe")
    (tmp_path / "posts.json").write_text(json.dumps([{"id": "a"}, {"id": "b"}]))
    monkeypatch.setattr(manager, "ask_manager", lambda step, p, **kw: manager.ManagerDecision("skip", "Skipped dedupe."))
    assert on_failure("dedupe", RuntimeError("boom"), tmp_path) is True
    clusters = json.loads((tmp_path / "clusters.json").read_text())
    assert clusters == {"clusters": [{"primary_id": "a", "member_ids": ["a"]}, {"primary_id": "b", "member_ids": ["b"]}],
                        "candidates": []}
    assert json.loads((tmp_path / "run_log.json").read_text())["steps"][-1]["status"] == "repaired"
