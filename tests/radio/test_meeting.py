"""Plan B1, Task 4: the weekly music meeting. Jev decides adds, moves and burn-out; code applies the rules."""
import sqlite3
from datetime import UTC, datetime, timedelta

from station.radio.meeting import meeting_due, music_meeting
from station.radio.model import load_station, open_radio
from station.store import SCHEMA as STORE_SCHEMA

NOW = datetime(2026, 11, 30, 13, 0, tzinfo=UTC)   # Monday 7 am Chicago


class Jev:
    """Answers each question by the song's id: fn(kind, song) -> probability."""
    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def json(self, method, provider, path, body):
        self.calls.append(body)
        songs = body["state"]["songs"]
        answers = {}
        for key in body["questions"]:
            kind, i = key.rsplit("_", 1)
            answers[key] = {"type": "noul", "noul": self.fn(kind, songs[int(i)])}
        return {"model": "jev-1", "answers": answers}


def station_db():
    db = sqlite3.connect(":memory:")
    db.executescript(STORE_SCHEMA)
    open_radio(db)
    return db


def song(db, cid, artist="Artist", released="2025-06-01", fit=0.8):
    db.execute("INSERT INTO candidates (id, kind, artist, title, status, song_id, matched_artist, matched_title, release_date, "
               "duration_ms, apple_url) VALUES (?, 'track', ?, ?, 'resolved', ?, ?, ?, ?, 240000, 'https://music.apple.com/x')",
               (cid, artist, cid, f"s-{cid}", artist, cid, released))
    db.execute("INSERT INTO station_candidates (station_id, candidate_id, fit_score, decided_at) VALUES ('uk-jazz', ?, ?, '')", (cid, fit))


def member(db, cid, cat, days_in=3, **kw):
    song(db, cid, **kw)
    when = (NOW - timedelta(days=days_in)).isoformat()
    db.execute("INSERT INTO rotation (station_id, candidate_id, category, added_at, moved_at) VALUES ('uk-jazz', ?, ?, ?, ?)",
               (cid, cat, when, when))


def cats(db):
    return dict(db.execute("SELECT candidate_id, category FROM rotation WHERE station_id = 'uk-jazz'").fetchall())


def test_adds_go_to_C_catalog_to_G():
    db = station_db()
    song(db, "new1", released="2025-03-01")
    song(db, "old1", released="2001-05-01")
    song(db, "weak", fit=0.4)                       # below the fit floor: never asked
    song(db, "nope")                                # Jev says no
    jev = Jev(lambda kind, s: 0.2 if s["id"] == "nope" else 0.9)
    r = music_meeting(jev, load_station("uk-jazz"), db, NOW)
    assert cats(db) == {"new1": "C", "old1": "G"} and sorted(r.adds) == ["new1", "old1"]
    asked = [s["id"] for s in jev.calls[0]["state"]["songs"]]
    assert "weak" not in asked and {"buzz", "era", "fit", "source"} <= set(jev.calls[0]["state"]["songs"][0])
    assert "brief" in jev.calls[0]["state"]["station"]


def test_moves_up_and_burnout():
    db = station_db()
    for i in range(6):
        member(db, f"a{i}", "A", artist=f"A{i}")
    member(db, "a_burned", "A")
    member(db, "a_old", "A", days_in=30)            # 4 weeks in A
    member(db, "b1", "B")
    member(db, "c1", "C")
    member(db, "r_old", "R", days_in=400)           # a year in R
    yes = {"a_burned", "b1", "c1"}
    r = music_meeting(Jev(lambda kind, s: 0.9 if s["id"] in yes else 0.1), load_station("uk-jazz"), db, NOW)
    c = cats(db)
    assert (c["c1"], c["b1"], c["a_burned"], c["a_old"], c["r_old"]) == ("B", "A", "R", "R", "G")
    assert {m[0] for m in r.moves} == {"c1", "b1", "a_burned", "a_old", "r_old"}


def test_meeting_caps_churn():  # Review Focus 4
    db = station_db()
    for i in range(8):
        member(db, f"c{i}", "C", artist=f"C{i}")
    for i in range(5):
        member(db, f"a{i}", "A", artist=f"A{i}")
    music_meeting(Jev(lambda kind, s: 0.95), load_station("uk-jazz"), db, NOW)
    c = cats(db)
    assert sum(1 for k, v in c.items() if k.startswith("c") and v != "C") == 2      # 25% of 8
    assert sum(1 for v in c.values() if v == "A") >= 4                              # A never below half its size (8)


def test_every_decision_logged_with_reason():
    db = station_db()
    member(db, "c1", "C")
    member(db, "a1", "A")
    song(db, "new1")
    music_meeting(Jev(lambda kind, s: 0.9 if kind != "burned" else 0.1), load_station("uk-jazz"), db, NOW)
    asked = {(r[0], r[1]) for r in db.execute("SELECT post_id, question_id FROM decisions")}
    assert {("radio:new1", "meeting:add"), ("radio:c1", "meeting:up"), ("radio:a1", "meeting:burned")} <= asked
    rows = db.execute("SELECT candidate_id, action, from_cat, to_cat, p, reason FROM meeting").fetchall()
    assert ("new1", "add", None, "C") == rows[[r[0] for r in rows].index("new1")][:4]
    assert all(r[5] for r in rows) and all(r[4] is not None for r in rows)


def test_first_week_meets_daily_then_weekly():
    db = station_db()
    st = load_station("uk-jazz")
    tue = datetime(2026, 12, 1, 13, 0, tzinfo=UTC)   # Tuesday 7 am Chicago
    assert meeting_due(db, st, tue)                  # no rotation yet: day one
    db.execute("INSERT INTO rotation (station_id, candidate_id, category, added_at) VALUES ('uk-jazz', 'x', 'C', ?)",
               ((tue - timedelta(days=2)).isoformat(),))
    db.execute("INSERT INTO meeting (station_id, held_at) VALUES ('uk-jazz', ?)", ((tue - timedelta(days=1)).isoformat(),))
    assert meeting_due(db, st, tue)                  # first week: daily
    db.execute("INSERT INTO meeting (station_id, held_at) VALUES ('uk-jazz', ?)", (tue.isoformat(),))
    assert not meeting_due(db, st, tue + timedelta(hours=3))          # already met today
    db.execute("UPDATE rotation SET added_at = ?", ((tue - timedelta(days=20)).isoformat(),))
    wed = tue + timedelta(days=1)
    assert not meeting_due(db, st, wed)              # after the first week: Mondays only
    mon = datetime(2026, 12, 7, 13, 0, tzinfo=UTC)
    assert meeting_due(db, st, mon) and not meeting_due(db, st, mon.replace(hour=11))   # 5 am Chicago: too early
