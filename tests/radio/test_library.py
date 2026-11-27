import sqlite3
from pathlib import Path

from station.radio.library import import_tracks, match_library, to_match
from tests.fakes import FakeGateway, ok

FIX = Path("tests/fixtures/rhythm_lab")


def db():
    d = sqlite3.connect(":memory:")
    import_tracks(d, FIX / "rhythm_lab_tracks.csv")
    return d


def test_import_reads_bom_csv_tiers_versions_and_segments():
    d = db()
    rows = d.execute("SELECT track_id, artist, base_title, version, tier, play_count, in_segment FROM library_tracks ORDER BY track_id").fetchall()
    assert len(rows) == 5
    assert rows[0] == ("RLT00001", "James Pants", "Crystal Lite", "", "core", 13, 0)
    assert rows[1][3] == "Jeremy Sole & Atropolis Remix" and rows[1][2] == "Batuque"
    assert next(r for r in rows if r[0] == "RLT00013")[6] == 1
    import_tracks(d, FIX / "rhythm_lab_tracks.csv")   # idempotent
    assert d.execute("SELECT COUNT(*) FROM library_tracks").fetchone()[0] == 5


def test_to_match_skips_guest_mixes_single_spins_and_done():
    d = db()
    assert [t[0] for t in to_match(d, min_plays=2)] == ["RLT00001", "RLT00004", "RLT00005"]
    d.execute("UPDATE library_tracks SET match_status = 'resolved' WHERE track_id = 'RLT00001'")
    assert [t[0] for t in to_match(d, min_plays=2)] == ["RLT00004", "RLT00005"]


def song(sid, artist, name):
    return {"id": sid, "attributes": {"artistName": artist, "name": name, "albumName": "Alb", "releaseDate": "2013-05-01",
                                      "durationInMillis": 250000, "isrc": "US1", "previews": [{"url": f"https://p/{sid}.m4a"}],
                                      "url": f"https://music.apple.com/us/song/{sid}", "artwork": {"url": "https://a/{w}x{h}.jpg"}}}


def test_match_stores_apple_fields_and_keeps_the_remix():
    d = db()
    gw = FakeGateway({("GET", "APPLE", "/v1/catalog/us/search"): [
        ok({"results": {"songs": {"data": [song("1", "James Pants", "Crystal Lite")]}}}),
        ok({"results": {"songs": {"data": [song("2", "Dom La Nena", "Batuque"), song("3", "Dom La Nena", "Batuque (Jeremy Sole & Atropolis Remix)")]}}}),
        ok({"results": {"songs": {"data": []}}})]})
    counts = match_library(gw, "APPLE", "us", d, min_plays=2, workers=1)
    assert counts == {"resolved": 2, "not_on_apple": 1}
    assert d.execute("SELECT apple_music_id, preview_url FROM library_tracks WHERE track_id = 'RLT00004'").fetchone() == ("3", "https://p/3.m4a")
    assert d.execute("SELECT match_status FROM library_tracks WHERE track_id = 'RLT00005'").fetchone()[0] == "not_on_apple"
