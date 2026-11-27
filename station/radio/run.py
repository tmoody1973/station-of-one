"""One station run (plan 2026-11-27-music-station-a, Task 8): poll -> extract -> fit (Jev, logged) ->
resolve (Apple Music) -> program -> sampler page -> upload. Each stage's failure is a note; an Apple
refusal stops matching and keeps the last published page (nothing is uploaded without a new set).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from station.config import Prefs
from station.gateway import GatewayError
from station.radio.extract import Extracted, extract
from station.radio.fit import fit_scores
from station.radio.model import candidate_id, load_station, open_radio
from station.radio.page import render_sampler, sampler_path
from station.radio.poll import FeedItem, poll
from station.radio.program import FIT_MIN, mark_scheduled, program_block
from station.radio.resolve import AppleRefused, resolve
from station.radio.seeds import seed_candidates
from station.steps.publish import cache_control, put_object
from station.store import record_decision

OUT_ROOT = Path("data/radio")
RESOLVE_LIMIT = 40  # per run: Apple lookups only for candidates Jev rated a fit
MIN_FILL = 0.5  # publish a set only when it fills at least half of block_minutes (review I2)
UNSCORED_LIMIT = 200


def _pending_items(db: sqlite3.Connection, station_id: str, limit: int = 64) -> list[FeedItem]:
    rows = db.execute("SELECT id, feed, guid, title, link, published_at, excerpt FROM feed_items "
                      "WHERE station_id = ? AND extracted_at IS NULL ORDER BY seen_at LIMIT ?", (station_id, limit)).fetchall()
    return [FeedItem(*r) for r in rows]


def _unscored(db: sqlite3.Connection, station_id: str) -> list[tuple[str, Extracted, FeedItem]]:
    """Every candidate from this station's items that Jev has not rated yet, so a failed hour is retried (review I5)."""
    rows = db.execute(
        "SELECT c.id, c.kind, c.artist, c.title, c.release, c.label, c.year, c.version, fi.id, fi.feed, fi.guid, fi.title, "
        "fi.link, fi.published_at, fi.excerpt FROM candidates c JOIN feed_items fi ON fi.id = c.feed_item_id "
        "WHERE fi.station_id = ? AND NOT EXISTS (SELECT 1 FROM station_candidates sc WHERE sc.station_id = ? "
        "AND sc.candidate_id = c.id) ORDER BY c.rowid LIMIT ?", (station_id, station_id, UNSCORED_LIMIT)).fetchall()
    return [(r[0], Extracted(r[1], r[2], r[3] or "", r[4] or "", r[5] or "", r[6], r[7] or ""), FeedItem(*r[8:15])) for r in rows]


def _store_candidates(db, station_id: str, found: dict[str, list[Extracted]], items: dict[str, FeedItem], now: datetime):
    new = []
    for item_id, music in found.items():
        for e in music:
            cid = candidate_id(e.artist, e.title, e.release)
            cur = db.execute("INSERT OR IGNORE INTO candidates (id, feed_item_id, kind, artist, title, release, label, year, version) "
                             "VALUES (?,?,?,?,?,?,?,?,?)", (cid, item_id, e.kind, e.artist, e.title, e.release, e.label, e.year, e.version))
            seen = db.execute("SELECT 1 FROM station_candidates WHERE station_id = ? AND candidate_id = ?", (station_id, cid)).fetchone()
            if cur.rowcount or not seen:
                new.append((cid, e, items[item_id]))
        db.execute("UPDATE feed_items SET extracted_at = ? WHERE id = ?", (now.isoformat(), item_id))
    db.commit()
    return new


def _resolve_some(gw, station, db, now: datetime, counts: dict, notes: list[str]) -> None:
    rows = db.execute("SELECT c.id, c.kind, c.artist, c.title, c.release, c.label, c.year, c.version, fi.excerpt, sc.fit_score "
                      "FROM candidates c JOIN station_candidates sc ON sc.candidate_id = c.id JOIN feed_items fi ON fi.id = c.feed_item_id "
                      "WHERE sc.station_id = ? AND c.status = 'new' AND sc.fit_score >= ? ORDER BY sc.fit_score DESC LIMIT ?",
                      (station.id, FIT_MIN, RESOLVE_LIMIT)).fetchall()
    for cid, kind, artist, title, release, label, year, version, excerpt, fit in rows:
        want = Extracted(kind, artist, title, release, label, year, version or "")
        try:
            matches, status = resolve(gw, station.apple_connection, want, station.storefront, excerpt or "")
        except AppleRefused as e:
            notes.append(str(e))
            return
        except GatewayError as e:
            notes.append(f"Apple Music lookup failed for {artist} - {title or release}: {e.status}")
            continue
        counts[status] = counts.get(status, 0) + 1
        db.execute("UPDATE candidates SET status = ?, resolved_at = ? WHERE id = ?", (status, now.isoformat(), cid))
        for i, m in enumerate(matches):
            target = cid if i == 0 else candidate_id(m.artist, m.title, release)
            if i:
                db.execute("INSERT OR IGNORE INTO candidates (id, feed_item_id, kind, artist, title, release) "
                           "SELECT ?, feed_item_id, 'track', ?, ?, release FROM candidates WHERE id = ?", (target, m.artist, m.title, cid))
                db.execute("INSERT OR IGNORE INTO station_candidates (station_id, candidate_id, fit_score, decided_at) VALUES (?,?,?,?)",
                           (station.id, target, fit, now.isoformat()))
            db.execute("UPDATE candidates SET status = 'resolved', song_id = ?, match_confidence = ?, apple_url = ?, preview_url = ?, "
                       "artwork_url = ?, duration_ms = ?, isrc = ?, release_date = ?, album = ?, matched_artist = ?, matched_title = ?, "
                       "resolved_at = ? WHERE id = ?", (m.song_id, m.confidence, m.apple_url, m.preview_url, m.artwork_url,
                                                        m.duration_ms, m.isrc, m.release_date, m.album, m.artist, m.title,
                                                        now.isoformat(), target))
        db.commit()


