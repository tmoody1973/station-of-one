"""Site shell end-to-end (plan 2026-11-27-site-shell, Task 3). Runs only with STATION_E2E=1, in system
Chrome, against the test copy published by spikes/shell_e2e_publish.py (or STATION_E2E_BASE)."""
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("STATION_E2E") != "1", reason="end-to-end: set STATION_E2E=1")
BASE = os.environ.get("STATION_E2E_BASE", "https://patient-mountain-3400.fly.storage.tigris.dev/_checks/shell-e2e")
STATE = """() => { const a = document.getElementById('wone-audio');
  return {path: location.pathname, title: document.title, paused: a.paused, t: a.currentTime, marker: window.__marker === 1} }"""


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(f"{BASE}/index.html", wait_until="networkidle")
        pg.evaluate("() => { window.__marker = 1 }")  # survives swaps, vanishes on a full page load
        yield pg
        b.close()


def _start(pg):
    pg.locator("#wone-play").click()
    pg.wait_for_function("() => !document.getElementById('wone-audio').paused && document.getElementById('wone-audio').currentTime > 0.5", timeout=15000)


def _click(pg, selector):
    before = pg.evaluate("() => location.pathname")
    pg.locator(selector).first.click()
    pg.wait_for_function(f"() => location.pathname !== {before!r}", timeout=10000)
    pg.wait_for_timeout(1200)


def test_navigation_keeps_audio_playing(page):
    _start(page)
    t0 = page.evaluate(STATE)["t"]
    _click(page, "main a[href*='/s/']")                        # a story page
    _click(page, "header.site nav a:has-text('Music')")        # the jazz sampler
    _click(page, "header.site nav a:has-text('Settings')")
    s = page.evaluate(STATE)
    assert s["marker"] and not s["paused"] and s["t"] > t0 + 2


def test_back_forward_keeps_playing(page):
    _start(page)
    _click(page, "header.site nav a:has-text('Music')")
    _click(page, "header.site nav a:has-text('Settings')")
    for step in ("back", "back", "forward"):
        getattr(page, f"go_{step}")()
        page.wait_for_timeout(1500)
    s = page.evaluate(STATE)
    assert s["marker"] and not s["paused"] and s["path"].endswith("/radio/uk-jazz/index.html")


def test_title_and_address_update(page):
    _click(page, "header.site nav a:has-text('Settings')")
    s = page.evaluate(STATE)
    assert s["path"].endswith("/settings/index.html") and "Settings" in s["title"] and s["marker"]
    assert page.locator("header.site .line").inner_text().lower() == "settings"


def test_external_and_download_links_untouched(page):
    # A window listener runs after the shell's document listener: it records whether the shell took the
    # click, then cancels the navigation itself so the test page stays put.
    probe = """sel => { const a = document.querySelector(sel); if (!a) return 'missing'; let taken = null;
        const spy = e => { taken = e.defaultPrevented; e.preventDefault(); };
        window.addEventListener('click', spy, {once: true});
        a.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true})); return taken }"""
    assert page.evaluate(probe, "a[href='/feed.xml']") is False              # RSS feed: left to the browser
    assert page.evaluate(probe, "main a[target='_blank'], main a[href^='https://']:not([href*='tigris'])") is False
    assert page.evaluate(probe, "header.site nav a") is True                   # a page link: swapped


def test_failed_fetch_falls_back(page):
    page.evaluate("""() => { const a = document.createElement('a'); a.href = 'broken/index.html'; a.id = 'brk';
        a.textContent = 'broken'; document.querySelector('main').append(a) }""")
    page.locator("#brk").click()
    page.wait_for_url("**/broken/index.html", timeout=10000)
    page.wait_for_load_state("load")
    assert page.evaluate("() => window.__marker") is None   # a real page load happened, not a blank page
    assert "deliberately has no main" in page.content()


def test_controls_work_after_swap(page):
    _click(page, "header.site nav a:has-text('Music')")          # reached by a swap, not a page load
    page.locator("main .pv").first.click()
    page.wait_for_function("() => { const a = document.getElementById('wone-audio'); return !a.paused && a.src.includes('itunes.apple.com') }", timeout=15000)
    assert "preview" in page.locator("#wone-label").inner_text().lower()
    page.go_back()
    page.wait_for_function("() => document.querySelector('main .btn-dark[data-play]') !== null", timeout=10000)  # the front page is back
    start = page.evaluate("() => JSON.parse(document.querySelector('main .btn-dark[data-play]').dataset.play).start")
    page.locator("main .btn-dark[data-play]").first.click()
    page.wait_for_function("() => { const a = document.getElementById('wone-audio'); return !a.paused && a.src.includes('/audio/') }", timeout=15000)
    page.wait_for_timeout(800)
    t = page.evaluate("() => document.getElementById('wone-audio').currentTime")
    assert start <= t <= start + 5 and page.evaluate("() => window.__marker") == 1


def test_station_strip(page):
    page.wait_for_function("() => document.querySelectorAll('#wone-strip .chip').length >= 2", timeout=10000)
    names = page.locator("#wone-strip .chip b").all_inner_texts()
    assert names[0] == "News" and "ONE Jazz" in names
    page.locator("#wone-strip .chip", has_text="News").click()
    page.wait_for_function("() => { const a = document.getElementById('wone-audio'); return !a.paused && a.src.includes('/audio/') }", timeout=15000)
    _click(page, "#wone-strip .chip:has-text('ONE Jazz')")
    s = page.evaluate(STATE)
    assert s["path"].endswith("/radio/uk-jazz/index.html") and not s["paused"] and s["marker"]
