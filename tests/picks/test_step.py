import json
from datetime import UTC, datetime

import pytest

from station.config import load_prefs
from station.manager import FALLBACKS, SKIP_MEANS
from station.picks.step import make_picks
from station.steps.scrape import ACTORS
from station.store import open_db
from tests.fakes import FakeGateway, ok

NOW = datetime(2026, 11, 27, 13, tzinfo=UTC)
YT = [{"feed_title": "NPR Music", "item_title": "Patti Smith: Tiny Desk", "item_link": "https://www.youtube.com/watch?v=lN96f4SwJyk",
       "item_published": "2026-11-25T10:00:27Z", "item_author": "NPR Music"},
      {"feed_title": "KEXP", "item_title": "Live on KEXP", "item_link": "https://www.youtube.com/watch?v=_l1DbqVacBc",
       "item_published": "2026-11-24T10:00:00Z", "item_author": "KEXP"}]
BC = [{"url": "https://subpop.bandcamp.com/music", "label": "Sub Pop Records",
       "items": [{"id": "2232478881", "title": "Harmacy", "artist": "Sebadoh", "href": "https://sebadoh.bandcamp.com/album/harmacy"}]}]


def _run(dataset):
    return [ok({"data": {"id": "r", "status": "SUCCEEDED", "defaultDatasetId": dataset, "usageTotalUsd": 0.0003}})]


def _gw(bandcamp_ok=True):
    jev = ok({"model": "jev-1", "answers": {f"interest_{i}": {"type": "noul", "noul": s} for i, s in enumerate([0.9, 0.6, 0.7])}})
    return FakeGateway({
        ("POST", "apify", f"/v2/actors/{ACTORS['rss']}/runs"): _run("yt"),
        ("GET", "apify", "/v2/datasets/yt/items"): [ok(YT)],
        ("POST", "apify", "/v2/actors/apify~cheerio-scraper/runs"): _run("bc") if bandcamp_ok else [ok({"error": "x"}, status=500)],
        ("GET", "apify", "/v2/datasets/bc/items"): [ok(BC)],
        ("POST", "typesafe", "/v1/systemone"): [jev]})


@pytest.fixture
def db(tmp_path):
    d = open_db(tmp_path / "station.db")
    yield d
    d.close()


def test_picks_file_written_and_decisions_logged(tmp_path, db):
    out = make_picks(_gw(), load_prefs(), db, "2026-11-27", tmp_path / "picks", now=NOW)
    saved = json.loads((tmp_path / "picks" / "2026-11-27.json").read_text())
    assert saved == out and [p["embed_id"] for p in out["picks"]] == ["lN96f4SwJyk", "2232478881", "_l1DbqVacBc"]
    assert out["picks"][0]["score"] == 0.9 and out["model"] == "jev-1"
    assert db.execute("SELECT COUNT(*) FROM decisions WHERE question_id = 'interest'").fetchone()[0] == 3


def test_picks_survive_one_source_failing(tmp_path, db):  # Review Focus 4
    out = make_picks(_gw(bandcamp_ok=False), load_prefs(), db, "2026-11-27", tmp_path / "picks", now=NOW)
    assert {p["kind"] for p in out["picks"]} == {"youtube"}
    assert any("bandcamp" in n for n in out["notes"])


def test_yesterdays_picks_are_not_repeated(tmp_path, db):
    root = tmp_path / "picks"
    root.mkdir()
    (root / "2026-11-26.json").write_text(json.dumps({"picks": [{"kind": "youtube", "embed_id": "lN96f4SwJyk"}]}))
    out = make_picks(_gw(), load_prefs(), db, "2026-11-27", root, now=NOW)
    assert "lN96f4SwJyk" not in [p["embed_id"] for p in out["picks"]]


def test_first_hour_runs_picks_after_table(monkeypatch):
    from station import build as build_mod
    from station.__main__ import main

    got = []
    monkeypatch.setattr(build_mod, "build", lambda hour, **kw: got.append(kw.get("steps")))
    main(["build", "--hour", "2026-11-27T07"])
    assert got[0][-2:] == ["table", "picks"]
    assert FALLBACKS["picks"] == ["retry", "skip"] and "newscasts are unaffected" in SKIP_MEANS["picks"]


def test_prefs_load_music_picks():
    mp = load_prefs().music_picks
    assert mp.count == 3 and "subpop" in mp.bandcamp_labels and len(mp.youtube_channels) == 3


def test_chosen_bandcamp_picks_get_notes_and_a_writeup(tmp_path, db):
    notes = "Sebadoh reissue the 1996 album Harmacy with demos and live tracks. " * 4
    gw = _gw()
    gw.routes[("POST", "apify", "/v2/actors/apify~cheerio-scraper/runs")] = [
        ok({"data": {"id": "r", "status": "SUCCEEDED", "defaultDatasetId": "bc", "usageTotalUsd": 0.0003}}),
        ok({"data": {"id": "r2", "status": "SUCCEEDED", "defaultDatasetId": "about", "usageTotalUsd": 0.0004}})]
    gw.routes[("GET", "apify", "/v2/datasets/about/items")] = [ok([{"url": "https://sebadoh.bandcamp.com/album/harmacy", "text": notes}])]
    gw.routes[("POST", "ollama", "/api/chat")] = [ok({"message": {"content": "According to the Bandcamp page, Sebadoh reissue Harmacy.\n\nIt is not yet clear when."}})]
    out = make_picks(gw, load_prefs(), db, "2026-11-27", tmp_path / "picks", now=NOW)
    bc = next(p for p in out["picks"] if p["kind"] == "bandcamp")
    yt = next(p for p in out["picks"] if p["kind"] == "youtube")
    assert bc["description"].startswith("Sebadoh reissue") and bc["paragraphs"][0].startswith("According to the Bandcamp page")
    assert yt["paragraphs"] is None   # no description to write from
