"""The new-release scout (jazz station plan, Task 4): new albums from the artists a station already plays.

For each artist, Apple Music's catalog gives the artist's latest release; anything out in the last 60 days that this
station hasn't scouted becomes candidates, entered like the seed list's (already matched on Apple Music). Jev then
rates their fit with every other find, and the music meeting decides adds and, for a styled station, the style.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import quote

from station.gateway import GatewayError
from station.radio.extract import Extracted
from station.radio.model import StationConfig, candidate_id, normalize
from station.radio.poll import FeedItem
from station.radio.resolve import AppleRefused, _get, _match, has_version

SCOUT_FEED = "Apple Music new releases"
RECENT_DAYS = 60
SCHEMA = """
CREATE TABLE IF NOT EXISTS apple_artists (name TEXT PRIMARY KEY, artist_id TEXT, checked_at TEXT);
CREATE TABLE IF NOT EXISTS scouted_albums (station_id TEXT, album_id TEXT, seen_at TEXT, PRIMARY KEY (station_id, album_id));
"""


def _artist_id(gw, station: StationConfig, db: sqlite3.Connection, name: str, now: datetime) -> str | None:
    """Apple's id for an artist, looked up once and cached ("" when Apple has no artist by exactly that name)."""
    key = normalize(name)
    row = db.execute("SELECT artist_id FROM apple_artists WHERE name = ?", (key,)).fetchone()
    if row:
        return row[0] or None
    hits = _get(gw, station.apple_connection, f"/v1/catalog/{station.storefront}/search?term={quote(name)}&types=artists&limit=1") \
        .get("results", {}).get("artists", {}).get("data", [])
    aid = hits[0]["id"] if hits and normalize(hits[0].get("attributes", {}).get("name", "")) == key else ""
    db.execute("INSERT OR REPLACE INTO apple_artists VALUES (?,?,?)", (key, aid, now.isoformat()))
    return aid or None


def _add(db, station, item: FeedItem, song: dict, now: datetime) -> tuple[str, Extracted, FeedItem] | None:
    m = _match(song, 1.0)
    cid = candidate_id(m.artist, m.title, "")
    if db.execute("SELECT 1 FROM candidates WHERE id = ?", (cid,)).fetchone():
        return None
    db.execute("INSERT OR IGNORE INTO feed_items (id, station_id, feed, guid, title, link, published_at, excerpt, seen_at, extracted_at) "
               "VALUES (?,?,?,?,?,?,?,?,?,?)", (item.id, station.id, item.feed, item.guid, item.title, item.link, item.published_at,
                                                item.excerpt, now.isoformat(), now.isoformat()))
    year = int(m.release_date[:4]) if m.release_date[:4].isdigit() else None
    db.execute("INSERT INTO candidates (id, feed_item_id, kind, artist, title, release, year, status, song_id, match_confidence, "
               "apple_url, preview_url, artwork_url, duration_ms, isrc, release_date, album, matched_artist, matched_title, resolved_at) "
               "VALUES (?,?,'track',?,?,?,?,'resolved',?,1.0,?,?,?,?,?,?,?,?,?,?)",
               (cid, item.id, m.artist, m.title, m.album, year, m.song_id, m.apple_url, m.preview_url, m.artwork_url,
                m.duration_ms, m.isrc, m.release_date, m.album, m.artist, m.title, now.isoformat()))
    return cid, Extracted("track", m.artist, m.title, m.album, "", year, ""), item


def scout_new_releases(gw, station: StationConfig, db: sqlite3.Connection, now: datetime, artists: list[str],
                       days: int = RECENT_DAYS) -> tuple[list[tuple[str, Extracted, FeedItem]], list[str]]:
    """Candidates from albums released in the last `days` by `artists`. An Apple refusal stops the scout (kept so far);
    a failed lookup is a note and the scout moves on (retried next time)."""
    db.executescript(SCHEMA)
    out: list[tuple[str, Extracted, FeedItem]] = []
    notes: list[str] = []
    cutoff = (now - timedelta(days=days)).date().isoformat()
    for name in artists:  # ponytail: one artist at a time (~2 lookups each, cached); parallel if the list grows past ~500
        try:
            aid = _artist_id(gw, station, db, name, now)
            if not aid:
                continue
            for al in _get(gw, station.apple_connection, f"/v1/catalog/{station.storefront}/artists/{aid}/view/latest-release").get("data", []):
                attrs = al.get("attributes", {})
                released = attrs.get("releaseDate", "")
                if released < cutoff or db.execute("SELECT 1 FROM scouted_albums WHERE station_id = ? AND album_id = ?",
                                                   (station.id, al["id"])).fetchone():
                    continue
                songs = _get(gw, station.apple_connection, f"/v1/catalog/{station.storefront}/albums/{al['id']}/tracks").get("data", [])
                item = FeedItem(hashlib.sha1(f"scout|{station.id}|{al['id']}".encode()).hexdigest()[:16], SCOUT_FEED, f"album:{al['id']}",
                                f"{name}: {attrs.get('name', '')} ({released})", attrs.get("url", ""), released,
                                f"A new release by {name}, an artist this station plays.")
                for s in songs:
                    if not has_version(s.get("attributes", {}).get("name", "")):  # originals only, as everywhere else
                        added = _add(db, station, item, s, now)
                        if added:
                            out.append(added)
                db.execute("INSERT OR IGNORE INTO scouted_albums VALUES (?,?,?)", (station.id, al["id"], now.isoformat()))
        except AppleRefused as e:
            notes.append(str(e))
            break
        except GatewayError as e:
            notes.append(f"scout lookup failed for {name}: {e.status}")
    db.commit()
    return out, notes
