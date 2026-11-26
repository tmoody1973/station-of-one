import copy
import json
import re

from station.config import load_prefs
from station.steps.page import hour_path, page, render_front, render_hour
from tests.conftest import load_fixture

PREFS = load_prefs()


def newscast(hour="2026-11-26T17", **over):
    n = copy.deepcopy(load_fixture("newscast_1700.json"))
    n["id"] = hour
    n["hour_local"] = f"{hour}:00:00-06:00"
    n.update(over)
    return n


def test_hour_path():
    assert hour_path("2026-11-26T17") == "h/2026-11-26/1700/index.html"


def test_front_page_escapes_post_html():  # Review Focus 1
    n = newscast()
    n["stories"][0]["headline"] = "<script>alert(1)</script>"
    n["stories"][1]["sources"][0]["source_name"] = 'A "quoted" & <b>bold</b> outlet'
    html = render_front(n, [n], PREFS)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>bold</b>" not in html


def test_links_end_in_index_html():  # Tigris serves no index documents
    html = render_front(newscast(), [newscast(), newscast("2026-11-26T16")], PREFS)
    internal = [h for h in re.findall(r'href="([^"]+)"', html) if h.startswith("/") and not h.startswith("//")]
    files = [h.split("#")[0] for h in internal]  # a #fragment after a named file is fine
    assert files and all(f.endswith("index.html") or f.endswith(".mp3") for f in files)


def test_footer_synthetic_line():
    html = render_front(newscast(), [newscast()], PREFS)
    assert "Voices are synthetic. This show is machine-edited from public posts, with every source linked." in html


def test_play_from_story_uses_chapter_start():
    n = newscast()
    html = render_front(n, [n], PREFS)
    lead = n["stories"][0]
    assert f'data-start-ms="{lead["chapter_start_ms"]}"' in html
    assert "Play from this story" in html and f'src="/audio/{n["id"]}.mp3"' in html


def test_today_list_newest_first():
    html = render_front(newscast(), [newscast("2026-11-26T15"), newscast("2026-11-26T17"), newscast("2026-11-26T16")], PREFS)
    times = re.findall(r'class="hour-time">([^<]+)<', html)
    assert times == ["5:00 pm", "4:00 pm", "3:00 pm"]


def test_counts_and_score_shown():
    n = newscast()
    html = render_front(n, [n], PREFS)
    assert f'{n["counts"]["posts_read_today"]:,}' in html and "posts read so you didn" in html
    assert f'Jev: {round(n["stories"][0]["score_matter_week"] * 100)}% likely to matter in a week' in html


def test_sources_listed_as_links():
    n = newscast()
    html = render_front(n, [n], PREFS)
    for s in n["stories"][0]["sources"]:
        assert f'href="{s["url"]}"' in html


def test_hour_page_names_the_newscast():
    html = render_hour(newscast(), PREFS)
    assert "5:00 pm newscast" in html and "Thursday, November 26" in html


def test_page_writes_front_and_hour_files(tmp_path):
    runs = tmp_path / "runs"
    for h in ("2026-11-26T16", "2026-11-26T17"):
        (runs / h).mkdir(parents=True)
        (runs / h / "newscast.json").write_text(json.dumps(newscast(h)))
    written = page(runs / "2026-11-26T17", PREFS, runs_root=runs)
    names = sorted(str(p.relative_to(runs / "2026-11-26T17" / "site")) for p in written)
    assert names == ["h/2026-11-26/1700/index.html", "index.html", "player.js"]


def test_only_http_links_render():  # scraped URLs are untrusted
    n = newscast()
    n["stories"][0]["sources"] = [{"post_id": "x", "url": "javascript:alert(1)", "author": None,
                                   "source_name": "Evil", "posted_at": ""}]
    html = render_front(n, [n], PREFS)
    assert "javascript:" not in html and 'href="#"' in html
