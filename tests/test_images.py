"""Story photos are shown from the publisher's own address (linked, never copied), credited, with the
beat card underneath as the fallback. Tarik's call, Nov 26 (docs/decisions/004)."""
import sqlite3
from datetime import UTC, datetime, timedelta

from station.config import load_prefs
from station.steps.page import render_front
from station.steps.scrape import normalize
from station.store import Post, aired_posts_since, open_db, record_aired, upsert_posts
from tests.conftest import load_fixture
from tests.test_page import newscast

PREFS = load_prefs()


def test_bluesky_story_keeps_link_thumbnail():
    item = next(i for i in load_fixture("apify_bluesky.json")
                if (i.get("externalLink") or {}).get("thumbnail") and not i.get("isReply"))
    assert normalize("bluesky", item, "ai-dev")[0].image == item["externalLink"]["thumbnail"]


def test_gnews_and_reddit_images():
    g = next(i for i in load_fixture("apify_gnews.json") if i.get("image"))
    assert normalize("googlenews", g, "milwaukee")[0].image == g["image"]
    post = next(i for i in load_fixture("apify_reddit.json") if i["type"] == "post")
    assert normalize("subreddit", {**post, "thumbnail": "self", "imageUrls": []}, "ai-dev")[0].image is None
    assert normalize("subreddit", {**post, "thumbnail": "", "imageUrls": ["https://i.redd.it/a.png"]},
                     "ai-dev")[0].image == "https://i.redd.it/a.png"


def test_existing_database_gains_image_column(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)  # the schema before images
    old.execute("CREATE TABLE posts (id TEXT PRIMARY KEY, source TEXT, beat TEXT, kind TEXT, author TEXT, title TEXT,"
                " url TEXT, text TEXT, posted_at TEXT, engagement_json TEXT, visibility TEXT, scraped_at TEXT)")
    old.commit()
    old.close()
    db = open_db(path)
    upsert_posts(db, [Post("x:1", "S", "ai-dev", "story", None, "T", "https://ex.com", "", "", {}, "public",
                           image="https://img.example/x.jpg")])
    record_aired(db, "n", [("x:1", "lead", 0.6)], datetime.now(UTC).isoformat())
    (p,) = aired_posts_since(db, datetime.now(UTC) - timedelta(hours=1))
    assert p.image == "https://img.example/x.jpg"
    db.close()


def test_lead_shows_linked_photo_with_credit():
    n = newscast()
    n["stories"][0]["image"] = "https://img.example/lead.jpg"
    html = render_front(n, [n], PREFS)
    assert 'src="https://img.example/lead.jpg"' in html and 'referrerpolicy="no-referrer"' in html
    src = n["stories"][0]["sources"][0]
    assert f'Image: <a href="{src["url"]}"' in html and f'>{src["source_name"]}</a>, shown from the original' in html
    assert 'class="art"' in html  # beat card stays underneath as the fallback


def test_unsafe_or_missing_image_shows_beat_card_only():
    n = newscast()
    n["stories"][0]["image"] = "javascript:alert(1)"
    html = render_front(n, [n], PREFS)
    assert "javascript:" not in html and "<img" not in html and 'class="art"' in html
