"""One newscast build: every step in spec order, one lock, one Sprite hold.

Each step is the same function the CLI runs by hand, so a build is exactly the hand steps
in a row. A failing step goes to on_failure (the station manager, Task 17); if that returns
True the build continues, otherwise the error stops the build.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from station.runs import RUNS_ROOT
from station.sprite import hold

STEPS = ["scrape", "dedupe", "judge", "rundown", "write", "voice", "assemble", "page", "publish", "archive", "finish"]
LOCK = Path("data/build.lock")
STALE_LOCK_S = 1200


def commands() -> dict[str, Callable[[Path], None]]:
    from station.__main__ import COMMANDS

    return COMMANDS


def target_hour(now_local: datetime) -> datetime:
    """A build started at :30 or later is for the next top of the hour."""
    top = now_local.replace(minute=0, second=0, microsecond=0)
    return top + timedelta(hours=1) if now_local.minute >= 30 else top


def acquire_lock(path: Path = LOCK, max_age_s: int = STALE_LOCK_S) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time():.0f}".encode())
            os.close(fd)
            return True
        except FileExistsError:
            if time.time() - path.stat().st_mtime < max_age_s:
                return False
            path.unlink(missing_ok=True)  # stale: a crashed build left it
    return False


def _log_failure(step: str, exc: Exception, run: Path) -> bool:
    return False  # Task 17 replaces this with the station manager


def build(hour_local: datetime, steps: list[str] | None = None, lock_path: Path = LOCK,
          runs_root: Path = RUNS_ROOT, on_failure: Callable[[str, Exception, Path], bool] = _log_failure) -> Path | None:
    if not acquire_lock(lock_path):
        return None
    run = runs_root / hour_local.strftime("%Y-%m-%dT%H")
    run.mkdir(parents=True, exist_ok=True)
    if (run / "run_log.json").exists():  # a rebuild of this hour starts a fresh log (start time, steps)
        (run / "run_log.json").replace(run / "run_log.prev.json")
    cmds = commands()
    try:
        with hold("build"):
            for name in steps or STEPS:
                try:
                    cmds[name](run)
                except Exception as exc:
                    if not on_failure(name, exc, run):
                        raise
        return run
    finally:
        lock_path.unlink(missing_ok=True)
