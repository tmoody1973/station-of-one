"""Pairings (Rhythm Lab plan, Task 3): tracks Tarik played back to back, from the library's plays file.
A soft preference for the scheduler: it never overrides separation rules."""
from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from itertools import groupby
from pathlib import Path

PER_PAIR, CAP = 0.1, 0.3


def import_pairs(db: sqlite3.Connection, plays_csv: Path) -> int:
    """Rebuild library_pairs(a, b, count): consecutive tracks in the same show, hour and block. Guest-mix tracks
    and duplicate copies of a show are left out. Returns the number of distinct pairs."""
    rows = sorted((r for r in csv.DictReader(open(plays_csv, encoding="utf-8-sig")) if r["show_status"] == "counted"),
                  key=lambda r: (r["show_id"], int(r["position"])))
    counts: Counter = Counter()
    for _, run in groupby(rows, key=lambda r: (r["show_id"], r["hour"], r["block"])):
        run = list(run)
        for prev, nxt in zip(run, run[1:]):
            if not prev["segment"] and not nxt["segment"] and int(nxt["position"]) == int(prev["position"]) + 1:
                counts[(prev["track_id"], nxt["track_id"])] += 1
    db.execute("CREATE TABLE IF NOT EXISTS library_pairs (a TEXT, b TEXT, count INTEGER, PRIMARY KEY (a, b))")
    db.execute("DELETE FROM library_pairs")
    db.executemany("INSERT INTO library_pairs VALUES (?,?,?)", [(a, b, n) for (a, b), n in counts.items()])
    db.commit()
    return len(counts)


def pair_bonus(db: sqlite3.Connection, prev_track_id: str | None, track_id: str) -> float:
    if not prev_track_id:
        return 0.0
    strip = lambda t: t.removeprefix("lib:")
    row = db.execute("SELECT count FROM library_pairs WHERE a = ? AND b = ?", (strip(prev_track_id), strip(track_id))).fetchone()
    return round(min(CAP, PER_PAIR * row[0]), 2) if row else 0.0
