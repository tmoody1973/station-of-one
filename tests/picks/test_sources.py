from datetime import UTC, datetime

from station.picks.sources import Pick, album_id, bandcamp_candidates, youtube_candidates, youtube_id
from station.steps.scrape import ACTORS
from tests.fakes import FakeGateway, ok

NOW = datetime(2026, 11, 27, 17, tzinfo=UTC)


def _apify(actor: str, items, status=200):
    return {("POST", "apify", f"/v2/actors/{actor}/runs"): [ok({"data": {"id": "r", "status": "SUCCEEDED", "defaultDatasetId": "d", "usageTotalUsd": 0.0003}}, status=status)],
            ("GET", "apify", "/v2/datasets/d/items"): [ok(items)]}


def test_youtube_id_forms():  # Review Focus 3
    assert youtube_id("https://www.youtube.com/watch?v=lN96f4SwJyk") == "lN96f4SwJyk"
    assert youtube_id("https://youtu.be/lN96f4SwJyk?t=3") == "lN96f4SwJyk"
    assert youtube_id("https://www.youtube.com/shorts/xZeIozsa6Z8") == "xZeIozsa6Z8"
    assert youtube_id("https://www.youtube.com/embed/_l1DbqVacBc") == "_l1DbqVacBc"
    assert youtube_id("https://www.youtube.com/playlist?list=PL123") is None
    assert youtube_id("https://www.youtube.com/watch?v=short") is None
    assert youtube_id('https://www.youtube.com/watch?v=lN96f4Sw"><') is None


def test_album_id_missing_is_dropped():  # Review Focus 2
    assert album_id({"id": "2250227950"}) == "2250227950"
    assert album_id({"id": ""}) is None and album_id({}) is None
    assert album_id({"id": "12a"}) is None and album_id({"id": "1" * 13}) is None


def test_youtube_candidates_from_rss_items():
    items = [
        {"feed_title": "NPR Music", "item_title": "Patti Smith: Tiny Desk Concert", "item_link": "https://www.youtube.com/watch?v=lN96f4SwJyk",
         "item_published": "2026-11-25T10:00:27Z", "item_author": "NPR Music"},
        {"feed_title": "NPR Music", "item_title": "A short", "item_link": "https://www.youtube.com/shorts/xZeIozsa6Z8",
         "item_published": "2026-11-24T20:20:16Z", "item_author": "NPR Music"},
        {"feed_title": "KEXP", "item_title": "Old one", "item_link": "https://www.youtube.com/watch?v=_l1DbqVacBc",
         "item_published": "2026-10-01T10:00:00Z", "item_author": "KEXP"}]
    picks, notes = youtube_candidates(FakeGateway(_apify(ACTORS["rss"], items)), ["UC1"], now=NOW)
    assert picks == [Pick("NPR Music", "youtube", "lN96f4SwJyk", "Patti Smith: Tiny Desk Concert", "NPR Music",
                          "https://www.youtube.com/watch?v=lN96f4SwJyk", "2026-11-25T10:00:27Z")]
    assert notes == []


def test_bandcamp_candidates_from_cheerio_items():
    items = [{"url": "https://stonesthrow.bandcamp.com/music", "label": "Stones Throw", "items": [
                {"id": "2250227950", "title": "THE BPM Remixes", "artist": "Sudan Archives", "href": "https://sudanarchives.bandcamp.com/album/the-bpm-remixes?label=1"},
                {"id": "", "title": "Merch", "artist": "", "href": "https://x.bandcamp.com/merch"},
                {"id": "1230255947", "title": "Tomorrow's World", "artist": "", "href": "javascript:alert(1)"}]},
             {"url": "https://warp.bandcamp.com/music", "label": "Midnight, by Warp", "items": []}]
    picks, notes = bandcamp_candidates(FakeGateway(_apify("apify~cheerio-scraper", items)), ["stonesthrow", "warp"])
    assert [(p.embed_id, p.artist, p.source) for p in picks] == [("2250227950", "Sudan Archives", "Stones Throw"),
                                                                 ("1230255947", "Stones Throw", "Stones Throw")]
    assert picks[1].url == "https://stonesthrow.bandcamp.com/music"   # unsafe link replaced by the label page
    assert any("warp" in n for n in notes)


def test_a_failed_run_is_a_note():
    gw = FakeGateway({("POST", "apify", f"/v2/actors/{ACTORS['rss']}/runs"): [ok({"error": "x"}, status=500)]})
    picks, notes = youtube_candidates(gw, ["UC1"], now=NOW)
    assert picks == [] and "youtube" in notes[0]
