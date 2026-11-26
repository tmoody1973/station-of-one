from datetime import UTC, datetime, timedelta

import pytest

from station.config import load_prefs
from station.gateway import Response
from station.steps.scrape import ACTORS, actor_input, normalize, run_actor, scrape
from station.store import get_cursor, open_db
from tests.conftest import load_fixture
from tests.fakes import FakeGateway, ok

NOW = datetime(2026, 11, 27, 14, 48, tzinfo=UTC)


def test_normalize_hn_story_and_comments():
    item = load_fixture("apify_hn.json")[0]
    posts = normalize("hackernews", item, "ai-dev")
    story = posts[0]
    assert story.id == f"hn:{item['id']}" and story.kind == "story" and story.source == "Hacker News"
    assert story.engagement == {"points": item["score"], "comments": item["descendants"]}
    assert story.url == (item["url"] or item["hnUrl"])
    comments = [p for p in posts if p.kind == "comment"]
    assert len(comments) == len(item["comments"]) and comments[0].title.startswith("Comment on: ")


def test_normalize_strips_html():
    item = {"id": 1, "type": "story", "by": "u", "title": "T", "url": None, "hnUrl": "https://news.ycombinator.com/item?id=1",
            "text": "<p>Hello &amp; <i>bye</i></p>", "score": 1, "descendants": 0, "createdAt": "2026-11-27T14:00:00Z",
            "comments": []}
    assert normalize("hackernews", item, "ai-dev")[0].text == "Hello & bye"


def test_normalize_reddit_post_and_comment():
    items = load_fixture("apify_reddit.json")
    post = next(i for i in items if i["type"] == "post")
    p = normalize("subreddit", post, "ai-dev")[0]
    assert p.id == f"reddit:{post['id']}" and p.source == f"Reddit r/{post['subreddit']}"
    assert p.engagement == {"points": post["score"], "comments": post["numComments"]}
    comment = next(i for i in items if i["type"] == "comment")
    c = normalize("subreddit", comment, "ai-dev")[0]
    assert c.kind == "comment" and c.text == comment["body"] and c.source.startswith("Reddit r/")


def test_normalize_rss_skips_feed_summary():
    items = load_fixture("apify_rss.json")
    assert normalize("rss", next(i for i in items if i["type"] == "feed_summary"), "ai-dev") == []
    item = next(i for i in items if i["type"] == "feed_item")
    p = normalize("rss", item, "ai-dev")[0]
    assert p.title == item["item_title"] and p.url == item["item_link"] and p.source == item["feed_title"]


def test_actor_input_shapes():
    since = NOW - timedelta(hours=2)
    rss = actor_input("rss", ["https://a/feed"], since)
    assert rss["feedUrls"] == ["https://a/feed"] and rss["filterByDate"] == "2026-11-27T12:48:00Z"
    red = actor_input("subreddit", ["LocalLLaMA", "milwaukee"], since)
    assert red["urls"] == ["https://www.reddit.com/r/LocalLLaMA/", "https://www.reddit.com/r/milwaukee/"]
    assert red["includeNsfw"] is False and red["sort"] == "new"
    hn = actor_input("hackernews", ["topstories"], since)
    assert hn["mode"] == "topstories" and hn["dateFromUnix"] == int(since.timestamp())
    assert hn["includeComments"] is False  # 735 comments for 20 stories on Nov 26; Overheard uses Reddit


def runs_routes(actor_id: str, ds: str, items: list, extra_status=("RUNNING",)):
    return {
        ("POST", "apify", f"/v2/actors/{actor_id}/runs"): [ok({"data": {"id": f"run-{ds}", "status": "READY", "defaultDatasetId": ds}}, 201)],
        ("GET", "apify", f"/v2/actor-runs/run-{ds}"): [ok({"data": {"id": f"run-{ds}", "status": s, "defaultDatasetId": ds,
                                                                  "usageTotalUsd": 0.012}})
                                                       for s in (*extra_status, "SUCCEEDED")],
        ("GET", "apify", f"/v2/datasets/{ds}/items"): [ok(items)],
    }


def test_run_actor_polls_until_succeeded():
    gw = FakeGateway(runs_routes("a~b", "ds1", [{"x": 1}], extra_status=("RUNNING", "RUNNING")))
    run = run_actor(gw, "a~b", {})
    assert run.items == [{"x": 1}] and run.status == "SUCCEEDED" and run.usd == 0.012
    assert sum(1 for c in gw.calls if c[2].startswith("/v2/actor-runs/")) == 3


def test_run_actor_sends_spend_cap_and_memory():
    gw = FakeGateway(runs_routes("a~b", "ds1", []))
    run_actor(gw, "a~b", {}, memory_mb=1024)
    start = gw.calls[0][2]
    assert "maxTotalChargeUsd=0.25" in start and "memory=1024" in start and "timeout=240" in start


def _all_routes():
    routes = {}
    routes.update(runs_routes(ACTORS["hackernews"], "ds-hn", load_fixture("apify_hn.json")))
    routes.update(runs_routes(ACTORS["subreddit"], "ds-rd", load_fixture("apify_reddit.json")))
    routes.update(runs_routes(ACTORS["rss"], "ds-rss", load_fixture("apify_rss.json")))
    return routes


def test_scrape_returns_only_new_posts_and_advances_cursor(tmp_path):
    db = open_db(tmp_path / "s.db")
    prefs = load_prefs()
    first = scrape(FakeGateway(_all_routes()), prefs, db, NOW)
    assert first.posts and first.counts["new_posts"] == len(first.posts)
    assert get_cursor(db, "rss") == NOW
    assert first.counts["apify_usd"] == 0.036  # three runs at 0.012, read from each run object
    assert sorted(first.counts["apify_runs"]) == ["run-ds-hn", "run-ds-rd", "run-ds-rss"]  # finish re-reads final cost
    second = scrape(FakeGateway(_all_routes()), prefs, db, NOW)
    assert second.posts == []


def test_one_failed_source_does_not_stop_others(tmp_path):
    routes = _all_routes()
    routes[("POST", "apify", f"/v2/actors/{ACTORS['subreddit']}/runs")] = [Response(403, {}, b'{"error":"nope"}')]
    result = scrape(FakeGateway(routes), load_prefs(), open_db(tmp_path / "s.db"), NOW)
    assert any(p.source == "Hacker News" for p in result.posts)
    assert not any(p.source.startswith("Reddit") for p in result.posts)
    assert any("subreddit" in n for n in result.notes)
