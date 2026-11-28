"""Jazz station plan, Task 4: the new-release scout, and Jev's style question at the music meeting."""
import sqlite3
from datetime import UTC, datetime, timedelta

from station.radio.model import load_station, open_radio
from station.radio.scout import SCOUT_FEED, scout_new_releases
from station.store import SCHEMA as STORE_SCHEMA
from tests.fakes import FakeGateway, ok

NOW = datetime(2026, 11, 27, 18, tzinfo=UTC)
ST = load_station("jazz")
C = ST.apple_connection


def db():
    d = sqlite3.connect(":memory:")
    d.executescript(STORE_SCHEMA)
    open_radio(d)
    return d


def artist_hit(aid, name):
    return ok({"results": {"artists": {"data": [{"id": aid, "attributes": {"name": name}}]}}})


def album(aid, name, released):
    return ok({"data": [{"id": aid, "attributes": {"name": name, "releaseDate": released, "artistName": "x"}}]})


def tracks(*names, artist="Nubya Garcia"):
    return ok({"data": [{"id": f"s{i}", "attributes": {"artistName": artist, "name": n, "albumName": "Odyssey II",
                                                        "releaseDate": "2026-11-13", "durationInMillis": 300000, "isrc": "I",
                                                        "previews": [{"url": "https://p.m4a"}], "url": f"https://music.apple.com/s{i}",
                                                        "artwork": {"url": "https://a/{w}x{h}.jpg"}}} for i, n in enumerate(names)]})


def test_recent_albums_from_station_artists_become_candidates():
    d = db()
    gw = FakeGateway({("GET", C, "/v1/catalog/us/search"): [artist_hit("1", "Nubya Garcia"), artist_hit("2", "Old Timer")],
                      ("GET", C, "/v1/catalog/us/artists/1/view/latest-release"): [album("a1", "Odyssey II", "2026-11-13")] * 2,
                      ("GET", C, "/v1/catalog/us/artists/2/view/latest-release"): [album("a2", "Way Back", "2019-03-01")],
                      ("GET", C, "/v1/catalog/us/albums/a1/tracks"): [tracks("Monsters II", "Clarity II", "Clarity II (Live)")]})
    found, notes = scout_new_releases(gw, ST, d, NOW, ["Nubya Garcia", "Old Timer"])
    titles = sorted(e.title for _, e, _ in found)
    assert titles == ["Clarity II", "Monsters II"] and notes == []                   # originals from the recent album only
    assert d.execute("SELECT DISTINCT feed, station_id FROM feed_items").fetchall() == [(SCOUT_FEED, "jazz")]
    again, _ = scout_new_releases(gw, ST, d, NOW, ["Nubya Garcia"])                  # cached artist id, album already scouted
    assert again == []


def test_scout_survives_apple_errors():  # jazz plan Review Focus 5
    d = db()
    gw = FakeGateway({("GET", C, "/v1/catalog/us/search"): [ok({}, 500), artist_hit("1", "Nubya Garcia")],
                      ("GET", C, "/v1/catalog/us/artists/1/view/latest-release"): [album("a1", "Odyssey II", "2026-11-13")],
                      ("GET", C, "/v1/catalog/us/albums/a1/tracks"): [tracks("Monsters II")]})
    found, notes = scout_new_releases(gw, ST, d, NOW, ["Broken Lookup", "Nubya Garcia"])
    assert [e.title for _, e, _ in found] == ["Monsters II"] and any("Broken Lookup" in n for n in notes)


# --- the meeting's style question ---
class Jev:
    def __init__(self, add=0.9, style="heritage"):
        self.add, self.style, self.calls = add, style, []

    def json(self, method, provider, path, body):
        self.calls.append(body)
        answers = {}
        for key in body["questions"]:
            kind = key.rsplit("_", 1)[0]
            answers[key] = ({"type": "choice", "choice": self.style, "confidence": 0.8} if kind == "style"
                            else {"type": "noul", "noul": self.add})
        return {"model": "jev-1", "answers": answers}


def addable(d, cid="new1"):
    d.execute("INSERT INTO candidates (id, kind, artist, title, status, song_id, matched_artist, matched_title, release_date, duration_ms) "
              "VALUES (?, 'track', 'Nubya Garcia', 'Monsters II', 'resolved', 's1', 'Nubya Garcia', 'Monsters II', '2026-11-13', 300000)", (cid,))
    d.execute("INSERT INTO station_candidates (station_id, candidate_id, fit_score, decided_at) VALUES ('jazz', ?, 0.8, '')", (cid,))


def test_style_choice_logged_and_attached():
    from station.radio.meeting import music_meeting
    d = db()
    addable(d)
    music_meeting(Jev(style="uk_jazz"), ST, d, NOW)
    assert d.execute("SELECT category, style FROM rotation WHERE candidate_id = 'new1'").fetchone() == ("N", "uk_jazz")
    assert d.execute("SELECT value FROM decisions WHERE post_id = 'radio:new1' AND question_id = 'meeting:style'").fetchone() == ("uk_jazz",)


def test_not_jazz_never_added():  # jazz plan Review Focus 3
    from station.radio.meeting import music_meeting
    d = db()
    addable(d)
    r = music_meeting(Jev(add=0.95, style="not_jazz"), ST, d, NOW)
    assert d.execute("SELECT COUNT(*) FROM rotation").fetchone()[0] == 0 and any("not jazz" in n for n in r.notes)


def test_scout_runs_with_the_meeting(tmp_path, monkeypatch):  # once per meeting, before fit scoring; artists from Tarik's file
    import station.radio.run as run_mod
    import station.radio.onair as onair
    from station.config import load_prefs
    from station.radio.jazz import scout_artists
    f = tmp_path / "jazz_artists.csv"
    f.write_text("﻿artist,jazz_tier,jazz_style,tracks,plays\nNubya Garcia,core,uk_jazz,5,9\nThundercat,adjacent,beats_nu_jazz,4,8\n")
    assert scout_artists(ST, f) == ["Nubya Garcia"]
    assert scout_artists(ST, tmp_path / "missing.csv") == ST.seeds["artists"]
    d = db()
    seen = []
    monkeypatch.setattr(run_mod, "poll", lambda gw, st, dd, n: ([], []))
    monkeypatch.setattr(run_mod, "extract", lambda gw, m, items: ({}, []))
    monkeypatch.setattr(run_mod, "seed_candidates", lambda gw, st, dd, n: ([], []))
    monkeypatch.setattr(run_mod, "scout_new_releases", lambda gw, st, dd, n, artists: (seen.append(len(artists)), ([], []))[1])
    monkeypatch.setattr(run_mod, "put_object", lambda *a: None)
    monkeypatch.setattr(onair, "put_object", lambda *a: None)
    monkeypatch.setattr(onair, "music_meeting", lambda gw, st, dd, n: __import__("station.radio.meeting", fromlist=["x"]).MeetingResult())
    for due in (True, False):
        monkeypatch.setattr(run_mod, "meeting_due", lambda dd, st, n, due=due: due)
        monkeypatch.setattr(onair, "meeting_due", lambda dd, st, n: False)
        run_mod.run_station(object(), "jazz", d, NOW, load_prefs(), out_root=tmp_path)
    assert len(seen) == 1
