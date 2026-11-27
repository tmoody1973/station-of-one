"""Site shell (plan 2026-11-27-site-shell, Task 2): every page carries the masthead with the station strip,
and one player bar, exactly once; nothing autoplays."""
import json
import re

from station.config import load_prefs
from station.radio.model import load_station
from station.radio.page import render_sampler
from station.radio.program import Block
from station.steps import page as pg
from station.table.build import render_table
from tests.test_story_page import _newscast


def pages() -> dict[str, str]:
    prefs = load_prefs()
    n = _newscast()
    pick = {"source": "KEXP", "kind": "youtube", "embed_id": "7_0iN8skvJc", "title": "T", "artist": "A", "url": "https://x", "score": 0.7}
    out = {
        "front": pg.render_front(n, [n], prefs),
        "hour": pg.render_hour(n, prefs),
        "story": pg.render_story(n, n["stories"][0], None, prefs),
        "pick": pg.render_pick({"day": "2026-11-27", "picks": [pick]}, pick, prefs),
        "sampler": render_sampler(load_station("uk-jazz"), Block("uk-jazz", "b", "2026-11-27T18:00:00+00:00", []), {}, prefs),
        "settings": pg.render_settings(prefs, {}),
        "control": pg.render_control_room({"steps": [], "started_at": "2026-11-27T15:00:00+00:00", "total_seconds": 1}, [], n, prefs),
    }
    return out


def test_every_page_has_masthead_strip_and_player():
    for name, html in pages().items():
        assert html.count('id="wone-player"') == 1, name
        assert html.count('id="wone-strip"') == 1, name
        assert html.count('src="/shell.js"') == 1, name
        assert "/player.js" not in html, name


def test_player_markup_has_no_autoplay():
    for name, html in pages().items():
        bar = html[html.index('id="wone-player"'):]
        assert "autoplay" not in bar.split("</audio>")[0], name


def test_front_play_buttons_carry_what_to_play():
    html = pages()["front"]
    attrs = re.findall(r"data-play='([^']*)'", html)
    assert attrs, "front page has play buttons"
    first = json.loads(attrs[0].replace("&#34;", '"').replace("&#39;", "'").replace("&amp;", "&"))
    assert first["src"].startswith("/audio/") and first["start"] == 9.0 and first["kind"] == "story"  # the lead's button


def test_no_old_player_left_on_front():
    html = pages()["front"]
    assert 'id="time"' not in html and 'id="player"' not in html and html.count('data-skip="-15"') == 1
