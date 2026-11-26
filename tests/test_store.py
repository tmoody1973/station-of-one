from datetime import UTC, datetime

import pytest

from station.store import (
    Post, get_cursor, local_midnight_utc, open_db, posts_read_since, record_aired, record_decision,
    set_cursor, upsert_posts,
)


def post(i: int, posted="2026-11-27T14:00:00Z") -> Post:
    return Post(id=f"hn:{i}", source="Hacker News", beat="ai-dev", kind="story", author="user1",
                title=f"Story {i}", url=f"https://example.com/{i}", text="", posted_at=posted,
                engagement={"points": 10, "comments": 2}, visibility="public")


@pytest.fixture
def db(tmp_path):
    return open_db(tmp_path / "s.db")


def test_upsert_returns_only_new(db):
    assert [p.id for p in upsert_posts(db, [post(1), post(2)])] == ["hn:1", "hn:2"]
    assert [p.id for p in upsert_posts(db, [post(2), post(3)])] == ["hn:3"]


def test_record_decision_stores_noul_probability(db):
    record_decision(db, "hn:1", "matter_week", {"type": "noul", "noul": 0.48}, "jev-1.14.0", "2026-11-27T14:05:00Z")
    row = db.execute("SELECT value, probability, confidence, model FROM decisions").fetchone()
    assert row == ("no", 0.48, None, "jev-1.14.0")


def test_record_decision_stores_choice(db):
    ans = {"type": "choice", "choice": "story", "confidence": 0.83,
           "probabilities": {"lead": 0.01, "story": 0.87, "overheard": 0.05, "none": 0.07}}
    record_decision(db, "hn:1", "part", ans, "jev-1.14.0", "2026-11-27T14:05:00Z")
    assert db.execute("SELECT value, probability, confidence FROM decisions").fetchone() == ("story", 0.87, 0.83)


def test_posts_today_resets_at_local_midnight():  # Review Focus 5
    now = datetime(2026, 11, 28, 5, 30, tzinfo=UTC)  # 11:30 pm Nov 27 in Chicago (CST)
    assert local_midnight_utc(now, "America/Chicago") == datetime(2026, 11, 27, 6, 0, tzinfo=UTC)


def test_posts_read_since_counts_scraped(db):
    upsert_posts(db, [post(1), post(2)])
    assert posts_read_since(db, datetime(2000, 1, 1, tzinfo=UTC)) == 2
    assert posts_read_since(db, datetime(2999, 1, 1, tzinfo=UTC)) == 0


def test_cursor_roundtrip(db):
    assert get_cursor(db, "rss") is None
    when = datetime(2026, 11, 27, 14, 0, tzinfo=UTC)
    set_cursor(db, "rss", when)
    assert get_cursor(db, "rss") == when


def test_record_aired(db):
    record_aired(db, "2026-11-27T09", [("hn:1", "lead", 0.62)], "2026-11-27T15:00:00Z")
    assert db.execute("SELECT post_id, part FROM aired").fetchall() == [("hn:1", "lead")]


def test_aired_posts_since(db):
    upsert_posts(db, [post(1), post(2)])
    record_aired(db, "2026-11-27T09", [("hn:1", "lead", 0.62)], "2026-11-27T15:00:00+00:00")
    from station.store import aired_posts_since
    assert [p.id for p in aired_posts_since(db, datetime(2026, 11, 27, 0, 0, tzinfo=UTC))] == ["hn:1"]
    assert aired_posts_since(db, datetime(2026, 11, 28, 0, 0, tzinfo=UTC)) == []


def test_aired_count_since(db):
    from station.store import aired_count_since
    record_aired(db, "a", [("hn:1", "lead", 0.6), ("hn:2", "story", 0.5)], "2026-11-27T15:00:00+00:00")
    assert aired_count_since(db, datetime(2026, 11, 27, 6, 0, tzinfo=UTC)) == 2
    assert aired_count_since(db, datetime(2026, 11, 28, 6, 0, tzinfo=UTC)) == 0
