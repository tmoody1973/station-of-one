from station.config import load_prefs
from station.steps.page import render_front
from tests.test_page import newscast

PREFS = load_prefs()


def test_almost_made_air_lists_cut_stories_with_scores():
    n = newscast()
    n["almost"] = [{"post_id": "a", "title": "Close call <b>story</b>", "url": "https://ex.com/a", "score_matter_week": 0.39},
                   {"post_id": "b", "title": "Unsafe link", "url": "javascript:alert(1)", "score_matter_week": 0.31}]
    html = render_front(n, [n], PREFS)
    assert "Almost made air" in html and "39%" in html and "31%" in html
    assert 'href="https://ex.com/a"' in html and "javascript:" not in html and "&lt;b&gt;story&lt;/b&gt;" in html


def test_almost_hidden_when_empty():
    n = newscast()
    n["almost"] = []
    assert "Almost made air" not in render_front(n, [n], PREFS)
