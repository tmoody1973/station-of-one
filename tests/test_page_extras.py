from datetime import UTC, datetime

from station.config import load_prefs
from station.steps.page import decision_log, render_control_room, render_settings, step_rows
from station.steps.rundown import Rundown
from station.store import Post, counts_by_beat, record_aired, upsert_posts
from tests.test_page import newscast
from tests.test_rundown import j

PREFS = load_prefs()
RUN_LOG = {"run_id": "2026-11-26T17", "started_at": "2026-11-26T22:48:02+00:00", "total_seconds": 130.6, "steps": [
    {"name": "scrape", "tool": "Apify", "status": "repaired", "seconds": 90.0,
     "counts": {"new_posts": 61, "seen": 802, "apify_runs": ["a"]}, "notes": ["Retried once, then used the RSS feed."]},
    {"name": "judge", "tool": "TypeSafe Jev", "status": "done", "seconds": 4.0, "counts": {"posts_judged": 61, "decisions": 305},
     "notes": []},
    {"name": "voice", "tool": "Gemini TTS", "status": "done", "seconds": 22.3, "counts": {"chapters_voiced": 8, "failed": 0},
     "notes": []}]}


def test_decision_verdicts():
    aired, cut, drop, merged = j("a", 0.6), j("c", 0.3), j("d", 0.7, harm=0.31), j("m", 0.9, same_story=0.94)
    rd = Rundown((aired,), {"a": 90}, None, ("d",), (cut,), True, False)
    log = {d["post_id"]: d for d in decision_log([aired, cut, drop, merged], rd)}
    assert (log["a"]["verdict"], log["c"]["verdict"], log["d"]["verdict"], log["m"]["verdict"]) == ("AIR", "CUT", "DROP", "MERGE")
    assert log["d"]["score"] == 0.31 and "private" in log["d"]["reason"]  # DROP shows the harm probability
    assert log["m"]["score"] == 0.94 and log["c"]["reason"] == "below the 40% floor"
    assert "title" not in log["d"] or log["d"]["title"] == ""  # dropped posts are never shown


def test_step_rows_labels_detail_and_dot():
    rows = step_rows(RUN_LOG)
    scrape = rows[0]
    assert (scrape["label"], scrape["tool"], scrape["dot"], scrape["time"]) == ("Scrape sources", "Apify", "amber", "1:30")
    assert scrape["detail"] == "61 new posts, 802 seen"
    assert rows[1]["detail"] == "305 typed decisions"


def test_control_room_shows_tiles_and_manager_note():
    n = newscast()
    html = render_control_room(RUN_LOG, [], n, PREFS)
    assert "Station manager" in html and "Retried once, then used the RSS feed." in html
    assert "5 questions per post" in html and "floor 40%" in html and "budget 10:00" in html


def test_control_room_escapes_titles():
    html = render_control_room(RUN_LOG, [{"verdict": "CUT", "score": 0.3, "title": "<img src=x onerror=alert(1)>",
                                          "reason": "below the 40% floor", "post_id": "x"}], newscast(), PREFS)
    assert "<img src=x" not in html and "&lt;img" in html


def test_settings_has_no_forms_and_shows_rules():
    html = render_settings(PREFS, {"ai-dev": (1420, 31)})
    assert "<form" not in html and "<input" not in html
    assert "top five at 40% or higher" in html and "20% or higher" in html
    assert "Keys are held by the Fly.io connector gateway and never stored on the Sprite." in html
    assert "1,420" in html and "Arts and culture" in html


def test_counts_by_beat(make_db):
    db = make_db()
    p = lambda i, beat: Post(f"x:{i}", "S", beat, "story", None, "t", "u", "", "", {}, "public")
    upsert_posts(db, [p(1, "ai-dev"), p(2, "ai-dev"), p(3, "milwaukee")])
    record_aired(db, "n", [("x:1", "lead", 0.6)], datetime.now(UTC).isoformat())
    got = counts_by_beat(db, datetime(2000, 1, 1, tzinfo=UTC), datetime(2999, 1, 1, tzinfo=UTC))
    assert got == {"ai-dev": (2, 1), "milwaukee": (1, 0)}


def test_settings_shows_friendly_times():
    html = render_settings(PREFS, {})
    assert "7:00 am" in html and "7:00 pm" in html and "19:00" not in html
