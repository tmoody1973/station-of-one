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


def load_station(station_id: str, root: Path = STATIONS_ROOT) -> StationConfig:
    d = json.loads((Path(root) / f"{station_id}.json").read_text())
    return StationConfig(id=d["id"], name=d["name"], type=d["type"], brief=d["brief"],
                         feeds=tuple(Feed(f["type"], f["ref"]) for f in d["feeds"]), seeds=d.get("seeds", {}),
                         era_mix=d["era_mix"], flow=d["flow"], talk=d["talk"], voice=d["voice"], news=bool(d["news"]),
                         storefront=d["storefront"], apple_connection=d["apple_connection"])


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
"""


def open_radio(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    db.commit()


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def candidate_id(artist: str, title: str, release: str) -> str:
    return hashlib.sha1("|".join(normalize(x) for x in (artist, title, release)).encode()).hexdigest()[:16]
