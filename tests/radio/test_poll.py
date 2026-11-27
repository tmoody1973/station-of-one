from datetime import UTC, datetime

import pytest

from station.radio.model import load_station, open_radio
from station.radio.poll import poll
from station.steps.scrape import ACTORS
from station.store import get_cursor, open_db
from tests.fakes import FakeGateway, ok

NOW = datetime(2026, 11, 27, 18, tzinfo=UTC)
RSS = [{"type": "feed_item", "feed_url": "https://ukvibe.org/feed/", "feed_title": "UK Vibe", "item_title": "Nubya Garcia 'Odyssey'",
        "item_link": "https://ukvibe.org/review/odyssey", "item_guid": "uv-1", "item_published": "2026-11-26T10:00:00Z",
        "item_text": "Review: Nubya Garcia's Odyssey on Concord Jazz. " * 30, "item_author": "UK Vibe"}]
REDDIT = [{"type": "post", "id": "abc", "subreddit": "Jazz", "title": "New Music Crate - 27 November", "url": "https://www.reddit.com/r/Jazz/comments/abc/",
           "permalink": "https://www.reddit.com/r/Jazz/comments/abc/", "selfText": "Share what you're spinning", "createdAt": "2026-11-27T12:00:00Z", "author": "mod"},
          {"type": "comment", "id": "c1", "permalink": "https://www.reddit.com/r/Jazz/comments/abc/x/c1/", "postTitle": "New Music Crate",
           "body": "Kokoroko - Abusey Junction, still on repeat", "createdAt": "2026-11-27T13:00:00Z", "author": "listener"}]


def _run(ds):
    return [ok({"data": {"id": "r", "status": "SUCCEEDED", "defaultDatasetId": ds, "usageTotalUsd": 0.001}})]


def _gw(reddit_ok=True):
    return FakeGateway({("POST", "apify", f"/v2/actors/{ACTORS['rss']}/runs"): _run("rss"),
                        ("GET", "apify", "/v2/datasets/rss/items"): [ok(RSS)],
                        ("POST", "apify", f"/v2/actors/{ACTORS['subreddit']}/runs"): _run("rd") if reddit_ok else [ok({"e": 1}, status=500)],
                        ("GET", "apify", "/v2/datasets/rd/items"): [ok(REDDIT)]})


@pytest.fixture
def db(tmp_path):
    d = open_db(tmp_path / "s.db")
    open_radio(d)
    yield d
    d.close()


def test_poll_dedupes_by_guid_or_link(db):
    st = load_station("uk-jazz")
    first, _ = poll(_gw(), st, db, NOW)
    again, _ = poll(_gw(), st, db, NOW)
    assert len(first) == 3 and again == []
    assert first[0].excerpt and len(first[0].excerpt) <= 600
    assert {i.feed for i in first} == {"UK Vibe", "Reddit r/Jazz"}


def test_poll_first_run_looks_back_7_days_then_uses_cursor(db):
    st = load_station("uk-jazz")
    gw = _gw()
    poll(gw, st, db, NOW)
    body = next(c[3] for c in gw.calls if c[2].startswith(f"/v2/actors/{ACTORS['rss']}/runs"))
    assert body["filterByDate"].startswith("2026-11-20")
    assert get_cursor(db, "radio:uk-jazz") == NOW


def test_one_feed_failing_is_a_note(db):
    items, notes = poll(_gw(reddit_ok=False), load_station("uk-jazz"), db, NOW)
    assert len(items) == 1 and any("subreddit" in n for n in notes)
