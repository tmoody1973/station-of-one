"""Corrections (spec §4): grade every story aired a week earlier — still being discussed this week?"""
import json
from datetime import UTC, datetime, timedelta

from station.config import load_prefs
from station.steps import corrections as cor
from station.store import Post, record_aired, upsert_posts
from tests.fakes import FakeGateway, ok

PREFS = load_prefs()
TZ = "America/Chicago"


def post(pid, title="AI is turning jobs into gig work", scraped="2026-11-26T18:00:00+00:00"):
    return Post(pid, "Hacker News", "ai-dev", "story", "u", title, f"https://ex.com/{pid}", "Body.", "", {}, "public")


def add(db, posts, scraped_at):
    upsert_posts(db, posts)
    db.executemany("UPDATE posts SET scraped_at = ? WHERE id = ?", [(scraped_at, p.id) for p in posts])
    db.commit()


def test_due_calls_are_stories_aired_seven_local_days_earlier(make_db):
    db = make_db()
    add(db, [post("hn:1"), post("hn:2"), post("hn:3")], "2026-11-19T18:00:00+00:00")
    record_aired(db, "2026-11-19T12", [("hn:1", "lead", 0.62)], "2026-11-19T18:00:00+00:00")   # Nov 19, noon Central
    record_aired(db, "2026-11-20T07", [("hn:2", "story", 0.55)], "2026-11-20T13:00:00+00:00")  # Nov 20: not due yet
    record_aired(db, "2026-11-19T19", [("hn:3", "story", 0.45)], "2026-11-20T05:30:00+00:00")  # 11:30 pm Nov 19 Central: due
    calls = cor.due_calls(db, "2026-11-26", TZ)
    assert [(c.post.id, c.said) for c in calls] == [("hn:1", 0.62), ("hn:3", 0.45)]


def test_followups_only_recent_similar_posts(make_db, monkeypatch):
    db = make_db()
    add(db, [post("hn:1")], "2026-11-19T18:00:00+00:00")
    add(db, [post("hn:new", "Gig work and AI, a week on")], "2026-11-26T15:00:00+00:00")
    add(db, [post("hn:old", "Old echo")], "2026-11-20T15:00:00+00:00")
    monkeypatch.setattr(cor, "similar", lambda gw, index, ns, text, top_k=10: [("hn:1", 0.99), ("hn:new", 0.71), ("hn:old", 0.8), ("hn:far", 0.2)])
    call = cor.Call(post("hn:1"), 0.62, "2026-11-19T18:00:00+00:00", "2026-11-19T12")
    got = cor.followups(None, call, db, since_utc=datetime(2026, 11, 25, tzinfo=UTC))
    assert [p.id for p in got] == ["hn:new"]  # not itself, not too old, not dissimilar


def test_grade_one_jev_request_and_threshold():
    calls = [cor.Call(post("hn:1"), 0.62, "x", "n"), cor.Call(post("hn:2", "Faded story"), 0.55, "x", "n")]
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [ok({"model": "jev-1.14.0", "answers": {
        "still_0": {"type": "noul", "noul": 0.81}, "still_1": {"type": "noul", "noul": 0.12}}})]})
    items, model = cor.grade(gw, [(calls[0], [post("hn:new", "Gig work, a week on")]), (calls[1], [])])
    (_, _, _, req), = gw.calls
    assert set(req["questions"]) == {"still_0", "still_1"} and req["state"]["calls"][1]["recent_posts"] == []
    assert [(i["post_id"], i["held_up"]) for i in items] == [("hn:1", True), ("hn:2", False)] and model == "jev-1.14.0"


def report(backfill=True):
    return {"day": "2026-11-26", "week_of": "2026-11-19", "backfill": backfill, "called": 3, "held": 1, "faded": 2,
            "items": [{"post_id": "a", "title": "AI is turning jobs into gig work", "url": "https://ex.com/a", "said": 0.62, "p_still": 0.81, "held_up": True},
                      {"post_id": "b", "title": "Carbon emissions of US data centers", "url": "https://ex.com/b", "said": 0.62, "p_still": 0.1, "held_up": False},
                      {"post_id": "c", "title": "Court rules on AI probable cause", "url": "javascript:x", "said": 0.57, "p_still": 0.3, "held_up": False}]}


