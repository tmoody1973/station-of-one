import sqlite3
from datetime import UTC, datetime, timedelta

from station.radio.buzz import buzz
from station.radio.model import open_radio
from station.radio.seeds import SEED_FEED

NOW = datetime(2026, 11, 27, 18, 0, tzinfo=UTC)


def db_with(*items):
    db = sqlite3.connect(":memory:")
    open_radio(db)
    for i, (station, feed, title, excerpt, days_ago) in enumerate(items):
        db.execute("INSERT INTO feed_items (id, station_id, feed, guid, title, link, published_at, excerpt, seen_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (f"f{i}", station, feed, f"g{i}", title, "", "", excerpt, (NOW - timedelta(days=days_ago)).isoformat()))
    return db


def test_buzz_counts_mentions_in_window():
    db = db_with(("uk-jazz", "UK Vibe", "Shabaka live in Leeds", "", 1),
                 ("uk-jazz", "r/Jazz", "New record", "The new SHABAKA album is out", 3),
                 ("uk-jazz", "UK Vibe", "Shabaka at Ronnie's", "", 30),        # outside the window
                 ("other", "UK Vibe", "Shabaka", "", 1),                       # another station
                 ("uk-jazz", "UK Vibe", "Nubya Garcia", "", 1))
    assert buzz(db, "uk-jazz", "Shabaka", NOW - timedelta(days=7)) == 2


def test_seed_items_do_not_count():
    db = db_with(("uk-jazz", SEED_FEED, "Shabaka", "Shabaka, a core artist", 0))
    assert buzz(db, "uk-jazz", "Shabaka", NOW - timedelta(days=7)) == 0


def test_partial_name_does_not_count():
    db = db_with(("uk-jazz", "UK Vibe", "Shabakaville opens", "", 1),
                 ("uk-jazz", "UK Vibe", "Sons of Kemet", "with Shabaka Hutchings", 1))
    assert buzz(db, "uk-jazz", "Shabaka", NOW - timedelta(days=7)) == 1
    assert buzz(db, "uk-jazz", "Shabaka Hutchings", NOW - timedelta(days=7)) == 1
