"""The daily `picks` step (plan 2026-11-27-music-picks, Task 4): after the 7 am newscast.

Gathers candidates, asks Jev once, keeps the top `count` (one per source, none picked in the last 7 days),
logs every Jev answer, and writes data/picks/<day>.json for the page step. A failing source is a note.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from station.config import Prefs
from station.picks.choose import choose, key, rank
from station.picks.sources import bandcamp_candidates, youtube_candidates
from station.store import record_decision

REPEAT_DAYS = 7


def recent_keys(picks_root: Path, day: str) -> set[str]:
    out = set()
    for back in range(1, REPEAT_DAYS + 1):
        f = picks_root / f"{date.fromisoformat(day) - timedelta(days=back)}.json"
        try:
            out |= {f"{p['kind']}:{p['embed_id']}" for p in json.loads(f.read_text()).get("picks", [])}
        except (OSError, ValueError, KeyError, TypeError):
            continue  # missing or damaged day
    return out


def make_picks(gw, prefs: Prefs, db: sqlite3.Connection, day: str, picks_root: Path,
               now: datetime | None = None) -> dict:
    mp = prefs.music_picks
    yt, yt_notes = youtube_candidates(gw, list(mp.youtube_channels), now=now)
    bc, bc_notes = bandcamp_candidates(gw, list(mp.bandcamp_labels))
    candidates = yt + bc
    ranked, raw, model = rank(gw, candidates)
    asked_at = (now or datetime.now(UTC)).isoformat()
    for pick in candidates:  # every Jev answer is logged with its probability
        record_decision(db, f"pick:{key(pick)}", "interest", raw[key(pick)], model or "", asked_at)
    chosen = choose(ranked, mp.count, recent_keys(picks_root, day))
    out = {"day": day, "picks": [{**asdict(p), "score": s} for p, s in chosen], "model": model,
           "candidates": len(candidates), "notes": yt_notes + bc_notes}
    picks_root.mkdir(parents=True, exist_ok=True)
    tmp = picks_root / f"{day}.json.tmp"
    tmp.write_text(json.dumps(out, indent=1))
    tmp.replace(picks_root / f"{day}.json")  # whole file or nothing: the page step reads it every hour
    return out
