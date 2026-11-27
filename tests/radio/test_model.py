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


def test_rotation_defaults_load():  # plan B1 Task 1
    r = load_station("uk-jazz").rotation
    assert [(c.code, c.size, c.rest_hours) for c in r.categories] == [
        ("A", 8, 3.5), ("B", 14, 7), ("C", 14, 12), ("R", 35, 36), ("G", 300, 96)]
    assert r.by_code("C").name == "Light/New"


def test_clocks_load_day_and_overnight():
    s = load_station("uk-jazz")
    day, night = s.clock_for(12), s.clock_for(23)
    assert day.name == "day" and night.name == "overnight" and s.clock_for(7).name == "day" and s.clock_for(6).name == "overnight"
    assert day.segments == ((0, ("id", "news")), (5, ("A", "G", "C", "break", "B", "R", "A")),
                            (30, ("id_tease", "G", "N", "break", "B", "R", "C")), (55, ("backsell",)))
    assert night.segments == ((0, ("id", "G", "A", "G", "R", "break", "G", "B")), (30, ("id", "G", "R", "G", "break", "C", "G")),
                              (55, ("backsell",)))
    assert s.separation == {"artist_hours": 3, "long_ms": 420000, "max_energy_step": 1}


def test_tables_created():
    db = sqlite3.connect(":memory:")
    open_radio(db)
    cols = lambda t: {r[1] for r in db.execute(f"PRAGMA table_info({t})")}
    assert {"station_id", "candidate_id", "category", "energy", "vocal", "added_at", "moved_at", "plays", "last_played_at",
            "opener", "closer", "source_note"} <= cols("rotation")
    assert {"station_id", "starts_at", "kind", "candidate_id", "song_id", "duration_ms", "category", "note", "source_url"} <= cols("queue")
    assert {"station_id", "held_at", "candidate_id", "action", "from_cat", "to_cat", "p", "reason"} <= cols("meeting")
