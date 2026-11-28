"""ONE Jazz (jazz station plan): the jazz cut of the Rhythm Lab library as a 24/7 station's catalog.

Tarik's `jazz_library.csv` tags every track with a tier (core = jazz proper, adjacent = crossovers) and one of eight
styles. The strict format plays core only, never guest-mix tracks; holiday-only tracks are flagged for the scheduler.
Categories set rest times: P (Rhythm Lab core and rotation tiers), M (repeat), G (single spins); N is for new releases.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from station.radio.library import seed_rotation


def jazz_category(tier: str, last_played: str = "") -> str:
    return {"core": "P", "rotation": "P", "repeat": "M"}.get(tier, "G")


def jazz_tracks(jazz_csv: Path) -> dict[str, dict]:
    """Core-tier, non-guest-mix tracks: {track_id: {"style", "holiday_only"}}."""
    out = {}
    for r in csv.DictReader(open(jazz_csv, encoding="utf-8-sig")):
        if r.get("jazz_tier") == "core" and not r.get("segments"):
            out[r["track_id"]] = {"style": r["jazz_style"], "holiday_only": bool(r.get("holiday_only"))}
    return out


def seed_jazz_rotation(db: sqlite3.Connection, station, jazz_csv: Path) -> dict[str, dict[str, int]]:
    """Load the matched core jazz tracks into the station's rotation; returns {style: {category: count}}."""
    seed_rotation(db, station, only=jazz_tracks(jazz_csv), category=jazz_category)
    counts: dict[str, dict[str, int]] = {}
    for style, cat, n in db.execute("SELECT style, category, COUNT(*) FROM rotation WHERE station_id = ? GROUP BY style, category",
                                    (station.id,)):
        counts.setdefault(style, {})[cat] = n
    return counts


ARTISTS = Path("data/library/jazz_artists.csv")  # Tarik's control file, private on the Sprite


def scout_artists(station, path: Path = ARTISTS) -> list[str]:
    """The artists the scout checks for new releases: the core artists in Tarik's file, or the station's seed list."""
    try:
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    except OSError:
        return list(station.seeds.get("artists", []))
    return [r["artist"] for r in rows if r.get("jazz_tier") == "core"]


def artists_by_style(path: Path = ARTISTS) -> dict[str, list[str]]:
    """Core artists per style from Tarik's file, most-played first (who the thin styles are deepened from)."""
    try:
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    except OSError:
        return {}
    out: dict[str, list[str]] = {}
    for r in sorted((r for r in rows if r.get("jazz_tier") == "core"), key=lambda r: -int(r.get("plays") or 0)):
        out.setdefault(r["jazz_style"], []).append(r["artist"])
    return out
