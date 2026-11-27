from station.config import load_prefs
from station.steps.page import embed_url, pick_path, render_pick

PICKS = {"day": "2026-11-27", "picks": [
    {"source": "Ninja Tune", "kind": "bandcamp", "embed_id": "3626022129", "title": "Chaos Theory (20th Anniversary Reissue)",
     "artist": "Amon Tobin", "url": "https://amontobin.bandcamp.com/album/chaos-theory", "published_at": "", "score": 0.73,
     "description": "notes", "paragraphs": ["According to the Bandcamp page, a <b>reissue</b>.", "Not yet clear."]},
    {"source": "KEXP", "kind": "youtube", "embed_id": "7_0iN8skvJc", "title": "Hermanos Gutiérrez - Full Performance",
     "artist": "KEXP", "url": "https://www.youtube.com/watch?v=7_0iN8skvJc", "published_at": "", "score": 0.76,
     "description": "", "paragraphs": None}]}


def test_pick_paths_are_unique_and_readable():
    assert pick_path("2026-11-27", 0, "Amon Tobin", "Chaos Theory (20th Anniversary Reissue)") == \
        "m/2026-11-27/1-amon-tobin-chaos-theory-20th-anniversary-reissue/index.html"
    assert pick_path("2026-11-27", 1, "", "") == "m/2026-11-27/2-pick/index.html"


def test_big_embeds():
    assert "tracklist=true" in embed_url(PICKS["picks"][0], big=True)
    assert "tracklist=false" in embed_url(PICKS["picks"][0])


def test_pick_page_has_big_player_on_tap_writeup_and_score():
    html = render_pick(PICKS, PICKS["picks"][0], load_prefs())
    assert "<iframe" not in html.split("<script")[0]
    assert f'data-embed="{embed_url(PICKS["picks"][0], big=True)}"' in html
    assert "&lt;b&gt;reissue&lt;/b&gt;" in html and "73%" in html
    assert "Hermanos Gutiérrez" in html   # more picks
    assert 'href="https://amontobin.bandcamp.com/album/chaos-theory"' in html


def test_pick_page_without_writeup():
    html = render_pick(PICKS, PICKS["picks"][1], load_prefs())
    assert "youtube-nocookie.com/embed/7_0iN8skvJc" in html and "write-up" in html.lower()
