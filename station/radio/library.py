"""A curator's library as a station's catalog (Rhythm Lab Radio, Tarik, Nov 27: the flagship station).

import_tracks loads the library's tracks CSV (one row per unique track, with play counts, rotation tiers and
version tags) into the Sprite's private database. match_library finds each track on Apple Music with the
same resolver the feeds use. The library itself never goes into the public repo or onto a public page.
"""
from __future__ import annotations

import csv
import sqlite3
from datetime import UTC, datetime
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


def library_energy(h1: int, h2: int) -> int:
    """Energy from Tarik's own placement: hour 2 of the show leans uptempo. No hour data is mid (2)."""
    total = (h1 or 0) + (h2 or 0)
    if not total:
        return 2
    share = (h2 or 0) / total
    return 3 if share >= 0.65 else 1 if share <= 0.35 else 2


def _category(tier: str, last_played: str) -> str:
    if tier == "core":
        return "P"
    if tier == "rotation":
        return "M"
    if tier == "repeat" and (last_played or "") >= "2023":
        return "R"
    return "G"  # older repeats and matched single spins


def _note(first_played: str) -> str:
    try:
        return f"First aired on Rhythm Lab Radio, {datetime.strptime(first_played, '%Y-%m-%d'):%b %Y}"
    except (TypeError, ValueError):
        return "First aired on Rhythm Lab Radio"


def seed_rotation(db: sqlite3.Connection, station) -> dict[str, int]:
    """Matched, non-guest-mix library tracks into the station's rotation (and the song pool the scheduler reads).
    Safe to run again: existing rows keep their plays and last-played time."""
    rows = db.execute("SELECT track_id, tier, first_played, last_played, hour1_plays, hour2_plays, opener_count, closer_count, "
                      "apple_music_id, isrc, match_confidence, apple_url, preview_url, artwork_url, duration_ms, release_date, "
                      "matched_artist, matched_title, matched_album, version, special_tags FROM library_tracks "
                      "WHERE match_status = 'resolved' AND in_segment = 0").fetchall()
    counts: dict[str, int] = {}
    now = datetime.now(UTC).isoformat()
    for (tid, tier, first, last, h1, h2, opens, closes, song_id, isrc, conf, apple_url, preview, art, dur, released,
         artist, title, album, version, tags) in rows:
        cid = f"lib:{tid}"
        db.execute("INSERT INTO candidates (id, kind, artist, title, version, status, song_id, match_confidence, apple_url, "
                   "preview_url, artwork_url, duration_ms, isrc, release_date, album, matched_artist, matched_title, resolved_at) "
                   "VALUES (?, 'track', ?, ?, ?, 'resolved', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                   "song_id = excluded.song_id, apple_url = excluded.apple_url, preview_url = excluded.preview_url, "
                   "duration_ms = excluded.duration_ms",
                   (cid, artist, title, version or "", song_id, conf, apple_url, preview, art, dur, isrc, released, album,
                    artist, title, now))
        cat = _category(tier, last)  # the starting category only: once a song is in, the music meeting owns it
        db.execute("INSERT INTO rotation (station_id, candidate_id, category, energy, added_at, opener, closer, source_note, tags) "
                   "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(station_id, candidate_id) DO UPDATE SET energy = excluded.energy, "
                   "opener = excluded.opener, closer = excluded.closer, source_note = excluded.source_note, tags = excluded.tags",
                   (station.id, cid, cat, library_energy(h1, h2), now, int((opens or 0) > 0), int((closes or 0) > 0), _note(first),
                    tags or ""))
        counts[cat] = counts.get(cat, 0) + 1
    db.commit()
    return counts


def library_track(db: sqlite3.Connection, candidate_id: str, today) -> dict:
    """A library song as pages and the queue show it: the track, the Apple links and "First aired on ...".
    No show notes, no Drive links (the library stays private), so source_url is empty."""
    from station.radio.program import era
    r = db.execute("SELECT c.id, c.song_id, c.matched_artist, c.matched_title, c.album, c.release_date, c.duration_ms, "
                   "c.preview_url, c.apple_url, c.artwork_url, ro.source_note FROM rotation ro JOIN candidates c ON c.id = ro.candidate_id "
                   "WHERE ro.candidate_id = ?", (candidate_id,)).fetchone()
    return {"candidate_id": r[0], "song_id": r[1], "artist": r[2], "title": r[3], "album": r[4], "release_date": r[5],
            "duration_ms": r[6], "preview_url": r[7], "apple_url": r[8], "artwork_url": r[9], "fit": None,
            "note": r[10] or "", "source_url": "", "era": era(r[5], today)}


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


__all__ = ["import_tracks", "to_match", "match_library", "held_report", "library_energy", "library_track", "seed_rotation", "AppleRefused"]
