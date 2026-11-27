"""Buzz (plan B1, Task 3): how many of a station's feed items in a window mention an artist. A signal the
music meeting gives Jev; seed-list items are the station's own list, so they don't count."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from station.radio.model import normalize
from station.radio.seeds import SEED_FEED


def buzz(db: sqlite3.Connection, station_id: str, artist: str, since: datetime) -> int:
    name = f" {normalize(artist)} "
    if not name.strip():
        return 0
    rows = db.execute("SELECT title, excerpt FROM feed_items WHERE station_id = ? AND feed != ? AND seen_at >= ?",
                      (station_id, SEED_FEED, since.isoformat())).fetchall()
    return sum(1 for title, excerpt in rows if name in f" {normalize(f'{title} {excerpt}')} ")  # whole words only
