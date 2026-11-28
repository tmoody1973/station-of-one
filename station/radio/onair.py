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
from station.radio.page import (EXPLAINER_PATH, PLAYLISTS_PATH, explainer_path, meeting_path, render_explainer, render_meeting,
                                render_moved, render_playlists, render_sampler, sampler_path)
from station.radio.program import Block
from station.radio.scheduler import schedule_hour
from station.radio.tags import tag_songs
from station.radio.cards import facts_for, sonar_facts
from station.radio.voicing import voice_spoken
from station.runs import RUNS_ROOT
from station.steps.publish import cache_control, put_object
from station.store import record_decision

AHEAD_HOURS = 2
BOARD_SONGS = 15  # songs listed per category on the meeting page (the library holds thousands)


def news_for_hour(station: StationConfig, local_hour_start: datetime, prefs: Prefs, newscast_ms: int) -> int:
    """The news slot's planned length for an hour: the newscast's, in newscast hours (7 am to 7 pm), else none."""
    first, last = (int(t.split(":")[0]) for t in (prefs.station.first_newscast, prefs.station.last_newscast))
    return newscast_ms if station.news and first <= local_hour_start.hour <= last else 0


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
        "c.artwork_url, c.preview_url, q.text, q.sources, q.audio_url, q.audio_ms FROM queue q LEFT JOIN candidates c ON c.id = q.candidate_id "
        "WHERE q.station_id = ? AND q.starts_at >= ? AND q.starts_at < ? ORDER BY q.starts_at",
        (station_id, start.isoformat(), end.isoformat())).fetchall()
    keys = ("starts_at", "kind", "song_id", "duration_ms", "category", "note", "source_url", "candidate_id", "artist", "title",
            "album", "release_date", "apple_url", "artwork_url", "preview_url", "text", "sources", "audio_url", "audio_ms")
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


SLOT_LABELS = {"break": "Host break", "backsell": "Host break", "id": "Station ID", "id_tease": "Station ID", "news": "News"}


def schedule_view(db: sqlite3.Connection, station: StationConfig, now: datetime, prefs: Prefs) -> list[dict]:
    """The next two hours as the program director planned them (live-playlist Task 4): songs with category and
    energy, and the spoken slots with what the host will say and its sources."""
    now = now.astimezone(UTC)
    rows = _timed(window(db, station.id, now, now + timedelta(hours=AHEAD_HOURS)), ZoneInfo(prefs.station.timezone))
    for it in rows:
        it["label"] = SLOT_LABELS.get(it["kind"], "")
        it["sources"] = json.loads(it.get("sources") or "[]") if it["kind"] != "song" else []
        r = db.execute("SELECT energy FROM rotation WHERE station_id = ? AND candidate_id = ?", (station.id, it["candidate_id"])).fetchone() \
            if it["kind"] == "song" else None
        it["energy"] = r[0] if r else None
    return rows


def _style_counts(db, station: StationConfig) -> dict[str, int]:
    return dict(db.execute("SELECT style, COUNT(*) FROM rotation WHERE station_id = ? AND style IS NOT NULL GROUP BY style",
                           (station.id,)).fetchall())


def _explainer(db, station: StationConfig, prefs: Prefs) -> str:
    counts = dict(db.execute("SELECT category, COUNT(*) FROM rotation WHERE station_id = ? GROUP BY category", (station.id,)).fetchall())
    last = db.execute("SELECT MAX(held_at) FROM meeting WHERE station_id = ?", (station.id,)).fetchone()[0]
    return render_explainer(station, counts, last, prefs, _style_counts(db, station))


PAGE_BACK_HOURS = 3  # the tracklist shows what played in the last 3 hours


def _timed(items: list[dict], tz) -> list[dict]:
    """Start time on the listener's clock, and the end time the browser uses to mark what's on."""
    for it in items:
        start_dt = datetime.fromisoformat(it["starts_at"])
        it["at"] = start_dt.astimezone(tz).strftime("%-I:%M %p").lower()
        it["ends_at"] = (start_dt + timedelta(milliseconds=it["duration_ms"] or 0)).isoformat()
    return items


