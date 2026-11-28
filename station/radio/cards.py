"""Facts a host may say about a song (Plan B2, Task 2). Cite or cut: every fact carries an http(s) link to where it
comes from, or it is dropped. Part 1: facts the station already holds (Apple Music, and where the agent found the
record). Perplexity's cards come first once check 23 pins its request shape (Tarik: "Add Perplexity"); until then,
and whenever Perplexity fails, the station's own facts stand alone."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

from station.gateway import GatewayError
from station.radio.model import StationConfig

MAX_FACTS = 5
SONAR_PATH = "/v1/sonar"  # check 23: 200 in 2.6 s, $0.0052 per lookup
_SCHEMA = {"type": "object", "properties": {"facts": {"type": "array", "items": {"type": "object", "properties": {
    "text": {"type": "string"}, "citation": {"type": "integer"}}, "required": ["text", "citation"]}}}, "required": ["facts"]}
_SYSTEM = ("You give short, checkable facts about one recording for a radio host. Each fact is one sentence and must be supported "
           "by a numbered search result; set `citation` to that result's number ([1] is 1). No opinions, no links in the text.")
SCHEMA = "CREATE TABLE IF NOT EXISTS cards (kind TEXT, key TEXT, facts TEXT, fetched_at TEXT, PRIMARY KEY (kind, key));"


SPOKEN_NAMES = {"music.apple.com": "Apple Music", "bandcamp.com": "Bandcamp", "wikipedia.org": "Wikipedia", "discogs.com": "Discogs",
                "allmusic.com": "AllMusic", "allaboutjazz.com": "All About Jazz", "genius.com": "Genius", "pitchfork.com": "Pitchfork",
                "whosampled.com": "WhoSampled", "nprmusic.org": "NPR Music", "npr.org": "NPR", "theguardian.com": "The Guardian",
                "spotify.com": "Spotify", "youtube.com": "YouTube"}


def source_name(url: str) -> str:
    """How the host says a source: a known site by name, otherwise its bare domain."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return next((name for dom, name in SPOKEN_NAMES.items() if host == dom or host.endswith("." + dom)), host)


def sonar_facts(gw, connection: str, song: dict) -> list[dict]:
    """Perplexity Sonar's facts about one recording, each linked to the search result it cites (links come from the
    response's `citations`, never from the model's text: Perplexity docs). Label and year disambiguate common names."""
    ask = (f"Facts about the song \"{song['title']}\" by {song['artist']}" + (f" (album {song['album']}" if song.get("album") else "")
           + (f", {song['year']})" if song.get("year") and song.get("album") else (")" if song.get("album") else ""))
           + ": release year, label, producer, players, samples, where it was recorded. 3 to 5 facts.")
    r = gw.json("POST", connection, SONAR_PATH, {"model": "sonar", "messages": [{"role": "system", "content": _SYSTEM},
                                                                                 {"role": "user", "content": ask}],
                                                 "response_format": {"type": "json_schema", "json_schema": {"name": "facts", "schema": _SCHEMA}}},
                timeout=60)
    cites = r.get("citations") or []
    out = []
    for f in json.loads(r["choices"][0]["message"]["content"]).get("facts") or []:
        n = f.get("citation")
        if isinstance(n, int) and 0 < n <= len(cites):
            out.append({"text": str(f.get("text") or ""), "source_url": cites[n - 1], "source_name": source_name(cites[n - 1])})
    return _cited(out)


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
    db.executescript(SCHEMA)
    extra: list[dict] = []
    cached = db.execute("SELECT facts FROM cards WHERE kind = 'track' AND key = ?", (candidate_id,)).fetchone()
    if cached:
        extra = json.loads(cached[0])  # a track card is fetched once (PRD: track cards don't expire)
    elif sonar and song:
        try:
            extra = _cited(sonar(gw, station, {"artist": song[0], "title": song[1], "album": song[2], "year": (song[3] or "")[:4]}))
            db.execute("INSERT OR REPLACE INTO cards VALUES ('track', ?, ?, ?)", (candidate_id, json.dumps(extra), now.isoformat()))
            db.commit()
        except (GatewayError, KeyError, TypeError, ValueError):
            extra = []  # Perplexity down, refusing or odd: the station's own facts stand alone, and it's asked again next time
    own = own_facts(db, candidate_id)
    if extra:  # web facts set Apple's listed date aside (it is often a reissue: a host once argued "1969, not 1964")
        found = [f for f in own if f["source_name"] != "Apple Music"]
        return (extra[:1] + found + extra[1:])[:MAX_FACTS]  # one web fact, where it was found (PRD), then the rest
    return own[:MAX_FACTS]
