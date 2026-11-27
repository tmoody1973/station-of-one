import base64
import json
from contextlib import closing

import pytest

from station.build import STEPS
from station.config import load_prefs
from station.manager import FALLBACKS, SKIP_MEANS
from station.steps.illustrate import PATH as GEMINI
from station.steps.story import make_stories
from station.store import Post, open_db, upsert_posts
from tests.fakes import FakeGateway, ok

JPEG = b"\xff\xd8\xff" + b"0" * 16
URLS = {"s1": "https://urbanmilwaukee.com/a", "s2": "https://wisconsinexaminer.com/b", "s3": "https://www.reddit.com/r/x/c"}


def _story(sid: str, image=None) -> dict:
    return {"id": sid, "beat_id": "mke", "headline": f"Headline {sid}", "summary": "Sum.", "image": image,
            "score_matter_week": 0.5, "seconds": 30, "chapter_start_ms": 0,
            "sources": [{"post_id": sid, "url": URLS[sid], "author": "user7", "source_name": "Urban Milwaukee"}]}


@pytest.fixture
def tmp_run(tmp_path):
    run = tmp_path / "runs" / "2026-11-27T10"
    run.mkdir(parents=True)
    (run / "newscast.json").write_text(json.dumps({"id": run.name, "stories": [
        _story("s1", image="https://urbanmilwaukee.com/scraped.jpg"), _story("s2"), _story("s3")]}))
    db = open_db(tmp_path / "station.db")
    upsert_posts(db, [Post(s, "Urban Milwaukee", "mke", "story", "user7", f"T {s}", u, "Posters say things " * 5,
                           "2026-11-27T15:00:00Z", {}, "public") for s, u in URLS.items()])
    db.commit()
    yield run, db
    db.close()


def _gw(chat_ok=True, gemini_ok=True):
    chat = ok({"message": {"content": "Posters on Urban Milwaukee say X.\n\nIt is not yet clear why."}}) if chat_ok \
        else ok({"message": {"content": "X happened.\n\nY happened.\n\nUnclear."}})
    gem = ok({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/jpeg",
                                                                    "data": base64.b64encode(JPEG).decode()}}]}}]}) \
        if gemini_ok else ok({"error": "boom"}, status=500)
    return FakeGateway({
        ("POST", "ollama", "/api/chat"): [chat],
        ("POST", "apify", "/v2/actors/apify~cheerio-scraper/runs"): [ok({"data": {"id": "r", "status": "SUCCEEDED", "defaultDatasetId": "d", "usageTotalUsd": 0.012}})],
        ("GET", "apify", "/v2/datasets/d/items"): [ok([{"url": URLS["s2"], "image": "https://wisconsinexaminer.com/p.jpg"}])],
        ("POST", "gemini", GEMINI): [gem]})


def test_story_step_prefers_scraped_then_photo_then_illustration(tmp_run):
    run, db = tmp_run
    stories, counts = make_stories(_gw(), run, load_prefs(), db)
    assert stories["s1"]["image"] == {"kind": "photo", "src": "https://urbanmilwaukee.com/scraped.jpg",
                                      "credit": "Urban Milwaukee", "link": URLS["s1"]}
    assert stories["s2"]["image"]["kind"] == "photo" and stories["s2"]["image"]["src"] == "https://wisconsinexaminer.com/p.jpg"
    assert stories["s3"]["image"]["kind"] == "illustration" and stories["s3"]["image"]["src"].startswith("/art/2026-11-27T10-")
    assert (run / "site" / stories["s3"]["image"]["src"].lstrip("/")).read_bytes() == JPEG
    assert stories["s1"]["paragraphs"] == ["Posters on Urban Milwaukee say X.", "It is not yet clear why."]
    assert counts == {"articles": 3, "photos": 2, "illustrations": 1, "apify_usd": 0.012, "notes": []}
    assert json.loads((run / "stories.json").read_text()) == stories


def test_story_step_survives_partial_failures(tmp_run):  # Review Focus 4
    run, db = tmp_run
    stories, counts = make_stories(_gw(chat_ok=False, gemini_ok=False), run, load_prefs(), db)
    assert stories["s3"]["image"] is None and stories["s2"]["paragraphs"] is None
    assert stories["s2"]["image"]["kind"] == "photo"  # the photo lookup still worked
    assert counts["articles"] == 0 and counts["illustrations"] == 0
    assert any("illustration" in n for n in counts["notes"]) and any("article dropped" in n for n in counts["notes"])


def test_steps_order_has_story_after_assemble():
    assert STEPS.index("story") == STEPS.index("assemble") + 1
    assert FALLBACKS["story"] == ["retry", "skip"] and "newscast is unaffected" in SKIP_MEANS["story"]