def station_page(db: sqlite3.Connection, station: StationConfig, prefs: Prefs, now: datetime, counts: dict | None = None) -> str:
    """The clock station's page as a tracklist (KCRW pattern): every song from 3 hours back to 3 ahead, newest first.
    The browser shows the one playing now on top and hides later ones (shell.js). Reads only; schedules nothing."""
    now = now.astimezone(UTC)
    tz = ZoneInfo(prefs.station.timezone)
    hour0 = now.replace(minute=0, second=0, microsecond=0)
    rows = [it for it in _timed(window(db, station.id, now - timedelta(hours=PAGE_BACK_HOURS), hour0 + timedelta(hours=AHEAD_HOURS + 1)), tz)
            if it["kind"] == "song" or (it["kind"] in ("break", "backsell") and it.get("audio_url"))]  # breaks show their work (B2)
    for it in rows:
        it["sources"] = json.loads(it.get("sources") or "[]") if it["kind"] != "song" else []
    songs = [it for it in rows if it["kind"] == "song"]
    on_now = next((s for s in reversed(songs) if s["starts_at"] <= now.isoformat()), None)
    block = Block(station.id, f"queue-{hour0:%Y%m%dT%H}", now.isoformat(), list(reversed(rows)))
    return render_sampler(station, block, counts or {}, prefs, on_now=on_now)


def playlists_page(db: sqlite3.Connection, now: datetime, prefs: Prefs, radio_root: Path = Path("data/radio")) -> str:
    """One tab per station: a clock station's songs today (newest first, the browser hides later ones), a sampler's set."""
    from station.radio.model import active_stations
    now = now.astimezone(UTC)
    tz = ZoneInfo(prefs.station.timezone)
    midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    tabs = []
    for st in active_stations():
        if st.programmer == "clock":
            rows = [it for it in _timed(window(db, st.id, midnight, now + timedelta(hours=AHEAD_HOURS)), tz) if it["kind"] == "song"]
            tabs.append({"st": st, "clock": True, "rows": list(reversed(rows))})
        else:
            try:
                rows = json.loads((Path(radio_root) / st.id / "latest.json").read_text())["block"]["tracks"]
            except (OSError, ValueError, KeyError, TypeError):
                rows = []
            tabs.append({"st": st, "clock": False, "rows": rows})
    return render_playlists(tabs, prefs)


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
        schedule_hour(station, db, local, news_for_hour(station, local, prefs, news))
    web = (lambda g, st, song: sonar_facts(g, prefs.perplexity, song)) if prefs.perplexity else None  # check 23
    voiced = voice_spoken(gw, db, station, prefs, now,  # Plan B2: IDs, teases and breaks in the host's voice
                          facts=lambda cid: facts_for(gw, db, station, cid, now, sonar=web))
    counts["voiced"] = voiced["voiced"]
    notes += voiced["notes"]
    items = _timed(window(db, station.id, now - timedelta(hours=1), hour0 + timedelta(hours=AHEAD_HOURS + 1)), tz)
    songs = [it for it in items if it["kind"] == "song"]
    on_now = next((s for s in reversed(songs) if s["starts_at"] <= now.isoformat()), None)
    counts["scheduled"] = len([s for s in songs if s["starts_at"] > now.isoformat()])

    out = Path(out_root) / station.id
    out.mkdir(parents=True, exist_ok=True)
    tracks = [t for t in [on_now, *[s for s in songs if s["starts_at"] > now.isoformat()]] if t]  # the strip's 3-hour schedule
    (out / "latest.json").write_text(json.dumps({"station": station.id, "block": {"tracks": tracks}}, indent=1))
    queue = {"station": station.id, "updated": now.isoformat(), "items": [{k: v for k, v in it.items() if k != "candidate_id"} for it in items]}
    pages = ((f"data/radio/{station.id}/queue.json", json.dumps(queue).encode(), "application/json"),
             (sampler_path(station.id), station_page(db, station, prefs, now, counts).encode(), "text/html; charset=utf-8"),
             (PLAYLISTS_PATH, playlists_page(db, now, prefs).encode(), "text/html; charset=utf-8"),
             (meeting_path(station.id), render_meeting(station, *meeting_view(db, station), prefs, _style_counts(db, station),
                                                       schedule=schedule_view(db, station, now, prefs)).encode(),
              "text/html; charset=utf-8"))
    explainer = _explainer(db, station, prefs).encode()
    pages += ((explainer_path(station.id), explainer, "text/html; charset=utf-8"),)  # one per station (two used to overwrite one)
    if station.type == "flagship":
        pages += ((EXPLAINER_PATH, explainer, "text/html; charset=utf-8"),)  # the address older pages link to
    templates = Path(__file__).resolve().parents[2] / "templates"  # the player, every hour (B2's waited for the 6:48 am build)
    pages += tuple((key, (templates / src).read_bytes(), ctype) for key, src, ctype in (
        ("shell.js", "shell.js", "text/javascript"), ("live.js", "live.js", "text/javascript"), ("shell.css", "_shell.css", "text/css")))
    if station.replaces:
        pages += ((sampler_path(station.replaces), render_moved(station).encode(), "text/html; charset=utf-8"),)
    for key, body, ctype in pages:
        put_object(gw, prefs.hosting.bucket, key, body, ctype, cache_control(key))
    return counts
