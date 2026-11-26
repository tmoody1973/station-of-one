"""Run folders: each build writes its step outputs to data/runs/<hour_id>/."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

RUNS_ROOT = Path("data/runs")


def run_dir(hour_id: str, root: Path = RUNS_ROOT) -> Path:
    path = root / hour_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(run: Path, name: str) -> Any:
    return json.loads((run / name).read_text())


def write_json(run: Path, name: str, data: Any) -> Path:
    """Write atomically: a crash mid-write never leaves a half-written step output."""
    target = run / name
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, target)
    return target
