"""Jazz station plan, Task 1: the jazz cut of the Rhythm Lab library into ONE Jazz's rotation."""
import csv
import sqlite3
from dataclasses import replace

from station.radio.jazz import jazz_category, seed_jazz_rotation
from station.radio.model import load_station, open_radio
from tests.radio.test_library_rotation import lib

FIELDS = ["track_id", "jazz_tier", "jazz_style", "holiday_only", "segments", "rotation_tier"]


def jazz_csv(tmp_path, rows):
    p = tmp_path / "jazz_library.csv"
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows([{**{k: "" for k in FIELDS}, **r} for r in rows])
    return p


def station():
    return replace(load_station("rhythm-lab"), id="jazz")  # the jazz config arrives in Task 2


def rot(db):
    return {r[0]: r[1:] for r in db.execute("SELECT candidate_id, category, style, tags FROM rotation WHERE station_id = 'jazz'")}


def test_core_only_and_styles_kept(tmp_path):
    db = lib({"track_id": "t1"}, {"track_id": "t2"}, {"track_id": "t3", "tier": "repeat"}, {"track_id": "t4", "tier": "single_spin"})
    f = jazz_csv(tmp_path, [{"track_id": "t1", "jazz_tier": "core", "jazz_style": "heritage", "rotation_tier": "core"},
                            {"track_id": "t2", "jazz_tier": "adjacent", "jazz_style": "beats_nu_jazz", "rotation_tier": "core"},
                            {"track_id": "t3", "jazz_tier": "core", "jazz_style": "vocal", "rotation_tier": "repeat", "segments": "guest mix"},
                            {"track_id": "t4", "jazz_tier": "core", "jazz_style": "uk_jazz", "rotation_tier": "single_spin"}])
    counts = seed_jazz_rotation(db, station(), f)
    r = rot(db)
    assert set(r) == {"lib:t1", "lib:t4"} and r["lib:t1"][1] == "heritage" and r["lib:t4"][1] == "uk_jazz"
    assert counts == {"heritage": {"P": 1}, "uk_jazz": {"G": 1}}


def test_tiers_map_to_jazz_categories():
    assert [jazz_category(t) for t in ("core", "rotation", "repeat", "single_spin")] == ["P", "P", "M", "G"]


def test_holiday_flag_kept(tmp_path):
    db = lib({"track_id": "t1"})
    f = jazz_csv(tmp_path, [{"track_id": "t1", "jazz_tier": "core", "jazz_style": "vocal", "rotation_tier": "core", "holiday_only": "yes"}])
    seed_jazz_rotation(db, station(), f)
    assert "holiday_only" in rot(db)["lib:t1"][2].split(";")


def test_unmatched_never_loaded(tmp_path):
    db = lib({"track_id": "t1", "match_status": "held"}, {"track_id": "t2", "match_status": None})
    f = jazz_csv(tmp_path, [{"track_id": t, "jazz_tier": "core", "jazz_style": "heritage", "rotation_tier": "core"} for t in ("t1", "t2")])
    assert seed_jazz_rotation(db, station(), f) == {} and rot(db) == {}


def test_style_column_added_to_an_existing_rotation_table():  # the live database predates the column
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE rotation (station_id TEXT, candidate_id TEXT, category TEXT, PRIMARY KEY (station_id, candidate_id))")
    open_radio(db)
    assert "style" in {r[1] for r in db.execute("PRAGMA table_info(rotation)")}


def test_drop_non_songs_from_rotation():  # Rhythm Lab aired a [Commentary] track, Nov 27
    import sqlite3
    from station.radio.library import SCHEMA as LIB, drop_non_songs
    from station.radio.model import open_radio
    from station.store import SCHEMA
    d = sqlite3.connect(":memory:")
    d.executescript(SCHEMA)
    open_radio(d)
    d.executescript(LIB)
    for tid, title in (("7", "The Lung (Nai Palm) [Commentary]"), ("8", "The Lung"), ("9", "Abusey Junction (Remix)")):
        d.execute("INSERT INTO library_tracks (track_id, artist, title, match_status, matched_title) VALUES (?, 'A', ?, 'resolved', ?)", (tid, title, title))
        d.execute("INSERT INTO candidates (id, kind, artist, title, status, matched_title) VALUES (?, 'track', 'A', ?, 'resolved', ?)", (f"lib:{tid}", title, title))
        d.execute("INSERT INTO rotation (station_id, candidate_id, category) VALUES ('rhythm-lab', ?, 'G')", (f"lib:{tid}",))
    assert drop_non_songs(d, dry_run=True) == [("rhythm-lab", "A", "The Lung (Nai Palm) [Commentary]")]
    assert d.execute("SELECT COUNT(*) FROM rotation").fetchone()[0] == 3                          # a dry run changes nothing
    drop_non_songs(d, dry_run=False)
    assert [r[0] for r in d.execute("SELECT candidate_id FROM rotation ORDER BY candidate_id")] == ["lib:8", "lib:9"]
    assert d.execute("SELECT match_status FROM library_tracks WHERE track_id = '7'").fetchone() == ("held",)
