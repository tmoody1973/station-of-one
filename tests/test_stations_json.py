import json

from station.config import load_prefs
from station.steps.stations import stations_json
from tests.test_story_page import _newscast


def test_stations_json_shape(tmp_path):
    (tmp_path / "uk-jazz").mkdir()
    tracks = [{"artist": f"Artist {i}", "title": f"Song {i}", "duration_ms": 1} for i in range(4)]
    (tmp_path / "uk-jazz" / "latest.json").write_text(json.dumps({"station": "uk-jazz", "block": {"tracks": tracks}}))
    out = stations_json(load_prefs(), _newscast(), radio_root=tmp_path)
    news, jazz = out["stations"][0], next(s for s in out["stations"] if s["id"] == "uk-jazz")
    assert news["kind"] == "news" and news["play"]["src"].startswith("/audio/") and "10:00 am" in news["on_now"]
    assert news["play"]["kind"] == "newscast" and news["page"] == "/index.html"
    assert jazz["id"] == "uk-jazz" and jazz["name"] == "ONE Jazz" and jazz["on_now"] == "Artist 0 · Song 0"
    assert jazz["next"] == ["Artist 1 · Song 1", "Artist 2 · Song 2"] and jazz["page"] == "/radio/uk-jazz/index.html"
    assert "London" in jazz["description"] and "play" not in jazz   # music plays on its page until Apple Music sign-in


def test_station_without_a_set_is_not_listed(tmp_path):  # no dead link to a page that was never published
    out = stations_json(load_prefs(), _newscast(), radio_root=tmp_path)
    assert [s["id"] for s in out["stations"]] == ["news"]


def test_flagship_first(tmp_path):
    for sid in ("uk-jazz", "rhythm-lab"):
        (tmp_path / sid).mkdir()
        (tmp_path / sid / "latest.json").write_text(json.dumps({"block": {"tracks": [{"artist": "A", "title": "T"}]}}))
    out = stations_json(load_prefs(), _newscast(), radio_root=tmp_path)
    assert [s["id"] for s in out["stations"]] == ["news", "rhythm-lab", "uk-jazz"]


def test_torn_latest_json_is_listed_quietly(tmp_path):  # review I4: a half-written file never stops the front page
    (tmp_path / "uk-jazz").mkdir()
    (tmp_path / "uk-jazz" / "latest.json").write_text('{"station": "uk-ja')
    out = stations_json(load_prefs(), _newscast(), radio_root=tmp_path)
    jazz = next(s for s in out["stations"] if s["id"] == "uk-jazz")
    assert jazz["on_now"] == "" and out["stations"][0]["id"] == "news"


def test_clock_station_chip_tunes_in(tmp_path):  # Plan C Task 4
    for sid in ("uk-jazz", "rhythm-lab"):
        (tmp_path / sid).mkdir()
        (tmp_path / sid / "latest.json").write_text(json.dumps({"block": {"tracks": [{"artist": "A", "title": "T"}]}}))
    out = {s["id"]: s for s in stations_json(load_prefs(), _newscast(), radio_root=tmp_path)["stations"]}
    assert out["rhythm-lab"]["play"] == {"kind": "station", "src": "/data/radio/rhythm-lab/queue.json", "title": "Rhythm Lab",
                                         "label": "Rhythm Lab · live"}
    assert "play" not in out["uk-jazz"]
