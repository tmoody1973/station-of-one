"""Music station settings and tables (plan 2026-11-27-music-station-a, Task 2).

A station is a config file (PRD "Station model") that one shared pipeline runs. Candidates live in one
shared pool; station_candidates holds each station's view of them (Jev's fit score, when scheduled).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

STATIONS_ROOT = Path("config/stations")


@dataclass(frozen=True)
class Feed:
    type: Literal["rss", "subreddit"]
    ref: str


@dataclass(frozen=True)
class Category:
    code: str
    name: str
    size: int
    rest_hours: float


@dataclass(frozen=True)
class Rotation:
    categories: tuple[Category, ...]

    def by_code(self, code: str) -> Category:
        return next(c for c in self.categories if c.code == code)


@dataclass(frozen=True)
class Clock:
    name: str
    from_hour: int  # local hours, inclusive; overnight wraps past midnight (19 → 6)
    to_hour: int
    segments: tuple[tuple[int, tuple[str, ...]], ...]  # (minute the segment starts, slots in order)

    def covers(self, hour: int) -> bool:
        if self.from_hour <= self.to_hour:
            return self.from_hour <= hour <= self.to_hour
        return hour >= self.from_hour or hour <= self.to_hour


@dataclass(frozen=True)
class StationConfig:
    id: str
    name: str
    type: str
    brief: str
    feeds: tuple[Feed, ...]
    seeds: dict[str, Any]
    era_mix: dict[str, float]
    flow: dict[str, Any]
    talk: dict[str, Any]
    voice: dict[str, Any]
    news: bool
    storefront: str
    apple_connection: str
    rotation: Rotation = Rotation(())
    clocks: tuple[Clock, ...] = ()
    separation: dict[str, Any] | None = None
    meeting: dict[str, Any] | None = None
    shape: dict[str, Any] | None = None
    programmer: str = "sampler"
    styles: dict[str, list[str]] | None = None  # jazz: each style and the styles it falls back to (clock slots name styles)
    retired: bool = False  # kept as a config, never run or listed  # "clock": the program director's 24/7 queue (plan B1); "sampler": an hourly set (plan A)  # soft hour shape: energy by half hour, holiday window (Rhythm Lab)  # the station's ladder: new, catalog, top, up, burn, age, down

    def clock_for(self, local_hour: int) -> Clock:
        return next(c for c in self.clocks if c.covers(local_hour))


def load_station(station_id: str, root: Path = STATIONS_ROOT) -> StationConfig:
    d = json.loads((Path(root) / f"{station_id}.json").read_text())
    return StationConfig(id=d["id"], name=d["name"], type=d["type"], brief=d["brief"],
                         feeds=tuple(Feed(f["type"], f["ref"]) for f in d["feeds"]), seeds=d.get("seeds", {}),
                         era_mix=d["era_mix"], flow=d["flow"], talk=d["talk"], voice=d["voice"], news=bool(d["news"]),
                         storefront=d["storefront"], apple_connection=d["apple_connection"],
                         rotation=Rotation(tuple(Category(c["code"], c["name"], c["size"], c["rest_hours"]) for c in d.get("rotation", []))),
                         clocks=tuple(Clock(c["name"], c["from_hour"], c["to_hour"],
                                            tuple((m, tuple(slots)) for m, slots in c["segments"])) for c in d.get("clocks", [])),
                         separation=d.get("separation"), meeting=d.get("meeting"), shape=d.get("shape"),
                         programmer=d.get("programmer", "sampler"), styles=d.get("styles"), retired=bool(d.get("retired")))


SCHEMA = """
CREATE TABLE IF NOT EXISTS feed_items (
  id TEXT PRIMARY KEY, station_id TEXT, feed TEXT, guid TEXT, title TEXT, link TEXT, published_at TEXT,
  excerpt TEXT, seen_at TEXT, extracted_at TEXT);
CREATE TABLE IF NOT EXISTS candidates (
  id TEXT PRIMARY KEY, feed_item_id TEXT, kind TEXT, artist TEXT, title TEXT, release TEXT, label TEXT,
  year INTEGER, version TEXT, status TEXT DEFAULT 'new', song_id TEXT, match_confidence REAL, apple_url TEXT,
  preview_url TEXT, artwork_url TEXT, duration_ms INTEGER, isrc TEXT, release_date TEXT, album TEXT,
  matched_artist TEXT, matched_title TEXT, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS station_candidates (
  station_id TEXT, candidate_id TEXT, fit_score REAL, decided_at TEXT, scheduled_at TEXT,
  PRIMARY KEY (station_id, candidate_id));
CREATE TABLE IF NOT EXISTS rotation (
  station_id TEXT, candidate_id TEXT, category TEXT, energy INTEGER, vocal INTEGER, added_at TEXT, moved_at TEXT,
  plays INTEGER DEFAULT 0, last_played_at TEXT, opener INTEGER DEFAULT 0, closer INTEGER DEFAULT 0, source_note TEXT, tags TEXT, style TEXT,
  PRIMARY KEY (station_id, candidate_id));
CREATE TABLE IF NOT EXISTS queue (
  station_id TEXT, starts_at TEXT, kind TEXT, candidate_id TEXT, song_id TEXT, duration_ms INTEGER, category TEXT,
  note TEXT, source_url TEXT, PRIMARY KEY (station_id, starts_at));
CREATE TABLE IF NOT EXISTS library_pairs (a TEXT, b TEXT, count INTEGER, PRIMARY KEY (a, b));
CREATE TABLE IF NOT EXISTS meeting (
  station_id TEXT, held_at TEXT, candidate_id TEXT, action TEXT, from_cat TEXT, to_cat TEXT, p REAL, reason TEXT);
"""


def open_radio(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    have = {r[1] for r in db.execute("PRAGMA table_info(rotation)")}
    for col in ("opener INTEGER DEFAULT 0", "closer INTEGER DEFAULT 0", "source_note TEXT", "tags TEXT", "style TEXT"):
        if col.split()[0] not in have:  # databases created before the column existed
            db.execute(f"ALTER TABLE rotation ADD COLUMN {col}")
    db.commit()


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def candidate_id(artist: str, title: str, release: str) -> str:
    return hashlib.sha1("|".join(normalize(x) for x in (artist, title, release)).encode()).hexdigest()[:16]


def active_stations(root: Path = STATIONS_ROOT) -> list[StationConfig]:
    """Every station that runs and is listed, the flagship first."""
    configs = [load_station(p.stem, root) for p in sorted(Path(root).glob("*.json"))]
    return sorted((s for s in configs if not s.retired), key=lambda s: (s.type != "flagship", s.name))
