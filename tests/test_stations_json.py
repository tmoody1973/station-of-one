import json

from station.config import load_prefs
from station.steps.stations import stations_json
from tests.test_story_page import _newscast


def _stations(tmp_path):
    """A stations folder for these tests: the real Rhythm Lab and jazz configs plus an active UK jazz sampler
    (the real one is retired, but the strip still has to handle sampler stations)."""
    import shutil
    from station.radio.model import STATIONS_ROOT
    root = tmp_path / "stations"
    root.mkdir()
    for f in ("rhythm-lab.json", "jazz.json"):
        shutil.copy(STATIONS_ROOT / f, root / f)
    cfg = json.loads((STATIONS_ROOT / "uk-jazz.json").read_text())
    cfg.pop("retired", None)
    (root / "uk-jazz.json").write_text(json.dumps(cfg))
    return root


def test_stations_json_shape(tmp_path):
    (tmp_path / "uk-jazz").mkdir()
    tracks = [{"artist": f"Artist {i}", "title": f"Song {i}", "duration_ms": 1} for i in range(4)]
    (tmp_path / "uk-jazz" / "latest.json").write_text(json.dumps({"station": "uk-jazz", "block": {"tracks": tracks}}))
    out = stations_json(load_prefs(), _newscast(), radio_root=tmp_path, stations_root=_stations(tmp_path))
    news, jazz = out["stations"][0], next(s for s in out["stations"] if s["id"] == "uk-jazz")
    assert news["kind"] == "news" and news["play"]["src"].startswith("/audio/") and "10:00 am" in news["on_now"]
    assert news["play"]["kind"] == "newscast" and news["page"] == "/index.html"
    assert jazz["id"] == "uk-jazz" and jazz["name"] == "ONE Jazz" and jazz["on_now"] == "Artist 0 · Song 0"
    assert jazz["next"]["title"] == "Artist 1 · Song 1" and jazz["page"] == "/radio/uk-jazz/index.html"
    assert "London" in jazz["description"] and "play" not in jazz   # music plays on its page until Apple Music sign-in


def test_station_without_a_set_is_not_listed(tmp_path):  # no dead link to a page that was never published
    out = stations_json(load_prefs(), _newscast(), radio_root=tmp_path, stations_root=_stations(tmp_path))
    assert [s["id"] for s in out["stations"]] == ["news"]


def test_flagship_first(tmp_path):
    for sid in ("uk-jazz", "rhythm-lab"):
        (tmp_path / sid).mkdir()
        (tmp_path / sid / "latest.json").write_text(json.dumps({"block": {"tracks": [{"artist": "A", "title": "T"}]}}))
    out = stations_json(load_prefs(), _newscast(), radio_root=tmp_path, stations_root=_stations(tmp_path))
    assert [s["id"] for s in out["stations"]][:2] == ["news", "rhythm-lab"] and "uk-jazz" in [s["id"] for s in out["stations"]]


def test_torn_latest_json_is_listed_quietly(tmp_path):  # review I4: a half-written file never stops the front page
    (tmp_path / "uk-jazz").mkdir()
    (tmp_path / "uk-jazz" / "latest.json").write_text('{"station": "uk-ja')
    out = stations_json(load_prefs(), _newscast(), radio_root=tmp_path, stations_root=_stations(tmp_path))
    jazz = next(s for s in out["stations"] if s["id"] == "uk-jazz")
    assert jazz["on_now"] == "" and out["stations"][0]["id"] == "news"


def test_clock_station_chip_tunes_in(tmp_path):  # Plan C Task 4
    for sid in ("uk-jazz", "rhythm-lab"):
        (tmp_path / sid).mkdir()
        (tmp_path / sid / "latest.json").write_text(json.dumps({"block": {"tracks": [{"artist": "A", "title": "T"}]}}))
    out = {s["id"]: s for s in stations_json(load_prefs(), _newscast(), radio_root=tmp_path, stations_root=_stations(tmp_path))["stations"]}
    assert out["rhythm-lab"]["play"] == {"kind": "station", "src": "/data/radio/rhythm-lab/queue.json", "title": "Rhythm Lab",
                                         "label": "Rhythm Lab · live"}
    assert "play" not in out["uk-jazz"]


def _write(tmp, sid, tracks):
    (tmp / sid).mkdir(exist_ok=True)
    (tmp / sid / "latest.json").write_text(json.dumps({"block": {"tracks": tracks}}))


def test_strip_entries_have_now_next_and_description(tmp_path):  # live-playlist Task 2 (KCRW pattern)
    tracks = [{"artist": f"Artist {i}", "title": f"Song {i}", "artwork_url": f"https://a/{i}.jpg", "duration_ms": 1} for i in range(3)]
    _write(tmp_path, "uk-jazz", tracks)
    out = {s["id"]: s for s in stations_json(load_prefs(), _newscast(), radio_root=tmp_path, stations_root=_stations(tmp_path))["stations"]}
    news, jazz = out["news"], out["uk-jazz"]
    assert news["now"]["at"] == "10:00 am" and news["now"]["title"] and news["next"] == {"at": "11:00 am", "title": "The next newscast"}
    assert "five minutes on the hour" in news["description"]
    assert jazz["now"] == {"at": "", "title": "Artist 0 · Song 0", "art": "https://a/0.jpg"} and jazz["next"]["title"] == "Artist 1 · Song 1"


def test_news_next_is_the_next_newscast(tmp_path):
    n = _newscast()
    n["hour_local"] = "2026-11-27T19:00:00-06:00"   # the last newscast of the day
    news = stations_json(load_prefs(), n, radio_root=tmp_path, stations_root=_stations(tmp_path))["stations"][0]
    assert news["next"]["at"] == "7:00 am"


def test_clock_station_publishes_its_schedule(tmp_path):
    tracks = [{"artist": "A", "title": f"T{i}", "song_id": f"{i}", "starts_at": f"2026-11-27T22:0{i}:00+00:00",
               "ends_at": f"2026-11-27T22:0{i}:59+00:00", "at": f"4:0{i} pm", "artwork_url": "https://a.jpg", "duration_ms": 1}
              for i in range(3)]
    _write(tmp_path, "rhythm-lab", tracks)
    rl = next(s for s in stations_json(load_prefs(), _newscast(), radio_root=tmp_path, stations_root=_stations(tmp_path))["stations"] if s["id"] == "rhythm-lab")
    assert rl["schedule"][1] == {"starts_at": "2026-11-27T22:01:00+00:00", "ends_at": "2026-11-27T22:01:59+00:00", "at": "4:01 pm",
                                 "song_id": "1", "title": "T1", "artist": "A", "art": "https://a.jpg"}
    assert rl["now"]["title"] == "A · T0" and rl["play"]["kind"] == "station"


def test_news_entry_carries_its_hour(tmp_path):  # Plan B2 Task 5: the browser skips a newscast over 70 minutes old
    n = _newscast()
    news = stations_json(load_prefs(), n, radio_root=tmp_path, stations_root=_stations(tmp_path))["stations"][0]
    assert news["id"] == "news" and news["hour_local"] == n["hour_local"]
