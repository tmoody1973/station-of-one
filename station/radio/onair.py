"""On air, around the clock (plan B1, Task 6): for a station run by the program director ("programmer": "clock").
Each hourly run: the music meeting when it's due, Jev's tags for new songs, the next two hours scheduled, then
the queue (last hour + next two), the station page with "On now" and the meeting page published."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from station.config import Prefs
from station.radio.meeting import meeting_due, music_meeting
from station.radio.model import StationConfig
from station.radio.page import EXPLAINER_PATH, meeting_path, render_explainer, render_meeting, render_sampler, sampler_path
from station.radio.program import Block
from station.radio.scheduler import schedule_hour
from station.radio.tags import tag_songs
from station.runs import RUNS_ROOT
from station.steps.publish import cache_control, put_object
from station.store import record_decision

AHEAD_HOURS = 2
BOARD_SONGS = 15  # songs listed per category on the meeting page (the library holds thousands)


def news_ms(station: StationConfig, runs_root: Path = RUNS_ROOT) -> int:
    """The latest newscast's length, as the planned length of each hour's news (0 when the station has no news)."""
    if not station.news:
        return 0
    for path in sorted(Path(runs_root).glob("*T??/newscast.json"), reverse=True):
        try:
            return int(json.loads(path.read_text())["audio"]["duration_ms"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return 0


def _tag_new(gw, db, station, now, notes) -> int:
    rows = db.execute("SELECT c.id, COALESCE(c.matched_artist, c.artist), COALESCE(c.matched_title, c.title), c.album, c.release_date "
                      "FROM rotation ro JOIN candidates c ON c.id = ro.candidate_id WHERE ro.station_id = ? AND ro.energy IS NULL",
                      (station.id,)).fetchall()
    if not rows:
        return 0
    items = [{"id": r[0], "artist": r[1], "title": r[2], "album": r[3], "release_date": r[4]} for r in rows]
    tags, raw, model, tag_notes = tag_songs(gw, items)
    notes += tag_notes
    for cid, t in tags.items():
        db.execute("UPDATE rotation SET energy = ?, vocal = ? WHERE station_id = ? AND candidate_id = ?", (t["energy"], t["vocal"], station.id, cid))
        for kind, answer in raw[cid].items():
            record_decision(db, f"radio:{cid}", f"tag:{kind}", answer, model or "", now.isoformat())
    db.commit()
    return len(tags)


def window(db: sqlite3.Connection, station_id: str, start: datetime, end: datetime) -> list[dict]:
    """Queue items as the public sees them: timing, the song and its Apple links, the public note. No private fields."""
    rows = db.execute(
        "SELECT q.starts_at, q.kind, q.song_id, q.duration_ms, q.category, q.note, q.source_url, q.candidate_id, "
        "COALESCE(c.matched_artist, c.artist), COALESCE(c.matched_title, c.title), c.album, c.release_date, c.apple_url, "
        "c.artwork_url, c.preview_url FROM queue q LEFT JOIN candidates c ON c.id = q.candidate_id "
        "WHERE q.station_id = ? AND q.starts_at >= ? AND q.starts_at < ? ORDER BY q.starts_at",
        (station_id, start.isoformat(), end.isoformat())).fetchall()
    keys = ("starts_at", "kind", "song_id", "duration_ms", "category", "note", "source_url", "candidate_id", "artist", "title",
            "album", "release_date", "apple_url", "artwork_url", "preview_url")
    return [dict(zip(keys, r)) for r in rows]


def meeting_view(db: sqlite3.Connection, station: StationConfig) -> tuple[list[dict], list[dict]]:
    """This week's meeting decisions (newest first) and the rotation board (each category, its busiest songs)."""
    last = db.execute("SELECT MAX(held_at) FROM meeting WHERE station_id = ?", (station.id,)).fetchone()[0]
    rows = []
    if last:
        since = (datetime.fromisoformat(last) - timedelta(days=7)).isoformat()
        keys = ("held_at", "action", "from_cat", "to_cat", "p", "reason", "artist", "title")
        rows = [dict(zip(keys, r)) for r in db.execute(
            "SELECT m.held_at, m.action, m.from_cat, m.to_cat, m.p, m.reason, COALESCE(c.matched_artist, c.artist), "
            "COALESCE(c.matched_title, c.title) FROM meeting m LEFT JOIN candidates c ON c.id = m.candidate_id "
            "WHERE m.station_id = ? AND m.held_at >= ? AND m.action IS NOT NULL ORDER BY m.held_at DESC, m.rowid LIMIT 200",
            (station.id, since))]
    board = []
    for cat in station.rotation.categories:
        count = db.execute("SELECT COUNT(*) FROM rotation WHERE station_id = ? AND category = ?", (station.id, cat.code)).fetchone()[0]
        songs = db.execute("SELECT COALESCE(c.matched_artist, c.artist), COALESCE(c.matched_title, c.title), ro.plays, ro.last_played_at "
                           "FROM rotation ro JOIN candidates c ON c.id = ro.candidate_id WHERE ro.station_id = ? AND ro.category = ? "
                           "ORDER BY ro.plays DESC, ro.last_played_at DESC, c.id LIMIT ?", (station.id, cat.code, BOARD_SONGS)).fetchall()
        board.append({"code": cat.code, "name": cat.name, "size": cat.size, "rest_hours": cat.rest_hours, "count": count,
                      "songs": [{"artist": a, "title": t, "plays": p or 0, "last_played": lp} for a, t, p, lp in songs]})
    return rows, board


