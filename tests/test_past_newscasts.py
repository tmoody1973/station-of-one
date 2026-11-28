"""Archive (past newscasts) plan, Task 1: /archive/, every aired newscast, newest day first."""
import json
import re

from station.config import load_prefs
from station.steps.page import ARCHIVE_PATH, all_newscasts, render_archive, render_front
from tests.test_page import newscast

PREFS = load_prefs()


def runs(tmp_path, *hours, **over):
    root = tmp_path / "runs"
    for h in hours:
        (root / h).mkdir(parents=True, exist_ok=True)
        (root / h / "newscast.json").write_text(json.dumps(newscast(h, **over)))
    return root


def test_archive_order_and_labels(tmp_path):
    html = render_archive(all_newscasts(runs(tmp_path, "2026-11-26T11", "2026-11-26T12", "2026-11-27T07")), PREFS)
    days = re.findall(r'<section class="day" id="(\d{4}-\d\d-\d\d)"', html)
    assert days == ["2026-11-27", "2026-11-26"]
    day26 = html[html.index('id="2026-11-26"'):]
    assert day26.index("12:00 pm") < day26.index("11:00 am")
    assert re.search(r'id="2026-11-27".*?<h2[^>]*>.*?Today', html, re.S)


def test_archive_lists_only_newscast_hours(tmp_path):
    root = runs(tmp_path, "2026-11-26T11")
    (root / "test-friday").mkdir()
    (root / "test-friday" / "newscast.json").write_text(json.dumps(newscast("2026-11-26T15")))
    (root / "rss-backfill").mkdir()
    assert [n["id"] for n in all_newscasts(root)] == ["2026-11-26T11"]


def test_archive_skips_damaged_runs(tmp_path):
    root = runs(tmp_path, "2026-11-26T11")
    (root / "2026-11-26T12").mkdir()
    (root / "2026-11-26T12" / "newscast.json").write_text('{"id": ')
    assert [n["id"] for n in all_newscasts(root)] == ["2026-11-26T11"]


def test_archive_lists_only_voiced_newscasts(tmp_path):
    root = runs(tmp_path, "2026-11-26T11")
    (root / "2026-11-26T12").mkdir()
    (root / "2026-11-26T12" / "newscast.json").write_text(json.dumps(newscast("2026-11-26T12", audio={})))
    assert [n["id"] for n in all_newscasts(root)] == ["2026-11-26T11"]


def test_archive_escapes_headlines(tmp_path):
    n = newscast("2026-11-26T11")
    n["stories"][0]["headline"] = "<b>x</b>"
    html = render_archive([n], PREFS)
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html


def test_archive_links_and_plays(tmp_path):
    html = render_archive(all_newscasts(runs(tmp_path, "2026-11-26T11")), PREFS)
    assert 'href="/h/2026-11-26/1100/index.html"' in html and 'href="/feed.xml"' in html
    srcs = [json.loads(p)["src"] for p in re.findall(r"data-play='([^']+)'", html)]
    assert "/audio/2026-11-26T11.mp3" in srcs


def test_front_page_links_the_archive():
    n = newscast()
    assert 'href="/archive/index.html"' in render_front(n, [n], PREFS)


def test_archive_path():
    assert ARCHIVE_PATH == "archive/index.html"
