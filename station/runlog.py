"""Per-build run log: step, tool, counts, seconds, status. The control room reads it."""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from station.runs import write_json


@dataclass
class StepRecord:
    name: str
    tool: str
    status: str = "running"
    seconds: float = 0.0
    counts: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class RunLog:
    def __init__(self, path: Path, run_id: str):
        self.path = Path(path)
        self.run_id = run_id
        self.started_at = datetime.now(UTC).isoformat()
        self._t0 = time.monotonic()
        self.steps: list[StepRecord] = []

    @contextmanager
    def step(self, name: str, tool: str):
        rec = StepRecord(name, tool)
        self.steps.append(rec)
        t = time.monotonic()
        try:
            yield rec
            if rec.status == "running":
                rec.status = "done"
        except BaseException as e:
            rec.status = "failed"
            rec.notes.append(f"{type(e).__name__}: {e}")
            raise
        finally:
            rec.seconds = round(time.monotonic() - t, 2)
            self.save()

    def save(self) -> None:
        write_json(self.path.parent, self.path.name, {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "total_seconds": round(time.monotonic() - self._t0, 2),
            "steps": [vars(s) for s in self.steps],
        })
