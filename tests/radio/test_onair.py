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
    assert "On now" in html and on[1] in html and "Playlist" in html
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


def test_page_lets_the_browser_pick_on_now(tmp_path, monkeypatch):  # review minor 3, re-graded: On now was frozen for an hour
    import re
    db = rl_db()
    _, uploads = run(db, tmp_path, monkeypatch)
    html = uploads[f"radio/{RL}/index.html"].decode()
    rows = re.findall(r'<li class="trk"[^>]* data-starts="([^"]+)" data-ends="([^"]+)"', html)
    assert len(rows) >= 20                                       # played songs and the next hours, for the browser to advance
    assert any(a <= NOW.isoformat() < b for a, b in rows)       # the song on when the page was built is among them
    assert 'id="onnow"' in html and '<span class="tag kicker lbl">On now</span>' in html


def test_station_page_rows_newest_first(tmp_path, monkeypatch):  # live-playlist Task 3 (KCRW tracklist)
    import re
    db = rl_db()
    run(db, tmp_path, monkeypatch, now=NOW - timedelta(hours=2))        # two hours of schedule already behind us
    _, uploads = run(db, tmp_path, monkeypatch)
    html = uploads[f"radio/{RL}/index.html"].decode()
    starts = re.findall(r'<li class="trk"[^>]* data-starts="([^"]+)"', html)
    assert len(starts) >= 30 and starts == sorted(starts, reverse=True)     # newest first
    assert min(starts) <= (NOW - timedelta(hours=1, minutes=50)).isoformat()  # songs already played are listed
    assert all(re.search(r'data-song="[^"]+"', row) for row in re.findall(r'<li class="trk"[^>]*>', html))
    assert "Coming up" not in html and "Playlist" in html


def test_playlists_page_has_a_tab_per_station(tmp_path, monkeypatch):
    from station.radio.onair import playlists_page
    db = rl_db()
    run(db, tmp_path, monkeypatch)
    html = playlists_page(db, NOW, load_prefs())
    assert 'href="#rhythm-lab"' in html and 'id="rhythm-lab"' in html and 'href="#jazz"' in html and 'href="#uk-jazz"' not in html
    assert "<script>" not in html


def test_empty_queue_page():  # live-playlist Focus 5
    from station.radio.onair import station_page
    db = station_db()
    db.executescript(STORE_SCHEMA)
    html = station_page(db, load_station(RL), load_prefs(), NOW)
    assert "Nothing scheduled yet" in html and '<li class="trk"' not in html


def test_news_follows_newscast_hours():  # jazz plan Task 2: jazz dayparts aren't named "day"
    from zoneinfo import ZoneInfo
    from station.radio.onair import news_for_hour
    chi = ZoneInfo("America/Chicago")
    st = load_station("jazz")
    assert news_for_hour(st, datetime(2026, 11, 27, 12, tzinfo=chi), load_prefs(), 165000) == 165000
    assert news_for_hour(st, datetime(2026, 11, 27, 19, tzinfo=chi), load_prefs(), 165000) == 165000   # the 7 pm newscast
    assert news_for_hour(st, datetime(2026, 11, 27, 22, tzinfo=chi), load_prefs(), 165000) == 0


def test_each_clock_station_has_its_own_explainer(tmp_path, monkeypatch):  # jazz plan Task 6: one shared path was overwritten
    db = rl_db()
    _, uploads = run(db, tmp_path, monkeypatch)
    assert "radio/rhythm-lab/how-it-works/index.html" in uploads and "radio/how-it-works/index.html" in uploads   # the flagship keeps the old address
    monkeypatch.setattr(onair, "meeting_due", lambda db, st, n: False)
    jazz_uploads = {}
    put = lambda gw, bucket, key, data, *a: jazz_uploads.__setitem__(key, data)
    monkeypatch.setattr(onair, "put_object", put)
    monkeypatch.setattr(run_mod, "put_object", put)
    run_mod.run_station(object(), "jazz", db, NOW, load_prefs(), out_root=tmp_path, discover=False)
    assert "radio/jazz/how-it-works/index.html" in jazz_uploads and "radio/how-it-works/index.html" not in jazz_uploads


def test_jazz_explainer_shows_styles_and_dayparts():
    import re
    from station.radio.page import render_explainer
    st = load_station("jazz")
    html = render_explainer(st, {"P": 140, "M": 174, "G": 600}, None, load_prefs(), style_counts={"heritage": 86, "vocal": 52})
    for style in st.styles:
        assert f'data-style="{style}"' in html
    assert re.search(r'<tr data-style="heritage">.*?86.*?150', html, re.S)                  # playable now, and the target
    assert set(re.findall(r'data-clock="([a-z_]+)"', html)) == {"rise", "workday", "drive", "after_hours", "overnight"}
    heritage = set(re.findall(r'data-slot="heritage"', html)) and re.search(r'fill="([^"]+)"[^>]*data-slot="heritage"', html).group(1)
    vocal = re.search(r'fill="([^"]+)"[^>]*data-slot="vocal"', html).group(1)
    assert heritage != vocal                                                                 # the clocks are colored by style
    assert ":30 always" not in html                                                          # jazz clocks have one fixed point