def _upload_strip(gw, prefs: Prefs, radio_root: Path) -> None:
    from station.runs import RUNS_ROOT
    from station.steps.stations import stations_json
    latest = sorted(Path(RUNS_ROOT).glob("*T??/newscast.json"))
    newscast = json.loads(latest[-1].read_text()) if latest else None
    put_object(gw, prefs.hosting.bucket, "data/stations.json", json.dumps(stations_json(prefs, newscast, radio_root)).encode(),
               "application/json", cache_control("data/stations.json"))


def run_station(gw, station_id: str, db: sqlite3.Connection, now: datetime, prefs: Prefs, out_root: Path = OUT_ROOT,
                discover: bool = True) -> dict:
    station = load_station(station_id)
    open_radio(db)
    counts: dict = {"items": 0, "extracted": 0, "fit_scored": 0, "resolved": 0, "held": 0, "not_on_apple": 0}
    notes: list[str] = []
    if discover:  # overnight runs only schedule and publish (plan B1 Task 7)
        new_items, poll_notes = poll(gw, station, db, now)
        notes += poll_notes
        items = {it.id: it for it in [*new_items, *_pending_items(db, station.id)]}
        counts["items"] = len(new_items)
        found, ex_notes = extract(gw, prefs.writer.model, list(items.values()))
        notes += ex_notes
        counts["extracted"] = sum(len(v) for v in found.values())
        _store_candidates(db, station.id, found, items, now)
        seeds, seed_notes = seed_candidates(gw, station, db, now)  # the core, when the feeds run thin (Tarik, Nov 27)
        notes += seed_notes
        counts["seeds"] = len(seeds)
        cands = _unscored(db, station.id)
        if cands:
            scores, raw, model, fit_notes = fit_scores(gw, station, cands)
            notes += fit_notes
            for cid, score in scores.items():
                db.execute("INSERT OR REPLACE INTO station_candidates (station_id, candidate_id, fit_score, decided_at) VALUES (?,?,?,?)",
                           (station.id, cid, score, now.isoformat()))
                record_decision(db, f"radio:{cid}", f"fit:{station.id}", raw[cid], model or "", now.isoformat())
            counts["fit_scored"] = len(scores)
            db.commit()
        _resolve_some(gw, station, db, now, counts, notes)
    if station.programmer == "clock":  # the program director: a 24/7 queue (plan B1)
        from station.radio.onair import run_clock
        counts["notes"] = notes
        run_clock(gw, station, db, now, prefs, out_root, counts, notes)
        try:
            _upload_strip(gw, prefs, Path(out_root))
        except Exception as e:  # noqa: BLE001
            notes.append(f"station strip not updated: {e}")
        return counts
    block = program_block(station, db, now, mark=False)
    counts["notes"] = notes
    counts["scheduled"] = 0
    minutes = sum(t["duration_ms"] for t in block.tracks) / 60000
    if minutes < MIN_FILL * station.flow.get("block_minutes", 50):
        notes.append(f"thin set ({len(block.tracks)} tracks, {minutes:.0f} min): keeping the last page")
        return counts  # keep the last published set; nothing is marked played
    out = Path(out_root) / station.id
    out.mkdir(parents=True, exist_ok=True)
    data = {"station": station.id, "block": asdict(block), "counts": {k: v for k, v in counts.items() if k != "notes"}}
    (out / "latest.json").write_text(json.dumps(data, indent=1))
    html = render_sampler(station, block, {**counts, "scheduled": len(block.tracks)}, prefs)
    (out / "index.html").write_text(html)
    for key, body, ctype in ((f"data/radio/{station.id}.json", json.dumps(data).encode(), "application/json"),
                             (sampler_path(station.id), html.encode(), "text/html; charset=utf-8")):
        put_object(gw, prefs.hosting.bucket, key, body, ctype, cache_control(key))
    mark_scheduled(db, block, now)  # only after the upload: a failed upload burns nothing
    counts["scheduled"] = len(block.tracks)
    try:  # the strip is a nicety: its failure never fails the set
        _upload_strip(gw, prefs, Path(out_root))
    except Exception as e:  # noqa: BLE001
        notes.append(f"station strip not updated: {e}")
    return counts