def test_chapter_is_code_written_with_numbers_and_backfill_note():
    ch = cor.corrections_chapter(report())
    text = ch.turns[0].text
    assert ch.kind == "corrections" and ch.turns[0].speaker == "host"
    assert "3 stories" in text and "1 was still being discussed" in text and "2 were not" in text
    assert "62 percent" in text and "Carbon emissions of US data centers" in text  # the strongest call that faded
    assert "last week's posts" in text and "in the last two days of feeds we read" in text and len(text.split()) <= 85


def test_lead_is_60_seconds_on_corrections_days():
    from station.steps.rundown import select
    from tests.test_rundown import j

    assert select([j("a", 0.6)], PREFS.thresholds, False, corrections=True).seconds["a"] == 60
    assert select([j("a", 0.6)], PREFS.thresholds, False).seconds["a"] == 90


def test_front_box_shows_summary_and_safe_links():
    from station.steps.page import render_front
    from tests.test_page import newscast

    n = newscast()
    html = render_front(n, [n], PREFS, corrections=report())
    assert "Corrections" in html and "called 3 stories" in html and "1 was still being discussed" in html
    assert "last two days of feeds we read" in html  # the window the code actually searched
    assert 'href="https://ex.com/a"' in html and "javascript:" not in html and "backfill" in html.lower()


def test_cli_no_due_calls_writes_empty_report(tmp_path, monkeypatch):
    from station.__main__ import main

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    monkeypatch.setattr("station.__main__.Gateway", lambda: None)
    run = tmp_path / "2026-11-26T07"
    assert main(["corrections", "--run", str(run)]) == 0
    assert json.loads((run / "corrections.json").read_text())["called"] == 0


def test_cli_grades_logs_and_flags_backfill(tmp_path, monkeypatch):
    from station.__main__ import main
    from station.store import open_db

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    db = open_db(tmp_path / "s.db")
    add(db, [post("hn:1")], "2026-11-19T18:00:00+00:00")
    record_aired(db, "backfill-2026-11-19", [("hn:1", "story", 0.62)], "2026-11-19T18:00:00+00:00")
    db.close()
    monkeypatch.setattr(cor, "similar", lambda *a, **k: [])
    monkeypatch.setattr("station.__main__.Gateway", lambda: FakeGateway({("POST", "typesafe", "/v1/systemone"): [
        ok({"model": "jev-1.14.0", "answers": {"still_0": {"type": "noul", "noul": 0.2}}})]}))
    run = tmp_path / "2026-11-26T07"
    assert main(["corrections", "--run", str(run)]) == 0
    r = json.loads((run / "corrections.json").read_text())
    assert (r["called"], r["faded"], r["backfill"]) == (1, 1, True)
    db = open_db(tmp_path / "s.db")
    assert db.execute("SELECT probability FROM decisions WHERE question_id = 'still_discussed'").fetchone() == (0.2,)


def test_write_puts_corrections_before_signoff(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from station.steps import write as w
    from station.steps.rundown import Rundown

    rd = Rundown((), {}, None, (), (), True, True)
    chapters, _ = w.write_all(None, rd, PREFS, datetime(2026, 11, 26, 7, tzinfo=ZoneInfo(TZ)), 100, 95, {},
                              corrections_chapter=cor.corrections_chapter(report()))
    assert [c.kind for c in chapters][-2:] == ["corrections", "signoff"]


def test_first_build_of_day_runs_corrections_before_rundown(monkeypatch):
    from station import build as build_mod
    from station.__main__ import main

    got = []
    monkeypatch.setattr(build_mod, "build", lambda hour, **kw: got.append(kw.get("steps")))
    main(["build", "--hour", "2026-11-27T07"])
    steps = got[0]
    assert steps.index("corrections") == steps.index("rundown") - 1 and steps[-3:] == ["table", "picks", "radio"]
