"""WONE 1.0 FM ID block (Tarik picked option B, Nov 26): header on every page, favicon, cover, video."""
from station.config import load_prefs
from station.steps.page import render_control_room, render_front, render_settings
from tests.test_page import newscast
from tests.test_page_extras import RUN_LOG

PREFS = load_prefs()


def test_every_page_has_the_mark_and_favicon():
    n = newscast()
    for html in (render_front(n, [n], PREFS), render_control_room(RUN_LOG, [], n, PREFS), render_settings(PREFS, {})):
        assert 'class="wone-id"' in html and '<link rel="icon" href="/logo.png" type="image/png">' in html
        assert ">1.0<" in html and ">WONE<" in html and 'aria-label="WONE 1.0 FM"' in html
        assert "Archivo+Black" in html  # the logo's typeface is loaded


def test_page_step_ships_the_logo(tmp_path):
    import json

    from station.steps.page import page

    run = tmp_path / "2026-11-26T17"
    run.mkdir()
    (run / "newscast.json").write_text(json.dumps(newscast()))
    page(run, PREFS, runs_root=tmp_path)
    assert (run / "site" / "logo.png").read_bytes()[:4] == b"\x89PNG"


def test_table_page_has_the_logo():
    from station.table.build import render_table
    from tests.table.test_table_build import EPISODE

    assert 'class="wone-id"' in render_table(EPISODE, PREFS)