def _explainer(db, station: StationConfig, prefs: Prefs) -> str:
    counts = dict(db.execute("SELECT category, COUNT(*) FROM rotation WHERE station_id = ? GROUP BY category", (station.id,)).fetchall())
    last = db.execute("SELECT MAX(held_at) FROM meeting WHERE station_id = ?", (station.id,)).fetchone()[0]
    return render_explainer(station, counts, last, prefs)


def run_clock(gw, station: StationConfig, db: sqlite3.Connection, now: datetime, prefs: Prefs, out_root: Path,
              counts: dict, notes: list[str]) -> dict:
    now = now.astimezone(UTC)  # queue times are UTC ISO strings, compared as text: never mix offsets
    if meeting_due(db, station, now):
        res = music_meeting(gw, station, db, now)
        notes += res.notes
        counts["meeting"] = {"adds": len(res.adds), "moves": len(res.moves), "drops": len(res.drops)}
    counts["tagged"] = _tag_new(gw, db, station, now, notes)
    tz = ZoneInfo(prefs.station.timezone)
    hour0 = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    news = news_ms(station)
    for k in range(AHEAD_HOURS + 1):  # this hour and the next two; an hour already scheduled is left alone
        local = (hour0 + timedelta(hours=k)).astimezone(tz)
        schedule_hour(station, db, local, news if station.clock_for(local.hour).name == "day" else 0)
    items = window(db, station.id, now - timedelta(hours=1), hour0 + timedelta(hours=AHEAD_HOURS + 1))
    for it in items:  # the listener's clock: start times in the station's time zone
        it["at"] = datetime.fromisoformat(it["starts_at"]).astimezone(tz).strftime("%-I:%M %p").lower()
    songs = [it for it in items if it["kind"] == "song"]
    on_now = next((s for s in reversed(songs) if s["starts_at"] <= now.isoformat()), None)
    upcoming = [s for s in songs if s["starts_at"] > now.isoformat() and s["starts_at"] < (now + timedelta(hours=1)).isoformat()]
    counts["scheduled"] = len([s for s in songs if s["starts_at"] > now.isoformat()])

    out = Path(out_root) / station.id
    out.mkdir(parents=True, exist_ok=True)
    tracks = [t for t in [on_now, *upcoming] if t]
    (out / "latest.json").write_text(json.dumps({"station": station.id, "block": {"tracks": tracks}}, indent=1))
    block = Block(station.id, f"queue-{hour0:%Y%m%dT%H}", now.isoformat(), upcoming)
    queue = {"station": station.id, "updated": now.isoformat(), "items": [{k: v for k, v in it.items() if k != "candidate_id"} for it in items]}
    pages = ((f"data/radio/{station.id}/queue.json", json.dumps(queue).encode(), "application/json"),
             (sampler_path(station.id), render_sampler(station, block, counts, prefs, on_now=on_now).encode(), "text/html; charset=utf-8"),
             (meeting_path(station.id), render_meeting(station, *meeting_view(db, station), prefs).encode(), "text/html; charset=utf-8"),
             (EXPLAINER_PATH, _explainer(db, station, prefs).encode(), "text/html; charset=utf-8"))
    for key, body, ctype in pages:
        put_object(gw, prefs.hosting.bucket, key, body, ctype, cache_control(key))
    return counts
