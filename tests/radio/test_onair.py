"""Plan B1, Task 6: the queue kept 2 hours ahead and published; the schedule on the station page; the meeting page."""
import json
from datetime import UTC, datetime, timedelta

import station.radio.onair as onair
import station.radio.run as run_mod
from station.config import load_prefs
from station.radio.meeting import music_meeting  # noqa: F401  (monkeypatched below)
from station.radio.model import load_station
from station.radio.page import render_meeting
from station.store import SCHEMA as STORE_SCHEMA
from tests.radio.test_hour_shape import library
from tests.radio.test_scheduler import station_db

NOW = datetime(2026, 11, 20, 18, 10, tzinfo=UTC)   # 12:10 pm Chicago
RL = "rhythm-lab"


def rl_db():
    db = station_db()
    db.executescript(STORE_SCHEMA)
    library(db, per_cat=40)
    db.execute("CREATE TABLE IF NOT EXISTS artist_notes (artist TEXT, date TEXT, source TEXT, note TEXT)")
    db.execute("INSERT INTO artist_notes VALUES ('Artist P00', '2014-01-01', 'https://docs.google.com/document/d/SECRET', 'PRIVATE NOTE')")
    return db


def run(db, tmp_path, monkeypatch, now=NOW):
    uploads = {}
    monkeypatch.setattr(run_mod, "poll", lambda gw, st, d, n: ([], []))
    monkeypatch.setattr(run_mod, "extract", lambda gw, m, items: ({}, []))
    monkeypatch.setattr(run_mod, "seed_candidates", lambda gw, st, d, n: ([], []))
    monkeypatch.setattr(onair, "meeting_due", lambda db, st, n: False)
    put = lambda gw, bucket, key, data, *a: uploads.__setitem__(key, data)
    monkeypatch.setattr(run_mod, "put_object", put)
    monkeypatch.setattr(onair, "put_object", put)
    out = run_mod.run_station(object(), RL, db, now, load_prefs(), out_root=tmp_path)
    return out, uploads


def test_queue_json_shape(tmp_path, monkeypatch):
    db = rl_db()
    _, uploads = run(db, tmp_path, monkeypatch)
    q = json.loads(uploads[f"data/radio/{RL}/queue.json"])
    assert q["station"] == RL and q["items"]
    for it in q["items"]:
        assert datetime.fromisoformat(it["starts_at"]).utcoffset() == timedelta(0)
        assert {"starts_at", "kind", "song_id", "duration_ms", "note", "source_url", "artist", "title"} <= set(it)
    songs = [it for it in q["items"] if it["kind"] == "song"]
    assert songs and all(it["song_id"] and "apple_url" in it for it in songs)
    text = uploads[f"data/radio/{RL}/queue.json"].decode()
    for leak in ("docs.google.com", "SECRET", "PRIVATE NOTE", "drive_url"):   # Rhythm Lab Review Focus 2, queue half
        assert leak not in text


def test_queue_kept_two_hours_ahead(tmp_path, monkeypatch):
    db = rl_db()
    run(db, tmp_path, monkeypatch)
    last = db.execute("SELECT MAX(starts_at) FROM queue WHERE station_id = ?", (RL,)).fetchone()[0]
    assert datetime.fromisoformat(last) >= NOW + timedelta(hours=2) - timedelta(minutes=10)
    hours = lambda: db.execute("SELECT COUNT(*) FROM queue WHERE station_id = ? AND kind = 'id' AND starts_at LIKE '%:00:00+00:00'",
                               (RL,)).fetchone()[0]
    assert hours() == 3                                   # this hour and the next two
    run(db, tmp_path, monkeypatch, now=NOW + timedelta(hours=1))
    assert hours() == 4                                   # one more hour; none scheduled twice


def test_meeting_page_shows_reasons_escaped():
    db = rl_db()
    st = load_station(RL)
    db.execute("INSERT INTO meeting VALUES (?, ?, 'P01', 'move', 'N', 'M', 0.91, ?)", (RL, NOW.isoformat(), "Jev: <script>x</script>"))
    html = render_meeting(st, *onair.meeting_view(db, st), load_prefs())
    assert "&lt;script&gt;" in html and "<script>x" not in html and "0.91" in html
    assert "Power Gold" in html and "Artist P01" in html


def test_sampler_shows_on_now(tmp_path, monkeypatch):
    db = rl_db()
    _, uploads = run(db, tmp_path, monkeypatch)
    html = uploads[f"radio/{RL}/index.html"].decode()
    on = db.execute("SELECT q.candidate_id, c.matched_title FROM queue q JOIN candidates c ON c.id = q.candidate_id "
                    "WHERE q.station_id = ? AND q.kind = 'song' AND q.starts_at <= ? ORDER BY q.starts_at DESC LIMIT 1",
                    (RL, NOW.isoformat())).fetchone()
    assert "On now" in html and on[1] in html and "Next hour" in html
    latest = json.loads((tmp_path / RL / "latest.json").read_text())
    assert latest["block"]["tracks"][0]["title"] == on[1]          # the station strip shows what's on now
    assert f"radio/{RL}/meeting/index.html" in uploads and "radio/how-it-works/index.html" in uploads


def test_schedule_only_run_reads_no_feeds(tmp_path, monkeypatch):  # overnight runs skip discovery
    db = rl_db()
    monkeypatch.setattr(run_mod, "poll", lambda *a: (_ for _ in ()).throw(AssertionError("polled")))
    monkeypatch.setattr(onair, "meeting_due", lambda db, st, n: False)
    uploads = {}
    put = lambda gw, bucket, key, data, *a: uploads.__setitem__(key, data)
    monkeypatch.setattr(run_mod, "put_object", put)
    monkeypatch.setattr(onair, "put_object", put)
    run_mod.run_station(object(), RL, db, NOW, load_prefs(), out_root=tmp_path, discover=False)
    assert f"data/radio/{RL}/queue.json" in uploads


def test_on_now_with_a_local_clock_time(tmp_path, monkeypatch):  # preview bug: ISO strings with mixed offsets compare wrong
    from zoneinfo import ZoneInfo
    db = rl_db()
    _, uploads = run(db, tmp_path, monkeypatch, now=NOW.astimezone(ZoneInfo("America/Chicago")))
    html = uploads[f"radio/{RL}/index.html"].decode()
    assert "On now" in html and "No set yet" not in html


def test_clock_station_page_never_says_sampler(tmp_path, monkeypatch):
    db = station_db()
    db.executescript(STORE_SCHEMA)           # an empty rotation: nothing on now
    _, uploads = run(db, tmp_path, monkeypatch)
    html = uploads[f"radio/{RL}/index.html"].decode()
    assert "sampler" not in html.lower() and "program director" in html


def test_next_hour_shows_local_start_times(tmp_path, monkeypatch):
    db = rl_db()
    _, uploads = run(db, tmp_path, monkeypatch)
    html = uploads[f"radio/{RL}/index.html"].decode()
    q = json.loads(uploads[f"data/radio/{RL}/queue.json"])
    nxt = next(it for it in q["items"] if it["kind"] == "song" and it["starts_at"] > NOW.isoformat())
    from zoneinfo import ZoneInfo
    local = datetime.fromisoformat(nxt["starts_at"]).astimezone(ZoneInfo("America/Chicago"))
    assert f'<span class="at">{local:%-I:%M %p}' .lower() in html.lower()
