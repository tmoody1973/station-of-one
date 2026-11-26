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
    assert hn["includeComments"] is True and hn["maxCommentDepth"] == 1  # Tarik, Nov 26: volume + Overheard


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
    routes.update(runs_routes(ACTORS["bluesky"], "ds-bs", load_fixture("apify_bluesky.json")))
    routes.update(runs_routes(ACTORS["googlenews"], "ds-gn", load_fixture("apify_gnews.json")))
    return routes


def test_scrape_returns_only_new_posts_and_advances_cursor(tmp_path, make_db):
    db = make_db()
    prefs = load_prefs()
    first = scrape(FakeGateway(_all_routes()), prefs, db, NOW)
    assert first.posts and first.counts["new_posts"] == len(first.posts)
    assert get_cursor(db, "rss") == NOW
    assert first.counts["apify_usd"] == 0.06  # five runs at 0.012, read from each run object
    assert sorted(first.counts["apify_runs"]) == ["run-ds-bs", "run-ds-gn", "run-ds-hn", "run-ds-rd", "run-ds-rss"]
    second = scrape(FakeGateway(_all_routes()), prefs, db, NOW)
    assert second.posts == []


def test_one_failed_source_does_not_stop_others(tmp_path, make_db):
    routes = _all_routes()
    routes[("POST", "apify", f"/v2/actors/{ACTORS['subreddit']}/runs")] = [Response(403, {}, b'{"error":"nope"}')]
    result = scrape(FakeGateway(routes), load_prefs(), make_db(), NOW)
    assert any(p.source == "Hacker News" for p in result.posts)
    assert not any(p.source.startswith("Reddit") for p in result.posts)
    assert any("subreddit" in n for n in result.notes)


def test_normalize_bluesky_links_to_the_article():  # Tarik: stories must link to the real article
    item = next(i for i in load_fixture("apify_bluesky.json") if i.get("externalLink") and not i.get("isReply"))
    p = normalize("bluesky", item, "ai-dev")[0]
    link = item["externalLink"]
    assert p.id == f"bsky:{item['id']}" and p.source == f"Bluesky @{item['handle']}" and p.kind == "story"
    assert p.url == link["url"] and p.title == link["title"]
    assert item["text"] in p.text and (link.get("description") or "") in p.text
    assert p.engagement == {"points": item["likeCount"], "comments": item["replyCount"], "reposts": item["repostCount"]}


def test_normalize_bluesky_uses_links_when_no_card():
    item = {**load_fixture("apify_bluesky.json")[0], "externalLink": None, "isReply": False,
            "links": ["https://bsky.app/profile/x/post/1", "https://example.com/article"]}
    assert normalize("bluesky", item, "ai-dev")[0].url == "https://example.com/article"


def test_normalize_bluesky_without_outbound_link_is_never_a_story():
    item = {**load_fixture("apify_bluesky.json")[0], "externalLink": None, "links": [], "isReply": False}
    p = normalize("bluesky", item, "ai-dev")[0]
    assert p.kind == "comment" and p.url == item["url"]


def test_normalize_bluesky_skips_reposts():
    item = {**load_fixture("apify_bluesky.json")[0], "isRepost": True}
    assert normalize("bluesky", item, "ai-dev") == []


def test_normalize_google_news_item():
    item = load_fixture("apify_gnews.json")[0]
    p = normalize("googlenews", item, "milwaukee")[0]
    assert p.id == f"gnews:{item['guid']}" and p.source == item["source"] and p.url == item["link"]
    assert p.title == item["title"] and p.posted_at == item["publishedAt"]


def test_actor_input_bluesky_and_google_news():
    since = NOW - timedelta(hours=2)
    bs = actor_input("bluesky", ["simonwillison.net"], since)
    assert bs["mode"] == "posts" and bs["handles"] == ["simonwillison.net"] and bs["includeReposts"] is False
    assert bs["monitoringStoreName"] == "station-one" and bs["postedAfter"] == "2026-11-27"
    gn = actor_input("googlenews", ["Milwaukee"], since)
    assert gn == {"query": "Milwaukee", "language": "US:en", "openEndedDateRange": "2h", "maxItems": 15,
                  "fetchArticleDetails": True}


def test_google_news_runs_one_query_per_run():
    from station.steps.scrape import runs_for
    assert [i["query"] for i in runs_for("googlenews", ["Milwaukee", "Wisconsin"], NOW)] == ["Milwaukee", "Wisconsin"]
    assert len(runs_for("rss", ["https://a", "https://b"], NOW)) == 1


def test_empty_successful_run_still_advances_cursor(tmp_path, make_db):
    routes = _all_routes()
    routes.update(runs_routes(ACTORS["rss"], "ds-rss", []))
    db = make_db()
    scrape(FakeGateway(routes), load_prefs(), db, NOW)
    assert get_cursor(db, "rss") == NOW


def test_rss_reads_the_last_24_hours_every_run(make_db):
    """RSS bills per feed, not per item: read everything recent; the DB drops posts already seen."""
    routes = _all_routes()
    db = make_db()
    gw = FakeGateway(routes)
    scrape(gw, load_prefs(), db, NOW)
    rss_start = next(c for c in gw.calls if c[0] == "POST" and ACTORS["rss"] in c[2])
    assert rss_start[3]["filterByDate"] == "2026-11-26T14:48:00Z"