def test_retired_sampler_page_points_to_jazz(tmp_path, monkeypatch):  # jazz plan Task 6: the frozen sampler page stops showing
    db = rl_db()
    monkeypatch.setattr(onair, "meeting_due", lambda db, st, n: False)
    uploads = {}
    put = lambda gw, bucket, key, data, *a: uploads.__setitem__(key, data)
    monkeypatch.setattr(onair, "put_object", put)
    monkeypatch.setattr(run_mod, "put_object", put)
    run_mod.run_station(object(), "jazz", db, NOW, load_prefs(), out_root=tmp_path, discover=False)
    page = uploads["radio/uk-jazz/index.html"].decode()
    assert 'url=/radio/jazz/index.html' in page and 'href="/radio/jazz/index.html"' in page


def test_jazz_pd_page_shows_styles():
    from station.radio.page import render_meeting
    st = load_station("jazz")
    html = render_meeting(st, [], [], load_prefs(), styles={"heritage": 86, "vocal": 52})
    assert 'data-style="heritage"' in html and "86" in html and "150" in html
    assert 'href="/radio/jazz/how-it-works/index.html"' in html


def test_tracklist_shows_breaks_with_sources():  # Plan B2 Task 6: show the work (PRD: the tracklist links the break's sources)
    import json as _json
    db = rl_db()
    at = (NOW - timedelta(minutes=5)).isoformat()
    db.execute("INSERT INTO queue (station_id, starts_at, kind, duration_ms, text, sources, audio_url, audio_ms) VALUES (?,?,?,?,?,?,?,?)",
               (RL, at, "break", 25000, "That was <b>Pace</b>. It's on Source.",
                _json.dumps([{"url": "https://music.apple.com/us/song/1", "name": "Apple Music"}]), "/audio/radio/rhythm-lab/ab.mp3", 21000))
    db.execute("INSERT INTO queue (station_id, starts_at, kind, duration_ms, text, audio_url, audio_ms) VALUES (?,?,?,?,?,?,?)",
               (RL, (NOW - timedelta(minutes=9)).isoformat(), "id", 8000, "Rhythm Lab. ONE, 1.0 FM.", "/audio/radio/rhythm-lab/id.mp3", 6000))
    html = onair.station_page(db, load_station(RL), load_prefs(), NOW)
    assert 'data-kind="voice"' in html and "Host break" in html and "That was &lt;b&gt;Pace&lt;/b&gt;" in html
    assert 'href="https://music.apple.com/us/song/1"' in html and "/audio/radio/rhythm-lab/ab.mp3" in html
    assert "ONE, 1.0 FM." not in html                                   # station IDs stay off the playlist


def test_pd_page_shows_the_schedule():  # live-playlist Task 4 (Tarik, 11:22 pm: upcoming breaks visible somewhere)
    import json as _json
    import re
    from station.radio.page import render_meeting
    db = rl_db()
    soon = NOW + timedelta(minutes=10)
    db.execute("INSERT INTO candidates (id, kind, artist, title, status, matched_artist, matched_title) VALUES "
               "('sx', 'track', 'A <i>x</i>', 'T', 'resolved', 'A <i>x</i>', 'Song <b>1</b>')")
    db.execute("INSERT OR REPLACE INTO rotation (station_id, candidate_id, category, energy) VALUES (?, 'sx', 'P', 3)", (RL,))
    db.execute("INSERT INTO queue (station_id, starts_at, kind, candidate_id, duration_ms, category) VALUES (?,?,?,?,?,?)",
               (RL, soon.isoformat(), "song", "sx", 240000, "P"))
    db.execute("INSERT INTO queue (station_id, starts_at, kind, duration_ms, text, sources, audio_url) VALUES (?,?,?,?,?,?,?)",
               (RL, (soon + timedelta(minutes=4)).isoformat(), "break", 25000, "That was Song 1.",
                _json.dumps([{"url": "https://en.wikipedia.org/wiki/x", "name": "Wikipedia"}]), "/audio/radio/rhythm-lab/b.mp3"))
    db.execute("INSERT INTO queue (station_id, starts_at, kind, duration_ms) VALUES (?,?,?,?)",
               (RL, (NOW + timedelta(hours=3)).isoformat(), "id", 8000))          # beyond two hours: not listed
    st = load_station(RL)
    html = render_meeting(st, *onair.meeting_view(db, st), load_prefs(), schedule=onair.schedule_view(db, st, NOW, load_prefs()))
    sched = html[html.index('id="schedule"'):]
    assert "12:20 pm" in sched and "Song &lt;b&gt;1&lt;/b&gt;" in sched and re.search(r">P<", sched) and "energy 3" in sched
    assert "Host break" in sched and "That was Song 1." in sched and 'href="https://en.wikipedia.org/wiki/x"' in sched
    assert sched.count('class="slot') == 2 and "The program director" in html


def test_station_page_links_the_schedule():
    db = rl_db()
    html = onair.station_page(db, load_station(RL), load_prefs(), NOW)
    assert "The program director: schedule and music meeting" in html
