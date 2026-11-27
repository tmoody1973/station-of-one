"""A curator's library as a station's catalog (Rhythm Lab Radio, Tarik, Nov 27: the flagship station).

import_tracks loads the library's tracks CSV (one row per unique track, with play counts, rotation tiers and
version tags) into the Sprite's private database. match_library finds each track on Apple Music with the
same resolver the feeds use. The library itself never goes into the public repo or onto a public page.
"""
from __future__ import annotations

import csv
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from station.gateway import GatewayError
from station.radio.extract import Extracted
from station.radio.resolve import AppleRefused, resolve

SCHEMA = """
CREATE TABLE IF NOT EXISTS library_tracks (
  track_id TEXT PRIMARY KEY, artist TEXT, title TEXT, base_title TEXT, version TEXT, featuring TEXT, play_count INTEGER,
  tier TEXT, first_played TEXT, last_played TEXT, hour1_plays INTEGER, hour2_plays INTEGER, opener_count INTEGER,
  closer_count INTEGER, special_tags TEXT, in_segment INTEGER, album TEXT, label TEXT,
  match_status TEXT, apple_music_id TEXT, isrc TEXT, match_confidence REAL, apple_url TEXT, preview_url TEXT,
  artwork_url TEXT, duration_ms INTEGER, release_date TEXT, matched_artist TEXT, matched_title TEXT, matched_album TEXT);
"""


def _int(v) -> int:
    try:
        return int(v or 0)
    except ValueError:
        return 0


def import_tracks(db: sqlite3.Connection, path: Path) -> int:
    db.executescript(SCHEMA)
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))  # the export starts with a byte-order mark
    for r in rows:
        db.execute("INSERT INTO library_tracks (track_id, artist, title, base_title, version, featuring, play_count, tier, "
                   "first_played, last_played, hour1_plays, hour2_plays, opener_count, closer_count, special_tags, in_segment, "
                   "album, label) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(track_id) DO UPDATE SET "
                   "play_count = excluded.play_count, tier = excluded.tier, last_played = excluded.last_played",
                   (r["track_id"], r["artist"], r["title"], r["base_title"] or r["title"], r["version"], r["featuring"],
                    _int(r["play_count"]), r["rotation_tier"], r["first_played"], r["last_played"], _int(r["hour1_plays"]),
                    _int(r["hour2_plays"]), _int(r["hour_opener_count"]), _int(r["show_closer_count"]), r["special_tags"],
                    1 if r["segments"] else 0, r["album"], r["label"]))
    db.commit()
    return len(rows)


def to_match(db: sqlite3.Connection, min_plays: int = 2, include_segments: bool = False, limit: int = 100000) -> list[tuple]:
    seg = "" if include_segments else "AND in_segment = 0 "
    return db.execute("SELECT track_id, artist, base_title, version, album, label FROM library_tracks "
                      f"WHERE play_count >= ? {seg}AND match_status IS NULL ORDER BY play_count DESC, track_id LIMIT ?",
                      (min_plays, limit)).fetchall()


def match_library(gw, conn: str, storefront: str, db: sqlite3.Connection, min_plays: int = 2, workers: int = 4,
                  limit: int = 100000, progress=None) -> dict[str, int]:
    todo = to_match(db, min_plays, limit=limit)

    def look(row):
        track_id, artist, base_title, version, album, label = row
        want = Extracted("track", artist, base_title, album or "", label or "", None, version or "")
        try:
            return track_id, resolve(gw, conn, want, storefront)
        except GatewayError as e:
            return track_id, ([], f"error {e.status}")

    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:  # lookups in parallel, writes on this thread
        for i, (track_id, (matches, status)) in enumerate(pool.map(look, todo), 1):
            if status.startswith("error"):
                counts["error"] = counts.get("error", 0) + 1
                continue  # left unmatched: retried on the next run
            counts[status] = counts.get(status, 0) + 1
            m = matches[0] if matches else None
            db.execute("UPDATE library_tracks SET match_status = ?, apple_music_id = ?, isrc = ?, match_confidence = ?, apple_url = ?, "
                       "preview_url = ?, artwork_url = ?, duration_ms = ?, release_date = ?, matched_artist = ?, matched_title = ?, "
                       "matched_album = ? WHERE track_id = ?",
                       (status, *(m and (m.song_id, m.isrc, m.confidence, m.apple_url, m.preview_url, m.artwork_url, m.duration_ms,
                                         m.release_date, m.artist, m.title, m.album) or (None,) * 11), track_id))
            if i % 50 == 0:
                db.commit()
                if progress:
                    progress(i, len(todo), counts)
    db.commit()
    return counts


REPORT_FIELDS = ("track_id", "artist", "title", "version", "play_count", "tier", "match_status", "matched_artist",
                 "matched_title", "match_confidence")


def held_report(db: sqlite3.Connection, path: Path) -> int:
    """Tracks the station can't program yet (held: a doubtful match; not_on_apple), for Tarik to check by hand.
    Private: written to the Sprite's data/ only, never published or committed."""
    rows = db.execute(f"SELECT {', '.join(REPORT_FIELDS)} FROM library_tracks WHERE match_status IN ('held', 'not_on_apple') "
                      "AND in_segment = 0 ORDER BY play_count DESC, track_id").fetchall()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(REPORT_FIELDS)
        w.writerows(rows)
    return len(rows)


__all__ = ["import_tracks", "to_match", "match_library", "held_report", "AppleRefused"]
