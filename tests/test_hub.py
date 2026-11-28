"""Music hub plan, Task 1: /music/, one landing page for all music."""
import json
import re

from station.config import load_prefs
from station.steps.page import MUSIC_HUB_PATH, render_hub
from station.steps.stations import stations_json
from tests.test_stations_json import _stations
from tests.test_story_page import _newscast

PREFS = load_prefs()


def stations(tmp_path):
    root = _stations(tmp_path)   # Rhythm Lab, ONE Jazz, an active UK jazz sampler
    retired = json.loads((root / "uk-jazz.json").read_text()) | {"id": "old-sampler", "retired": True}
    (root / "old-sampler.json").write_text(json.dumps(retired))
    for sid in ("rhythm-lab", "jazz", "uk-jazz", "old-sampler"):   # the strip lists only stations that have published
        (tmp_path / sid).mkdir()
        (tmp_path / sid / "latest.json").write_text(json.dumps({"block": {"tracks": [{"artist": "A", "title": f"{sid} song"}]}}))
    return stations_json(PREFS, _newscast(), radio_root=tmp_path, stations_root=root)["stations"]


def pick(title="Odyssey", artist="Nubya Garcia"):
    return {"day": "2026-11-27", "picks": [{"title": title, "artist": artist, "kind": "bandcamp", "source": "Brownswood",
                                             "url": "https://x.bandcamp.com/album/o", "embed": "https://bandcamp.com/EmbeddedPlayer/album=1",
                                             "page": "/m/2026-11-27/1-x/index.html"}]}


def test_hub_lists_music_stations_only(tmp_path):
    ids = re.findall(r'data-now-of="([^"]+)"', render_hub(stations(tmp_path), pick(), PREFS))
    assert ids[0] == "rhythm-lab" and set(ids) == {"rhythm-lab", "jazz", "uk-jazz"} and len(ids) == 3


def test_hub_links_each_station(tmp_path):
    html = render_hub(stations(tmp_path), pick(), PREFS)
    for href in ("/radio/jazz/index.html", "/radio/jazz/meeting/index.html", "/radio/jazz/how-it-works/index.html", "/playlists/index.html"):
        assert f'href="{href}"' in html, href
    plays = [json.loads(p.replace("&#34;", '"').replace("&quot;", '"')) for p in re.findall(r"data-play='([^']+)'", html)]
    assert any(p.get("src") == "/data/radio/jazz/queue.json" for p in plays)


def test_hub_without_picks(tmp_path):
    html = render_hub(stations(tmp_path), None, PREFS)
    assert "arrive with the 7 am newscast" in html and 'class="card pick"' not in html


def test_hub_escapes_text(tmp_path):
    st = stations(tmp_path)
    st[1] = {**st[1], "description": "<i>y</i>"}
    html = render_hub(st, pick(title="<b>x</b>"), PREFS)
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "&lt;i&gt;y&lt;/i&gt;" in html and "<b>x</b>" not in html


def test_hub_path():
    assert MUSIC_HUB_PATH == "music/index.html"
