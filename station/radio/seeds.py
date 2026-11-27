"""Seed tracks (plan 2026-11-27-music-station-a, Task 8 addendum; PRD "Catalog-era stations": the seed list
carries the core). Decided by Tarik on Nov 27 after the first live run: the UK jazz feeds mostly surface
classic American jazz, so 2 of 61 finds fit the brief.

For each seed artist with fewer than MIN_UNUSED unscheduled tracks in the pool, Apple Music search gives
up to PER_ARTIST new songs by that artist. They enter the pool already matched; Jev still rates their fit.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from urllib.parse import quote

from station.gateway import GatewayError
from station.radio.extract import Extracted
from station.radio.model import StationConfig, candidate_id, normalize
from station.radio.poll import FeedItem
from station.radio.resolve import AppleRefused, _get, _match, has_version

SEED_FEED = "the station's seed list"
MIN_UNUSED = 2
PER_ARTIST = 3


def _unused(db: sqlite3.Connection, station_id: str, artist: str) -> int:
    rows = db.execute("SELECT c.matched_artist FROM candidates c JOIN station_candidates sc ON sc.candidate_id = c.id "
                      "WHERE sc.station_id = ? AND sc.scheduled_at IS NULL AND c.status = 'resolved'", (station_id,)).fetchall()
    return sum(1 for (a,) in rows if normalize(a or "").startswith(normalize(artist)))


def seed_candidates(gw, station: StationConfig, db: sqlite3.Connection, now: datetime
                    ) -> tuple[list[tuple[str, Extracted, FeedItem]], list[str]]:
    out: list[tuple[str, Extracted, FeedItem]] = []
    notes: list[str] = []
    for artist in station.seeds.get("artists", []):
        if _unused(db, station.id, artist) >= MIN_UNUSED:
            continue
        try:
            songs = _get(gw, station.apple_connection,
                         f"/v1/catalog/{station.storefront}/search?term={quote(artist)}&types=songs&limit=15") \
                .get("results", {}).get("songs", {}).get("data", [])
        except AppleRefused as e:
            notes.append(str(e))
            break
        except GatewayError as e:
            notes.append(f"seed lookup failed for {artist}: {e.status}")
            continue
        mine = [s for s in songs if normalize(s.get("attributes", {}).get("artistName", "")).startswith(normalize(artist))
                and not has_version(s.get("attributes", {}).get("name", ""))]  # originals only (review I3)
        item = FeedItem(hashlib.sha1(f"seed|{station.id}|{artist}".encode()).hexdigest()[:16], SEED_FEED, f"seed:{artist}",
                        f"{artist}, a core artist of this station", "", "",  # each track links to its own Apple page
                        station.brief)
        added = 0
        for s in mine:
            m = _match(s, 1.0)
            cid = candidate_id(m.artist, m.title, "")
            if added == PER_ARTIST or db.execute("SELECT 1 FROM candidates WHERE id = ?", (cid,)).fetchone():
                continue
            db.execute("INSERT OR IGNORE INTO feed_items (id, station_id, feed, guid, title, link, published_at, excerpt, seen_at, extracted_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)", (item.id, station.id, item.feed, item.guid, item.title, item.link, "",
                                                        item.excerpt, now.isoformat(), now.isoformat()))
            year = int(m.release_date[:4]) if m.release_date[:4].isdigit() else None
            db.execute("INSERT INTO candidates (id, feed_item_id, kind, artist, title, release, year, status, song_id, match_confidence, "
                       "apple_url, preview_url, artwork_url, duration_ms, isrc, release_date, album, matched_artist, matched_title, resolved_at) "
                       "VALUES (?,?,'track',?,?,?,?,'resolved',?,1.0,?,?,?,?,?,?,?,?,?,?)",
                       (cid, item.id, m.artist, m.title, m.album, year, m.song_id, m.apple_url, m.preview_url, m.artwork_url,
                        m.duration_ms, m.isrc, m.release_date, m.album, m.artist, m.title, now.isoformat()))
            out.append((cid, Extracted("track", m.artist, m.title, m.album, "", year, ""), item))
            added += 1
    db.commit()
    return out, notes
