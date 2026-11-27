"""Programmer (plan 2026-11-27-music-station-a, Task 7; PRD "Station model": era_mix, flow).

Builds a block from matched candidates Jev rated a fit (>= FIT_MIN): highest fit first, each pick taken
from the era (new <= 1 year, recent <= 10 years, older) furthest below its era_mix share, no artist
twice within flow.artist_gap_hours, until flow.block_minutes are filled. Picked tracks are marked scheduled.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from station.radio.model import StationConfig, normalize

FIT_MIN = 0.5
ERAS = ("new", "recent", "older")


@dataclass
class Block:
    station_id: str
    block_id: str
    built_at: str
    tracks: list[dict] = field(default_factory=list)


def era(release_date: str, today: date) -> str:
    try:
        age = (today - date.fromisoformat((release_date or "")[:10])).days
    except ValueError:
        return "older"
    return "new" if age <= 365 else "recent" if age <= 3650 else "older"


def _recent_artists(db: sqlite3.Connection, station_id: str, since: datetime) -> set[str]:
    rows = db.execute("SELECT c.matched_artist FROM station_candidates sc JOIN candidates c ON c.id = sc.candidate_id "
                      "WHERE sc.station_id = ? AND sc.scheduled_at >= ?", (station_id, since.isoformat())).fetchall()
    return {normalize(r[0]) for r in rows}


def program_block(station: StationConfig, db: sqlite3.Connection, now: datetime, mark: bool = True) -> Block:
    rows = db.execute(
        "SELECT c.id, c.song_id, c.matched_artist, c.matched_title, c.album, c.release_date, c.duration_ms, c.preview_url, "
        "c.apple_url, c.artwork_url, sc.fit_score, fi.feed, fi.title, fi.link FROM station_candidates sc "
        "JOIN candidates c ON c.id = sc.candidate_id JOIN feed_items fi ON fi.id = c.feed_item_id "
        "WHERE sc.station_id = ? AND sc.scheduled_at IS NULL AND c.status = 'resolved' AND sc.fit_score >= ? "
        "AND c.duration_ms > 0 ORDER BY sc.fit_score DESC, c.id", (station.id, FIT_MIN)).fetchall()
    pools: dict[str, list[dict]] = {e: [] for e in ERAS}
    for r in rows:
        t = {"candidate_id": r[0], "song_id": r[1], "artist": r[2], "title": r[3], "album": r[4], "release_date": r[5],
             "duration_ms": r[6], "preview_url": r[7], "apple_url": r[8], "artwork_url": r[9], "fit": r[10],
             "note": f"Found in {r[11]}: {r[12]}", "source_url": r[13] or r[8], "era": era(r[5], now.date())}
        pools[t["era"]].append(t)
    used = _recent_artists(db, station.id, now - timedelta(hours=station.flow.get("artist_gap_hours", 3)))
    target = station.flow.get("block_minutes", 50) * 60000
    tracks: list[dict] = []
    total = 0
    while total < target:
        for e in ERAS:
            pools[e] = [t for t in pools[e] if normalize(t["artist"]) not in used]
        open_eras = [e for e in ERAS if pools[e]]
        if not open_eras:
            break
        share = {e: (sum(1 for t in tracks if t["era"] == e) / len(tracks)) if tracks else 0.0 for e in ERAS}
        pick_era = max(open_eras, key=lambda e: (station.era_mix.get(e, 0) - share[e], station.era_mix.get(e, 0)))
        t = pools[pick_era].pop(0)
        tracks.append(t)
        used.add(normalize(t["artist"]))
        total += t["duration_ms"]
    block = Block(station.id, f"{station.id}-{now:%Y%m%dT%H%M}", now.isoformat(), tracks)
    if mark:
        mark_scheduled(db, block, now)
    return block


def mark_scheduled(db: sqlite3.Connection, block: Block, now: datetime) -> None:
    db.executemany("UPDATE station_candidates SET scheduled_at = ? WHERE station_id = ? AND candidate_id = ?",
                   [(now.isoformat(), block.station_id, t["candidate_id"]) for t in block.tracks])
    db.commit()
