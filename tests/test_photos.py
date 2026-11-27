from station.steps.photos import clean_image, lookup_urls, preview_images
from tests.fakes import FakeGateway, ok


def story(url: str) -> dict:
    return {"id": url, "sources": [{"post_id": url, "url": url}]}


def test_lookup_skips_social_hosts():
    stories = [story("https://www.reddit.com/r/x/1"), story("https://urbanmilwaukee.com/a"), story("https://bsky.app/p/1"),
               story("https://urbanmilwaukee.com/a"), {"id": "none", "sources": []}]
    assert lookup_urls(stories) == ["https://urbanmilwaukee.com/a"]


def test_resolves_relative_and_drops_unsafe():  # Review Focus 3
    assert clean_image("https://site.com/news/a", "/img/a.jpg") == "https://site.com/img/a.jpg"
    assert clean_image("https://site.com/a", "javascript:alert(1)") is None
    assert clean_image("https://site.com/a", "data:image/png;base64,AAA") is None
    assert clean_image("https://site.com/a", None) is None
    assert clean_image("https://site.com/a", "  ") is None


def test_rejects_logo_like_images():  # Review Focus 2
    for bad in ("https://site.com/logo.png", "https://site.com/static/site-logo-1200.jpg",
                "https://site.com/favicon.ico", "https://site.com/og.svg"):
        assert clean_image("https://site.com/a", bad) is None
    assert clean_image("https://site.com/a", "https://cdn.site.com/2026/11/photo.jpg?w=1200") == "https://cdn.site.com/2026/11/photo.jpg?w=1200"


def _apify(items):
    return {("POST", "apify", "/v2/actors/apify~cheerio-scraper/runs"): [ok({"data": {"id": "r1", "status": "SUCCEEDED", "defaultDatasetId": "d1", "usageTotalUsd": 0.01}})],
            ("GET", "apify", "/v2/datasets/d1/items"): [ok(items)]}


def test_preview_images_maps_actor_items():
    gw = FakeGateway(_apify([{"url": "https://a.com/1", "image": "https://a.com/photo.jpg"},
                             {"url": "https://b.com/2", "image": "/logo.png"}]))
    found, cost = preview_images(gw, ["https://a.com/1", "https://b.com/2"])
    assert found == {"https://a.com/1": "https://a.com/photo.jpg"} and cost == 0.01


def test_preview_images_no_urls_makes_no_call():
    gw = FakeGateway({})
    assert preview_images(gw, []) == ({}, 0.0) and gw.calls == []


def test_preview_images_failed_run_returns_nothing():
    gw = FakeGateway({("POST", "apify", "/v2/actors/apify~cheerio-scraper/runs"): [ok({"error": "nope"}, status=403)]})
    assert preview_images(gw, ["https://a.com/1"]) == ({}, 0.0)
