"""The new-release scout (jazz station plan, Task 4): new albums from the artists a station already plays.

For each artist, Apple Music's catalog gives the artist's latest release; anything out in the last 60 days that this
station hasn't scouted becomes candidates, entered like the seed list's (already matched on Apple Music). Jev then
rates their fit with every other find, and the music meeting decides adds and, for a styled station, the style.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from datetime import datetime, timedelta
from urllib.parse import quote

from station.gateway import GatewayError
from station.radio.extract import Extracted
from station.radio.model import StationConfig, candidate_id, normalize
from station.radio.poll import FeedItem
from station.radio.resolve import AppleRefused, _get, _match, has_version

SCOUT_FEED = "Apple Music new releases"
DEEPEN_FEED = "Apple Music catalog, to deepen a thin style"
TOP_SONGS = 10
RECENT_DAYS = 60
BUDGET_S = 300  # a scout or a deepening pass never runs longer than this (the build lock goes stale at 20 minutes)


class _Stop(Exception):
    """Apple rate-limited us or the time budget ran out: keep what was found, try again next meeting."""


def _guard(e: GatewayError, notes: list[str], name: str, what: str) -> None:
    if e.status == 429:
        raise _Stop(f"{what} stopped: Apple Music rate limit (429) at {name}; the rest waits for the next meeting")
    notes.append(f"{what} lookup failed for {name}: {e.status}")


def _check_time(deadline: float, what: str) -> None:
    if time.monotonic() >= deadline:
        raise _Stop(f"{what} stopped: time budget used; the rest waits for the next meeting")
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
    if db.execute("SELECT 1 FROM candidates WHERE id = ? OR (song_id = ? AND song_id != '')", (cid, m.song_id)).fetchone():
        return None  # already held, possibly under another id (a library row): never the same recording twice
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
                       days: int = RECENT_DAYS, budget_s: float = BUDGET_S) -> tuple[list[tuple[str, Extracted, FeedItem]], list[str]]:
    """Candidates from albums released in the last `days` by `artists`. An Apple refusal stops the scout (kept so far);
    a failed lookup is a note and the scout moves on (retried next time)."""
    db.executescript(SCHEMA)
    out: list[tuple[str, Extracted, FeedItem]] = []
    notes: list[str] = []
    cutoff = (now - timedelta(days=days)).date().isoformat()
    deadline = time.monotonic() + budget_s
    for name in artists:  # ponytail: one artist at a time (~2 lookups each, cached); parallel if the list grows past ~500
        try:
            _check_time(deadline, "scout")
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
        except (AppleRefused, _Stop) as e:
            notes.append(str(e))
            break
        except GatewayError as e:
            try:
                _guard(e, notes, name, "scout")
            except _Stop as stop:
                notes.append(str(stop))
                break
    db.commit()
    return out, notes


def deepen_styles(gw, station: StationConfig, db: sqlite3.Connection, now: datetime, targets: dict[str, int],
                  artists_by_style: dict[str, list[str]], budget_s: float = BUDGET_S
                  ) -> tuple[list[tuple[str, Extracted, FeedItem]], dict[str, int], list[str]]:
    """For each style with fewer playable songs than its target: well-known recordings by that style's artists (Apple's
    top songs for each, artists checked once), up to twice the gap, as candidates. Jev still rates fit and names the style;
    the meeting files them under the catalog category."""
    db.executescript(SCHEMA)
    out: list[tuple[str, Extracted, FeedItem]] = []
    counts: dict[str, int] = {}
    notes: list[str] = []
    deadline = time.monotonic() + budget_s
    for style, target in targets.items():
        have = db.execute("SELECT COUNT(*) FROM rotation WHERE station_id = ? AND style = ?", (station.id, style)).fetchone()[0]
        want = 2 * (target - have)
        if want <= 0:
            continue
        for name in artists_by_style.get(style, []):
            if counts.get(style, 0) >= want:
                break
            try:
                _check_time(deadline, "deepening")
                aid = _artist_id(gw, station, db, name, now)
                if not aid or db.execute("SELECT 1 FROM scouted_albums WHERE station_id = ? AND album_id = ?",
                                         (station.id, f"top:{aid}")).fetchone():
                    continue
                songs = _get(gw, station.apple_connection,
                             f"/v1/catalog/{station.storefront}/artists/{aid}/view/top-songs?limit={TOP_SONGS}").get("data", [])
                item = FeedItem(hashlib.sha1(f"deepen|{station.id}|{aid}".encode()).hexdigest()[:16], DEEPEN_FEED, f"top:{aid}",
                                f"{name}: best-known recordings ({style})", "", "", f"Deepening {style} with {name}'s best-known recordings.")
                for s in songs:
                    if counts.get(style, 0) >= want:
                        break
                    if not has_version(s.get("attributes", {}).get("name", "")):
                        added = _add(db, station, item, s, now)
                        if added:
                            out.append(added)
                            counts[style] = counts.get(style, 0) + 1
                db.execute("INSERT OR IGNORE INTO scouted_albums VALUES (?,?,?)", (station.id, f"top:{aid}", now.isoformat()))
            except (AppleRefused, _Stop) as e:
                notes.append(str(e))
                db.commit()
                return out, counts, notes
            except GatewayError as e:
                try:
                    _guard(e, notes, name, "deepening")
                except _Stop as stop:
                    notes.append(str(stop))
                    db.commit()
                    return out, counts, notes
    db.commit()
    return out, counts, notes
