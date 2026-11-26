import json
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

from station.config import load_prefs
from station.steps.finish import checkpoint_command, finish, in_broadcast_hours
from station.steps.rundown import Rundown
from tests.test_page import newscast
from tests.test_publish import RecordingGateway
from tests.test_rundown import j

PREFS = load_prefs()
CT = ZoneInfo("America/Chicago")


def test_broadcast_hours_edges():
    at = lambda h, m: datetime(2026, 11, 27, h, m, tzinfo=CT)
    assert in_broadcast_hours(at(18, 59), PREFS)      # building the 7 pm newscast
    assert not in_broadcast_hours(at(19, 30), PREFS)  # would be 8 pm
    assert in_broadcast_hours(at(6, 48), PREFS)       # 7 am newscast
    assert not in_broadcast_hours(at(6, 29), PREFS)   # would be 6 am


def make_run(tmp_path):
    run = tmp_path / "2026-11-26T17"
    run.mkdir()
    (run / "newscast.json").write_text(json.dumps(newscast()))
    (run / "rundown.json").write_text(json.dumps(Rundown((j("a", 0.6),), {"a": 90}, None, (), (), True, False).to_dict()))
    (run / "run_log.json").write_text(json.dumps({"run_id": "x", "started_at": "2026-11-26T22:48:02+00:00", "steps": [
        {"name": "archive", "tool": "Box", "status": "done", "seconds": 2.3, "counts": {"bytes": 1725113}, "notes": []}]}))
    return run


def test_finish_rerenders_control_room_and_checkpoints(tmp_path):
    gw, ran = RecordingGateway(), []
    notes = finish(make_run(tmp_path), PREFS, gw, runner=lambda cmd, **kw: ran.append(cmd) or
                   subprocess.CompletedProcess(cmd, 0, "", ""), has_sprite_env=True)
    (method, provider, path, body, headers), = gw.puts
    assert (method, provider, path) == ("PUT", "tigris", "/patient-mountain-3400/control-room/index.html")
    assert b"Archive" in body and headers["Cache-Control"] == "max-age=60"  # archive row now on the public page
    assert ran == [checkpoint_command("2026-11-26T17")] and notes == ["Checkpoint saved."]


def test_finish_off_sprite_skips_checkpoint(tmp_path):
    notes = finish(make_run(tmp_path), PREFS, RecordingGateway(), runner=None, has_sprite_env=False)
    assert notes == ["No sprite-env here; checkpoint skipped."]
