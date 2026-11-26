"""Step 11, finish: bring the public control room up to date, then checkpoint the Sprite.

Runs last because the checkpoint may pause running processes (docs disagree; research notes §2).
sprite-env has no delete subcommand (checked 2026-11-26), so old checkpoints are not pruned here.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, time
from pathlib import Path

from station.build import target_hour
from station.config import Prefs
from station.steps.page import write_control_room
from station.steps.publish import CONTENT_TYPES, cache_control, put_object


def in_broadcast_hours(now_local: datetime, prefs: Prefs) -> bool:
    hour = target_hour(now_local).time()
    first, last = (time.fromisoformat(t) for t in (prefs.station.first_newscast, prefs.station.last_newscast))
    return first <= hour <= last


def checkpoint_command(run_id: str) -> list[str]:
    return ["sprite-env", "checkpoints", "create", "--comment", f"build {run_id}"]


def finish(run: Path, prefs: Prefs, gw, runner=subprocess.run, has_sprite_env: bool | None = None) -> list[str]:
    newscast = json.loads((run / "newscast.json").read_text())
    (page,) = write_control_room(run, prefs, newscast)  # now includes the publish and archive rows
    key = "control-room/index.html"
    put_object(gw, prefs.hosting.bucket, key, page.read_bytes(), CONTENT_TYPES[".html"], cache_control(key))
    if has_sprite_env is None:
        has_sprite_env = shutil.which("sprite-env") is not None
    if not has_sprite_env:
        return ["No sprite-env here; checkpoint skipped."]
    runner(checkpoint_command(run.name), check=True, capture_output=True, text=True, timeout=120)
    return ["Checkpoint saved."]
