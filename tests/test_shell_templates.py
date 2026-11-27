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


def _with_content() -> dict[str, str]:
    from station.steps.page import render_pick
    from station.table.build import render_table
    prefs = load_prefs()
    out = dict(pages())
    track = {"candidate_id": "c", "song_id": "1", "artist": "A", "title": "T's", "album": "Al", "release_date": "2024-01-01",
             "duration_ms": 1, "preview_url": "https://audio-ssl.itunes.apple.com/p.m4a", "apple_url": "https://music.apple.com/x",
             "artwork_url": "https://a", "fit": 0.9, "note": "n", "source_url": "https://s", "era": "new"}
    out["sampler"] = render_sampler(load_station("uk-jazz"), Block("uk-jazz", "b", "2026-11-27T18:00:00+00:00", [track]), {}, prefs)
    pick = {"source": "Ninja Tune", "kind": "bandcamp", "embed_id": "3626022129", "title": "Chaos Theory", "artist": "Amon Tobin",
            "url": "https://x", "score": 0.7, "paragraphs": None}
    out["pick"] = render_pick({"day": "2026-11-27", "picks": [pick]}, pick, prefs)
    ep = {"day": "2026-11-26", "question": "Is it 'good'?", "positions": {"anchor": "a", "uncle": "u"},
          "thread": {"title": "t", "source": "Hacker News", "url": "https://x"}, "rounds": [],
          "verdict": {"winner": "draw", "anchor": 1.0, "uncle": 1.0}, "record": {"anchor": 0, "uncle": 0, "draw": 1},
          "chapters": [{"title": "The question", "start_ms": 0, "end_ms": 21000}, {"title": "Round 1", "start_ms": 41000, "end_ms": 71000}],
          "audio": {"duration_ms": 150000, "bytes": 1, "key": "audio/table-2026-11-26-abc.mp3"}}
    out["table"] = render_table(ep, prefs)
    return out


def test_no_inline_page_scripts_left():
    for name, html in _with_content().items():
        scripts = re.findall(r"<script[^>]*>", html)
        assert scripts == ['<script src="/shell.js" defer>'], (name, scripts)
        assert html.count("<audio") == 1, name   # only the player bar's


def test_controls_say_what_to_play():
    h = _with_content()
    assert '"kind": "preview"' in h["sampler"] and "audio-ssl.itunes.apple.com/p.m4a" in h["sampler"]
    assert '"kind": "table"' in h["table"] and '"start": 41.0' in h["table"]
    assert '"kind": "story"' in h["story"] and '"start": 9.0' in h["story"]
    assert "data-stage-embed=" in h["pick"] and '"kind": "embed"' in h["pick"]


def test_data_play_attributes_escaped():
    h = _with_content()
    assert "T\\u0027s" in h["sampler"] and "Is it \\u0027good\\u0027?" in h["table"]


def test_strip_knows_where_its_data_is():
    for name, html in pages().items():
        assert 'id="wone-strip" data-src="/data/stations.json"' in html, name
