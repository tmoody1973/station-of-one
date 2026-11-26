import json

from station.__main__ import main


def test_scrape_cli_writes_posts_json(tmp_path, monkeypatch):
    from station.steps import scrape as scrape_mod
    from station.store import Post

    fake_post = Post("hn:1", "Hacker News", "ai-dev", "story", "u", "T", "https://x", "", "2026-11-27T14:00:00Z", {}, "public")
    monkeypatch.setattr(scrape_mod, "scrape", lambda gw, prefs, db, now: scrape_mod.ScrapeResult([fake_post], {"new_posts": 1}, []))
    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "run"
    assert main(["scrape", "--run", str(run)]) == 0
    assert json.loads((run / "posts.json").read_text())[0]["id"] == "hn:1"
    step = json.loads((run / "run_log.json").read_text())["steps"][0]
    assert (step["name"], step["tool"], step["counts"]["new_posts"]) == ("scrape", "Apify", 1)


def test_dedupe_cli_writes_clusters(tmp_path, monkeypatch):
    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "run"
    run.mkdir()
    post = {"id": "hn:1", "source": "Hacker News", "beat": "ai-dev", "kind": "story", "author": "u", "title": "T",
            "url": "https://ex.com/a", "text": "", "posted_at": "2026-11-27T14:00:00Z", "engagement": {}, "visibility": "public"}
    (run / "posts.json").write_text(json.dumps([post, {**post, "id": "rss:1", "url": "https://ex.com/a?utm_source=x"}]))
    assert main(["dedupe", "--run", str(run)]) == 0
    out = json.loads((run / "clusters.json").read_text())
    assert out["clusters"] == [{"primary_id": "hn:1", "member_ids": ["hn:1", "rss:1"]}] and out["candidates"] == []
    assert json.loads((run / "run_log.json").read_text())["steps"][-1]["counts"] == {"posts": 2, "clusters": 1, "candidates": 0}
