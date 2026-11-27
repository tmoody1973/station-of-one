"""Rhythm Lab plan, Task 2: the library into the station's rotation."""
import sqlite3

import pytest

from station.radio.library import SCHEMA, library_energy, seed_rotation
from station.radio.model import load_station, open_radio


def lib(*tracks):
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    open_radio(db)
    for t in tracks:
        row = {"track_id": "RLT1", "artist": "Flying Lotus", "title": "Zodiac Shit", "tier": "core", "play_count": 8,
               "first_played": "2014-11-21", "last_played": "2025-03-01", "hour1_plays": 2, "hour2_plays": 6,
               "opener_count": 0, "closer_count": 0, "in_segment": 0, "match_status": "resolved", "apple_music_id": "111",
               "apple_url": "https://music.apple.com/x", "preview_url": "https://p.m4a", "artwork_url": "https://a",
               "duration_ms": 240000, "release_date": "2010-05-24", "matched_artist": "Flying Lotus",
               "matched_title": "Zodiac Shit", "matched_album": "Cosmogramma", "isrc": "GB", "match_confidence": 0.95, **t}
        db.execute(f"INSERT INTO library_tracks ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
    return db


def rot(db):
    return {r[0]: r[1:] for r in db.execute(
        "SELECT candidate_id, category, energy, opener, closer, source_note FROM rotation WHERE station_id = 'rhythm-lab'")}


def test_tiers_map_to_categories():
    db = lib({"track_id": "t1", "tier": "core"}, {"track_id": "t2", "tier": "rotation"},
             {"track_id": "t3", "tier": "repeat", "last_played": "2023-02-01"}, {"track_id": "t4", "tier": "repeat", "last_played": "2019-05-01"},
             {"track_id": "t5", "tier": "single_spin"})
    counts = seed_rotation(db, load_station("rhythm-lab"))
    r = rot(db)
    assert {k: v[0] for k, v in r.items()} == {"lib:t1": "P", "lib:t2": "M", "lib:t3": "R", "lib:t4": "G", "lib:t5": "G"}
    assert counts == {"P": 1, "M": 1, "R": 1, "G": 2}
    assert r["lib:t1"][4] == "First aired on Rhythm Lab Radio, Nov 2014"
    song = db.execute("SELECT song_id, duration_ms, artist, status FROM candidates WHERE id = 'lib:t1'").fetchone()
    assert song == ("111", 240000, "Flying Lotus", "resolved")   # the scheduler reads songs from one place


@pytest.mark.parametrize("h1,h2,energy", [(1, 9, 3), (2, 6, 3), (5, 5, 2), (6, 4, 2), (7, 3, 1), (9, 1, 1)])
def test_energy_from_hour_placement(h1, h2, energy):
    assert library_energy(h1, h2) == energy


def test_energy_without_hour_data():  # Review Focus 5
    assert library_energy(0, 0) == 2


def test_unmatched_never_scheduled():  # Review Focus 3
    db = lib({"track_id": "t1"}, {"track_id": "t2", "match_status": "held"}, {"track_id": "t3", "match_status": "not_on_apple"},
             {"track_id": "t4", "match_status": None})
    seed_rotation(db, load_station("rhythm-lab"))
    assert set(rot(db)) == {"lib:t1"}
    assert db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 1


def test_guest_mix_tracks_excluded():
    db = lib({"track_id": "t1"}, {"track_id": "t2", "in_segment": 1})
    seed_rotation(db, load_station("rhythm-lab"))
    assert set(rot(db)) == {"lib:t1"}


def test_seed_rotation_idempotent():
    db = lib({"track_id": "t1", "opener_count": 3, "closer_count": 1})
    st = load_station("rhythm-lab")
    seed_rotation(db, st)
    db.execute("UPDATE rotation SET plays = 4, last_played_at = '2026-11-27T10:00:00+00:00' WHERE candidate_id = 'lib:t1'")
    seed_rotation(db, st)
    assert db.execute("SELECT COUNT(*), plays, last_played_at, opener, closer FROM rotation").fetchone() == (
        1, 4, "2026-11-27T10:00:00+00:00", 1, 1)   # a second run never resets what the station has played


def test_reseeding_keeps_the_meetings_moves():
    db = lib({"track_id": "t1", "tier": "core"})
    st = load_station("rhythm-lab")
    seed_rotation(db, st)
    db.execute("UPDATE rotation SET category = 'R', moved_at = '2026-12-01' WHERE candidate_id = 'lib:t1'")  # burned out
    seed_rotation(db, st)
    assert rot(db)["lib:t1"][0] == "R"


def test_seed_rotation_carries_holiday_tags():
    db = lib({"track_id": "t1", "special_tags": "holiday;best_of_year_2014"}, {"track_id": "t2"})
    seed_rotation(db, load_station("rhythm-lab"))
    tags = dict(db.execute("SELECT candidate_id, tags FROM rotation"))
    assert "holiday" in tags["lib:t1"] and not tags["lib:t2"]
