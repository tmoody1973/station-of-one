import json

from station.config import load_prefs
from station.steps.page import embed_url, latest_picks, render_front
from tests.test_story_page import _newscast

PICKS = {"day": "2026-11-27", "picks": [
    {"source": "NPR Music", "kind": "youtube", "embed_id": "lN96f4SwJyk", "title": 'Patti <b>"Smith"</b>', "artist": "NPR Music",
     "url": "https://www.youtube.com/watch?v=lN96f4SwJyk", "published_at": "", "score": 0.9},
    {"source": "Sub Pop Records", "kind": "bandcamp", "embed_id": "2232478881", "title": "Harmacy", "artist": "Sebadoh",
     "url": "javascript:alert(1)", "published_at": "", "score": 0.7}]}


def test_embed_url_built_from_validated_id_only():
    assert embed_url({"kind": "youtube", "embed_id": "lN96f4SwJyk"}) == "https://www.youtube-nocookie.com/embed/lN96f4SwJyk?autoplay=1"
    assert embed_url({"kind": "bandcamp", "embed_id": "2232478881"}).startswith("https://bandcamp.com/EmbeddedPlayer/album=2232478881/")
    assert embed_url({"kind": "youtube", "embed_id": 'x"><script>'}) == ""
    assert embed_url({"kind": "bandcamp", "embed_id": "12a"}) == "" and embed_url({"kind": "other", "embed_id": "1"}) == ""


def test_picks_escape_text_and_build_embed_from_id():  # Review Focus 1
    n = _newscast()
    html = render_front(n, [n], load_prefs(), picks=PICKS)
    assert "Patti &lt;b&gt;&#34;Smith&#34;&lt;/b&gt;" in html or "Patti &lt;b&gt;&quot;Smith&quot;&lt;/b&gt;" in html
    assert '"src": "https://www.youtube-nocookie.com/embed/lN96f4SwJyk?autoplay=1"' in html  # in the shared player's data-play
    assert "javascript:alert" not in html


def test_no_iframe_before_tap():
    n = _newscast()
    html = render_front(n, [n], load_prefs(), picks=PICKS)
    assert "<iframe" not in html.split("<script")[0] and "music picks" in html.lower()


def test_no_section_without_picks():
    n = _newscast()
    assert "data-embed" not in render_front(n, [n], load_prefs())


def test_latest_picks_reads_newest_file(tmp_path):
    assert latest_picks(tmp_path / "none") is None
    (tmp_path / "2026-11-26.json").write_text(json.dumps({"day": "2026-11-26", "picks": [{"kind": "youtube", "embed_id": "lN96f4SwJyk"}]}))
    (tmp_path / "2026-11-27.json").write_text(json.dumps({"day": "2026-11-27", "picks": []}))
    assert latest_picks(tmp_path)["day"] == "2026-11-26"   # an empty day keeps the last real picks


def test_settings_list_music_picks_sources():
    from station.steps.page import render_settings
    html = render_settings(load_prefs(), {})
    assert "Music picks" in html and "subpop" in html


def test_malformed_newest_picks_file_falls_back(tmp_path):  # review Important 1
    (tmp_path / "2026-11-26.json").write_text(json.dumps({"day": "2026-11-26", "picks": [{"kind": "youtube", "embed_id": "lN96f4SwJyk"}]}))
    (tmp_path / "2026-11-27.json").write_text('{"day": "2026-11-27", "picks": [')
    assert latest_picks(tmp_path)["day"] == "2026-11-26"


def test_future_dated_picks_are_ignored(tmp_path):  # review Minor 2
    (tmp_path / "2026-11-27.json").write_text(json.dumps({"day": "2026-11-27", "picks": [{"kind": "youtube", "embed_id": "lN96f4SwJyk"}]}))
    (tmp_path / "2026-12-01.json").write_text(json.dumps({"day": "2026-12-01", "picks": [{"kind": "youtube", "embed_id": "_l1DbqVacBc"}]}))
    assert latest_picks(tmp_path, today="2026-11-27")["day"] == "2026-11-27"
