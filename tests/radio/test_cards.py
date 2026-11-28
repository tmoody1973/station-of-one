"""Plan B2, Task 2 (part 1): fact cards from what the station already holds; Perplexity layers on after check 23."""
import sqlite3
from datetime import UTC, datetime

from station.gateway import GatewayError
from station.radio.cards import facts_for, own_facts
from station.radio.model import load_station, open_radio
from station.store import SCHEMA

NOW = datetime(2026, 11, 28, 2, tzinfo=UTC)
ST = load_station("jazz")


def db(link="https://www.ukvibe.org/reviews/pace"):
    d = sqlite3.connect(":memory:")
    d.executescript(SCHEMA)
    open_radio(d)
    d.execute("INSERT INTO feed_items (id, station_id, feed, guid, title, link, published_at, excerpt, seen_at) "
              "VALUES ('f1', 'jazz', 'UK Vibe', 'g', 'Nubya Garcia returns', ?, '', '', '')", (link,))
    d.execute("INSERT INTO candidates (id, feed_item_id, kind, artist, title, status, matched_artist, matched_title, album, "
              "release_date, apple_url) VALUES ('c1', 'f1', 'track', 'Nubya Garcia', 'Pace', 'resolved', 'Nubya Garcia', 'Pace', "
              "'Source', '2020-08-21', 'https://music.apple.com/us/song/1')")
    return d


def test_own_facts_are_cited():
    facts = own_facts(db(), "c1")
    assert facts[0] == {"text": "Pace is on Nubya Garcia's album Source, released in 2020.",
                        "source_url": "https://music.apple.com/us/song/1", "source_name": "Apple Music"}
    assert facts[1]["source_url"] == "https://www.ukvibe.org/reviews/pace" and "UK Vibe" in facts[1]["text"]


def test_a_fact_without_a_link_is_cut():
    facts = own_facts(db(link=""), "c1")
    assert [f["source_name"] for f in facts] == ["Apple Music"]


def test_cards_fall_back_to_own_facts():  # B2 Focus 1: Perplexity down, refusing or absent
    def sonar(*a):
        raise GatewayError("perplexity", 429, "slow down")
    d = db()
    assert facts_for(object(), d, ST, "c1", NOW, sonar=sonar) == own_facts(d, "c1")
    assert facts_for(object(), d, ST, "c1", NOW, sonar=None) == own_facts(d, "c1")


def test_sonar_facts_come_first_and_keep_only_links():
    d = db()
    sonar = lambda gw, station, song: [{"text": "Recorded at Abbey Road.", "source_url": "https://example.org/a", "source_name": "example.org"},
                                       {"text": "Made up.", "source_url": "", "source_name": "?"}]
    facts = facts_for(object(), d, ST, "c1", NOW, sonar=sonar)
    assert facts[0]["source_url"] == "https://example.org/a" and all(f["source_url"].startswith("https://") for f in facts)
