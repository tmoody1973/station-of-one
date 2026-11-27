"""Feed poller (plan 2026-11-27-music-station-a, Task 3; PRD "Discovery pipeline" steps 1-2).

Reads the station's feeds through the same Apify actors and item shapes as the newscast scraper, keeps
items not seen before (by GUID or link), and stores them. First run looks back 7 days, then a cursor.
The PRD's ETag polling is replaced by Apify's date filter: every call goes through the gateway.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from station.gateway import GatewayError
from station.radio.model import StationConfig
from station.steps.scrape import ACTORS, ScrapeError, actor_input, normalize, run_actor
from station.store import get_cursor, set_cursor

FIRST_RUN = timedelta(days=7)
EXCERPT = 600


@dataclass(frozen=True)
class FeedItem:
    id: str
    feed: str
    guid: str
    title: str
    link: str
    published_at: str
    excerpt: str


def _item_id(station_id: str, guid: str) -> str:
    return hashlib.sha1(f"{station_id}|{guid}".encode()).hexdigest()[:16]


def poll(gw, station: StationConfig, db: sqlite3.Connection, now: datetime) -> tuple[list[FeedItem], list[str]]:
    key = f"radio:{station.id}"
    since = get_cursor(db, key) or now - FIRST_RUN
    notes: list[str] = []
    found: list[FeedItem] = []
    for source_type in ("rss", "subreddit"):
        refs = [f.ref for f in station.feeds if f.type == source_type]
        if not refs:
            continue
        try:
            run = run_actor(gw, ACTORS[source_type], actor_input(source_type, refs, since), cap_usd=0.10, timeout_s=180)
        except (ScrapeError, GatewayError) as e:
            notes.append(f"{source_type} feeds failed: {str(e)[:120]}")
            continue
        for item in run.items:
            for post in normalize(source_type, item, station.id):
                guid = post.id or post.url
                if not guid:
                    continue
                text = f"{post.title}. {post.text}" if post.kind == "comment" else post.text
                found.append(FeedItem(_item_id(station.id, guid), post.source, guid, post.title, post.url,
                                      post.posted_at, " ".join(text.split())[:EXCERPT]))
    new = []
    for it in found:
        cur = db.execute("INSERT OR IGNORE INTO feed_items (id, station_id, feed, guid, title, link, published_at, excerpt, seen_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?)", (it.id, station.id, it.feed, it.guid, it.title, it.link,
                                                        it.published_at, it.excerpt, now.isoformat()))
        if cur.rowcount:
            new.append(it)
    db.commit()
    set_cursor(db, key, now)
    return new, notes
