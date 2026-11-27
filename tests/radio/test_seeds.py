import sqlite3
from datetime import UTC, datetime

import pytest

from station.radio.model import load_station, open_radio
from station.radio.seeds import SEED_FEED, seed_candidates
from tests.fakes import FakeGateway, ok

NOW = datetime(2026, 11, 27, 18, tzinfo=UTC)


def song(sid, artist, name):
    return {"id": sid, "attributes": {"artistName": artist, "name": name, "albumName": "Alb", "releaseDate": "2024-01-01",
                                      "durationInMillis": 240000, "isrc": "I", "previews": [{"url": f"https://p/{sid}.m4a"}],
                                      "url": f"https://music.apple.com/us/song/{sid}", "artwork": {"url": "https://a/{w}x{h}.jpg"}}}


@pytest.fixture
def db():
    d = sqlite3.connect(":memory:")
    open_radio(d)
    return d


def station_with(artists):
    s = load_station("uk-jazz")
    return s.__class__(**{**s.__dict__, "seeds": {"artists": artists, "labels": []}})


def test_seed_songs_are_by_the_artist_resolved_and_returned_for_fit(db):
    gw = FakeGateway({("GET", "APPLE", "/v1/catalog/us/search"): [ok({"results": {"songs": {"data": [
        song("1", "Ezra Collective", "Victory Dance"), song("2", "Ezra Collective", "Ego Killah"),
        song("3", "Someone Else", "Cover of Ezra"), song("4", "Ezra Collective & Sampa the Great", "Life Goes On"),
        song("5", "Ezra Collective", "No One's Watching Me"), song("6", "Ezra Collective", "God Gave Me Feet")]}}})]})
    st = station_with(["Ezra Collective"])
    st = st.__class__(**{**st.__dict__, "apple_connection": "APPLE"})
    cands, notes = seed_candidates(gw, st, db, NOW)
    assert len(cands) == 3 and notes == []
    assert all(e.artist.startswith("Ezra Collective") for _, e, _ in cands)
    row = db.execute("SELECT status, preview_url, matched_artist FROM candidates WHERE song_id = '1'").fetchone()
    assert row == ("resolved", "https://p/1.m4a", "Ezra Collective")
    assert db.execute("SELECT feed, extracted_at IS NOT NULL FROM feed_items").fetchone() == (SEED_FEED, 1)
    again, _ = seed_candidates(gw, st, db, NOW)
    assert all(e.title not in {x.title for _, x, _ in cands} for _, e, _ in again)


def test_artist_with_enough_unused_tracks_is_skipped(db):
    gw = FakeGateway({})
    st = station_with(["Kokoroko"])
    for i in range(2):
        db.execute("INSERT INTO candidates (id, feed_item_id, kind, artist, title, status, matched_artist) "
                   "VALUES (?, 'f', 'track', 'Kokoroko', ?, 'resolved', 'Kokoroko')", (f"k{i}", f"T{i}"))
        db.execute("INSERT INTO station_candidates VALUES ('uk-jazz', ?, 0.8, '', NULL)", (f"k{i}",))
    assert seed_candidates(gw, st, db, NOW) == ([], []) and gw.calls == []
