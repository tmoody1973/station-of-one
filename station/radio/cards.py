"""Facts a host may say about a song (Plan B2, Task 2). Cite or cut: every fact carries an http(s) link to where it
comes from, or it is dropped. Part 1: facts the station already holds (Apple Music, and where the agent found the
record). Perplexity's cards come first once check 23 pins its request shape (Tarik: "Add Perplexity"); until then,
and whenever Perplexity fails, the station's own facts stand alone."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from station.gateway import GatewayError
from station.radio.model import StationConfig

MAX_FACTS = 5


def _cited(facts: list[dict]) -> list[dict]:
    return [f for f in facts if str(f.get("source_url") or "").startswith(("http://", "https://")) and f.get("text")]


def own_facts(db: sqlite3.Connection, candidate_id: str) -> list[dict]:
    r = db.execute("SELECT COALESCE(c.matched_artist, c.artist), COALESCE(c.matched_title, c.title), c.album, c.release_date, "
                   "c.apple_url, f.feed, f.title, f.link FROM candidates c LEFT JOIN feed_items f ON f.id = c.feed_item_id "
                   "WHERE c.id = ?", (candidate_id,)).fetchone()
    if not r:
        return []
    artist, title, album, released, apple, feed, item_title, link = r
    facts = []
    if album and (released or "")[:4].isdigit():
        facts.append({"text": f"Apple Music lists {title} on {artist}'s album {album}, dated {released[:4]}.", "source_url": apple or "",
                      "source_name": "Apple Music"})
    if feed and link:
        facts.append({"text": f"The agent found it through {feed}.", "source_url": link, "source_name": feed})  # never the scraped title
    return _cited(facts)


def facts_for(gw, db: sqlite3.Connection, station: StationConfig, candidate_id: str, now: datetime, sonar=None) -> list[dict]:
    """Perplexity's cited facts first (when available), then the station's own; at most 5, every one linked."""
    song = db.execute("SELECT COALESCE(matched_artist, artist), COALESCE(matched_title, title), album, release_date FROM candidates "
                      "WHERE id = ?", (candidate_id,)).fetchone()
    extra: list[dict] = []
    if sonar and song:
        try:
            extra = _cited(sonar(gw, station, {"artist": song[0], "title": song[1], "album": song[2], "year": (song[3] or "")[:4]}))
        except (GatewayError, KeyError, TypeError, ValueError):
            extra = []  # Perplexity down, refusing or odd: the station's own facts stand alone (B2 Focus 1)
    return (extra + own_facts(db, candidate_id))[:MAX_FACTS]
