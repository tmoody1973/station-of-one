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
    assert files and all(f.endswith(("index.html", ".mp3", ".xml", ".svg", ".png")) for f in files)  # never a bare folder


def test_footer_synthetic_line():
    html = render_front(newscast(), [newscast()], PREFS)
    assert "Voices are synthetic. This show is machine-edited from public posts, with every source linked." in html


def test_play_from_story_uses_chapter_start():
    n = newscast()
    html = render_front(n, [n], PREFS)
    lead = n["stories"][0]
    assert f'"start": {lead["chapter_start_ms"] / 1000}' in html  # the shared player starts at the chapter
    assert "Play from this story" in html and f'/audio/{n["id"]}.mp3' in html


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
    assert names == ["data/stations.json", "feed.xml", "h/2026-11-26/1700/index.html", "index.html", "live.js", "shell.js"]


def test_only_http_links_render():  # scraped URLs are untrusted
    n = newscast()
    n["stories"][0]["sources"] = [{"post_id": "x", "url": "javascript:alert(1)", "author": None,
                                   "source_name": "Evil", "posted_at": ""}]
    html = render_front(n, [n], PREFS)
    assert "javascript:" not in html and 'href="#"' in html


def test_play_labels_show_story_length():  # "0:010:01..." bug seen in the first screenshot
    n = newscast()
    n["stories"][0]["seconds"] = 90
    n["stories"][1]["seconds"] = 32
    html = render_front(n, [n], PREFS)
    assert "Play from this story · 1:30" in html and "Play · 0:32" in html and "0:010:01" not in html


def test_musickit_json_written_from_token_file(tmp_path):  # Plan C Task 1
    from station.steps.page import musickit_config
    runs = tmp_path / "runs"
    (runs / "2026-11-26T17").mkdir(parents=True)
    (runs / "2026-11-26T17" / "newscast.json").write_text(json.dumps(newscast("2026-11-26T17")))
    token = tmp_path / "musickit_token"
    token.write_text("abc.def.ghi\n")
    written = page(runs / "2026-11-26T17", PREFS, runs_root=runs, musickit_token=token)
    out = runs / "2026-11-26T17" / "site" / "data" / "musickit.json"
    assert out in written
    assert json.loads(out.read_text()) == {"developerToken": "abc.def.ghi", "app": {"name": "ONE 1.0 FM", "build": "2026.11.27"}}
    assert musickit_config(token) == json.loads(out.read_text())


def test_no_token_no_musickit_json(tmp_path):
    from station.steps.page import musickit_config
    runs = tmp_path / "runs"
    (runs / "2026-11-26T17").mkdir(parents=True)
    (runs / "2026-11-26T17" / "newscast.json").write_text(json.dumps(newscast("2026-11-26T17")))
    written = page(runs / "2026-11-26T17", PREFS, runs_root=runs, musickit_token=tmp_path / "missing")
    assert not any(p.name == "musickit.json" for p in written)
    (tmp_path / "empty").write_text("  \n")
    assert musickit_config(tmp_path / "missing") is None and musickit_config(tmp_path / "empty") is None


def test_token_file_is_git_ignored():
    import subprocess
    assert subprocess.run(["git", "check-ignore", "-q", "data/musickit_token"]).returncode == 0
