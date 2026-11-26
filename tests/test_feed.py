import xml.etree.ElementTree as ET

from station.config import load_prefs
from station.steps.page import render_feed
from station.steps.publish import CONTENT_TYPES, cache_control
from tests.test_page import newscast

PREFS = load_prefs()
IT = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
BASE = "https://patient-mountain-3400.fly.storage.tigris.dev"


def feed(n=None):
    return ET.fromstring(render_feed(n or newscast(), PREFS, audio_bytes=1722088))


def test_single_latest_item_with_absolute_enclosure():
    items = feed().findall("channel/item")
    assert len(items) == 1
    enc = items[0].find("enclosure").attrib
    assert enc == {"url": f"{BASE}/audio/2026-11-26T17.mp3", "length": "1722088", "type": "audio/mpeg"}
    assert items[0].find("guid").text == "2026-11-26T17" and items[0].find("guid").get("isPermaLink") == "false"
    assert items[0].find(f"{IT}duration").text == "215"
    assert "5:00 pm" in items[0].find("title").text


def test_show_fields_directories_require():
    ch = feed().find("channel")
    assert ch.find("title").text and ch.find("description").text and ch.find("language").text == "en-us"
    assert ch.find(f"{IT}image").get("href") == f"{BASE}/cover-dial.png"
    assert ch.find(f"{IT}category").get("text") == "News" and ch.find(f"{IT}explicit").text == "false"
    assert ch.find("link").text == f"{BASE}/index.html"
    assert "synthetic" in ch.find("description").text.lower() and "machine-edited" in ch.find("description").text.lower()


def test_item_description_lists_chapters_as_plain_text():
    desc = feed().find("channel/item/description").text
    assert "0:00 Open" in desc and "<" not in desc and "synthetic" in desc.lower()


def test_titles_are_escaped():
    n = newscast()
    n["chapters"][1]["title"] = "AT&T <b>deal</b>"
    assert "AT&T <b>deal</b>" in feed(n).find("channel/item/description").text  # parses back as plain text


def test_feed_served_as_xml_with_short_cache():
    assert CONTENT_TYPES[".xml"] == "application/rss+xml; charset=utf-8" and cache_control("feed.xml") == "max-age=60"


def test_front_page_links_the_feed():
    from station.steps.page import render_front

    n = newscast()
    html = render_front(n, [n], PREFS)
    assert '<link rel="alternate" type="application/rss+xml"' in html and 'href="/feed.xml"' in html
