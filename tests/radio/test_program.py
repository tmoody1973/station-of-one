import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from station.radio.model import load_station, open_radio
from station.radio.program import program_block

NOW = datetime(2026, 11, 27, 18, tzinfo=UTC)


@pytest.fixture
def db():
    d = sqlite3.connect(":memory:")
    open_radio(d)
    d.execute("INSERT INTO feed_items (id, station_id, feed, guid, title, link, published_at, excerpt, seen_at) "
              "VALUES ('fi', 'uk-jazz', 'UK Vibe', 'g', 'A review', 'https://ukvibe.org/r', '', '', '')")
    return d


def add(db, cid, artist, fit=0.8, status="resolved", released="2026-06-01", ms=300000, scheduled=None):
    db.execute("INSERT INTO candidates (id, feed_item_id, kind, artist, title, status, song_id, match_confidence, apple_url, "
               "preview_url, artwork_url, duration_ms, release_date, album, matched_artist, matched_title) "
               "VALUES (?, 'fi', 'track', ?, ?, ?, ?, 0.9, 'https://music.apple.com/x', 'https://audio/x.m4a', 'https://art', ?, ?, 'Alb', ?, ?)",
               (cid, artist, f"Song {cid}", status, f"s{cid}", ms, released, artist, f"Song {cid}"))
    db.execute("INSERT INTO station_candidates VALUES ('uk-jazz', ?, ?, ?, ?)", (cid, fit, NOW.isoformat(), scheduled))


def test_block_fills_to_minutes_by_duration(db):
    for i in range(20):
        add(db, f"c{i}", f"Artist {i}")
    b = program_block(load_station("uk-jazz"), db, NOW)
    assert len(b.tracks) == 10 and sum(t["duration_ms"] for t in b.tracks) == 50 * 60000


def test_no_artist_within_gap(db):
    add(db, "old", "Kokoroko", scheduled=(NOW - timedelta(hours=1)).isoformat())
    add(db, "k2", "Kokoroko")
    add(db, "e1", "Ezra Collective", fit=0.9)
    add(db, "e2", "Ezra Collective", fit=0.85)
    artists = [t["artist"] for t in program_block(load_station("uk-jazz"), db, NOW).tracks]
    assert artists == ["Ezra Collective"]


def test_era_mix_is_approximated(db):
    for i in range(12):
        add(db, f"n{i}", f"New {i}", fit=0.9, released="2026-05-01")
        add(db, f"r{i}", f"Recent {i}", fit=0.8, released="2020-05-01")
        add(db, f"o{i}", f"Old {i}", fit=0.7, released="1972-05-01")
    tracks = program_block(load_station("uk-jazz"), db, NOW).tracks
    share = {k: sum(1 for t in tracks if t["era"] == k) / len(tracks) for k in ("new", "recent", "older")}
    assert abs(share["new"] - 0.5) <= 0.15 and abs(share["recent"] - 0.3) <= 0.15 and abs(share["older"] - 0.2) <= 0.15


def test_low_fit_and_held_are_excluded(db):
    add(db, "low", "Low", fit=0.3)
    add(db, "held", "Held", status="held")
    add(db, "ok", "Ok")
    assert [t["candidate_id"] for t in program_block(load_station("uk-jazz"), db, NOW).tracks] == ["ok"]


def test_scheduled_tracks_not_reused_and_note_has_source(db):
    add(db, "a", "A")
    first = program_block(load_station("uk-jazz"), db, NOW + timedelta(hours=5))
    assert first.tracks[0]["note"] == "Found in UK Vibe: A review" and first.tracks[0]["source_url"] == "https://ukvibe.org/r"
    assert program_block(load_station("uk-jazz"), db, NOW + timedelta(hours=10)).tracks == []
