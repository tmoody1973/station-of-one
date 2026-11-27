import sqlite3

from station.radio.model import Feed, candidate_id, load_station, open_radio


def test_load_station_reads_prd_fields():
    s = load_station("uk-jazz")
    assert s.id == "uk-jazz" and s.type == "flagship" and s.storefront == "us" and s.news is True
    assert Feed("subreddit", "Jazz") in s.feeds and Feed("rss", "https://ukvibe.org/feed/") in s.feeds
    assert s.era_mix == {"new": 0.5, "recent": 0.3, "older": 0.2}
    assert s.flow["artist_gap_hours"] == 3 and s.flow["block_minutes"] == 50
    assert "Ezra Collective" in s.seeds["artists"] and s.apple_connection


def test_open_radio_is_idempotent():
    db = sqlite3.connect(":memory:")
    open_radio(db)
    open_radio(db)
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"feed_items", "candidates", "station_candidates"} <= tables


def test_candidate_id_ignores_case_and_punctuation():
    assert candidate_id("Nubya Garcia", "Odyssey", "") == candidate_id("nubya garcia", "Odyssey!", "")
    assert candidate_id("Nubya Garcia", "Odyssey", "") != candidate_id("Nubya Garcia", "Solstice", "")
