import sqlite3

from station.radio.model import Feed, candidate_id, load_station, open_radio


def test_load_station_reads_prd_fields():
    s = load_station("uk-jazz")
    assert s.id == "uk-jazz" and s.type == "genre" and s.storefront == "us" and s.news is True
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


def test_rhythm_lab_station_loads_as_flagship():  # Rhythm Lab plan, Task 1
    s = load_station("rhythm-lab")
    assert s.type == "flagship" and s.name == "Rhythm Lab" and s.news is True and s.storefront == "us"
    assert s.apple_connection == load_station("uk-jazz").apple_connection
    assert Feed("rss", "https://djmag.com/feed") in s.feeds and Feed("rss", "https://www.stonesthrow.com/feed/") in s.feeds
    assert len(s.seeds["artists"]) == 40 and s.seeds["artists"][:2] == ["Machinedrum", "Flying Lotus"]
    assert [(c.code, c.rest_hours) for c in s.rotation.categories] == [("P", 20), ("M", 72), ("R", 120), ("G", 240), ("N", 6)]
    assert {slot for c in s.clocks for _, slots in c.segments for slot in slots} <= {"P", "M", "R", "G", "N", "id", "id_tease",
                                                                                     "news", "break", "backsell"}
    assert s.clock_for(12).name == "day" and s.clock_for(2).name == "overnight"


def test_only_one_flagship():
    from station.radio.model import STATIONS_ROOT
    types = [load_station(p.stem).type for p in sorted(STATIONS_ROOT.glob("*.json"))]
    assert types.count("flagship") == 1


# Tarik's jazz_clocks.json (Nov 27), the slot orders the config must carry
TARIK_JAZZ_CLOCKS = {
    "rise": ([6, 7, 8, 9], ["vocal", "latin_brazilian_afro", "heritage", "contemporary", "jazz_funk_fusion", "uk_jazz", "vocal",
                            "latin_brazilian_afro", "contemporary", "heritage", "jazz_funk_fusion"]),
    "workday": ([10, 11, 12, 13, 14], ["contemporary", "uk_jazz", "jazz_funk_fusion", "heritage", "latin_brazilian_afro", "contemporary",
                                       "vocal", "uk_jazz", "jazz_funk_fusion", "contemporary", "heritage"]),
    "drive": ([15, 16, 17, 18], ["jazz_funk_fusion", "uk_jazz", "latin_brazilian_afro", "contemporary", "jazz_funk_fusion", "vocal",
                                 "uk_jazz", "heritage", "jazz_funk_fusion", "latin_brazilian_afro", "contemporary"]),
    "after_hours": ([19, 20, 21, 22, 23], ["heritage", "vocal", "spiritual_avant", "contemporary", "heritage", "uk_jazz", "spiritual_avant",
                                           "vocal", "contemporary", "heritage", "spiritual_avant"]),
    "overnight": ([0, 1, 2, 3, 4, 5], ["spiritual_avant", "contemporary", "spiritual_avant", "uk_jazz", "heritage", "spiritual_avant",
                                       "latin_brazilian_afro", "contemporary", "spiritual_avant", "heritage", "spiritual_avant"]),
}


def test_jazz_clocks_match_tarik_file():  # jazz station plan, Task 2
    st = load_station("jazz")
    assert st.programmer == "clock" and st.name == "ONE Jazz" and st.type == "genre"
    for name, (hours, slots) in TARIK_JAZZ_CLOCKS.items():
        clock = next(c for c in st.clocks if c.name == name)
        assert [h for h in range(24) if clock.covers(h)] == hours
        flat = [s for _, seg in clock.segments for s in seg]
        assert [s for s in flat if s not in ("id", "news", "break", "backsell")] == slots
        assert flat[:2] == ["id", "news"] and flat.index("break") == 6 and flat[11] == "break"   # breaks after songs 4 and 8
    assert st.separation["artist_hours"] == 4
    assert all(c.rest_hours >= 72 for c in st.rotation.categories)                             # no track inside 72 hours


def test_jazz_dayparts_cover_every_hour():
    st = load_station("jazz")
    assert [sum(c.covers(h) for c in st.clocks) for h in range(24)] == [1] * 24
    assert set(st.styles) == {"contemporary", "uk_jazz", "spiritual_avant", "jazz_funk_fusion", "heritage", "vocal", "latin_brazilian_afro"}
    assert all(set(fb) <= set(st.styles) for fb in st.styles.values())


def test_uk_jazz_sampler_retired():  # kept as a config (40 tests use it as their test station), but nothing runs or lists it
    from station.radio.model import active_stations
    assert load_station("uk-jazz").retired is True
    ids = [st.id for st in active_stations()]
    assert "jazz" in ids and "uk-jazz" not in ids and ids[0] == "rhythm-lab"   # the flagship first
