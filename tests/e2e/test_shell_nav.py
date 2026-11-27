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
    _click(page, "#wone-strip a:has-text('ONE Jazz')")        # the jazz sampler
    _click(page, "header.site nav a:has-text('Settings')")
    s = page.evaluate(STATE)
    assert s["marker"] and not s["paused"] and s["t"] > t0 + 2


def test_back_forward_keeps_playing(page):
    _start(page)
    _click(page, "#wone-strip a:has-text('ONE Jazz')")
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
    _click(page, "#wone-strip a:has-text('ONE Jazz')")          # reached by a swap, not a page load
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


def test_station_strip(page):  # KCRW pattern: a name box with play, what's on now, More station info
    page.wait_for_function("() => document.querySelectorAll('#wone-strip .st-name').length >= 2", timeout=10000)
    names = page.locator("#wone-strip .st-name .nm").all_text_contents()
    assert names[0] == "News" and "ONE Jazz" in names
    page.locator("#wone-strip .st-name", has_text="News").click()           # the name box plays
    page.wait_for_function("() => { const a = document.getElementById('wone-audio'); return !a.paused && a.src.includes('/audio/') }", timeout=15000)
    _click(page, "#wone-strip a.st-name:has-text('ONE Jazz')")               # a station with no live stream opens its page
    s = page.evaluate(STATE)
    assert s["path"].endswith("/radio/uk-jazz/index.html") and not s["paused"] and s["marker"]


def test_more_station_info_panel(page):
    page.wait_for_selector("#wone-strip [data-strip-more]", timeout=10000)
    assert page.locator("#wone-strip .strip-panel").is_hidden()
    page.locator("#wone-strip [data-strip-more]").click()
    panel = page.locator("#wone-strip .strip-panel")
    text = panel.text_content()   # raw text: the panel's styling lowercases headings
    assert panel.is_visible() and "five minutes on the hour" in text and "Next up" in text and "Rhythm Lab" in text
    hrefs = panel.locator("a").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert any(h.endswith("/radio/how-it-works/index.html") for h in hrefs)   # Tarik, 5:36 pm: no direct link to it


def test_strip_now_links_to_station_page(page):
    page.wait_for_selector("#wone-strip .st-now", timeout=10000)
    hrefs = page.locator("#wone-strip .st-now").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert any(h.endswith("/radio/rhythm-lab/index.html") for h in hrefs) and any(h.endswith("/radio/uk-jazz/index.html") for h in hrefs)



def _inject(page, html):
    page.evaluate("h => document.querySelector('main').insertAdjacentHTML('beforeend', h)", html)


EMBED = '<button id="emb" data-play=\'{"src": "https://www.youtube-nocookie.com/embed/lN96f4SwJyk", "title": "t", "label": "Music pick", "start": 0, "chapters": [], "kind": "embed"}\'>dock</button>'


def test_older_page_loads_normally(page):  # review I1: archive pages built before the shell
    _inject(page, '<a id="old" href="old/index.html">old</a>')
    page.locator("#old").click()
    page.wait_for_url("**/old/index.html", timeout=10000)
    page.wait_for_load_state("load")
    assert page.evaluate("() => window.__marker") is None and "built before the shell" in page.content()


def test_bar_play_follows_the_current_page(page):  # review I2
    page.goto(f"{BASE}/radio/uk-jazz/index.html", wait_until="networkidle")   # a page with nothing to play
    page.evaluate("() => { window.__marker = 1 }")
    _click(page, "header.site nav a:has-text('News')")
    page.locator("#wone-play").click()
    page.wait_for_function("() => { const a = document.getElementById('wone-audio'); return !a.paused && a.src.includes('/audio/') }", timeout=15000)
    assert page.evaluate("() => window.__marker") == 1


def test_bar_play_after_docked_embed_plays_one_thing(page):  # review I3
    _start(page)
    _inject(page, EMBED)
    page.locator("#emb").click()
    page.wait_for_function("() => document.querySelector('#wone-embed iframe') !== null", timeout=5000)
    page.locator("#wone-play").click()
    page.wait_for_timeout(1000)
    s = page.evaluate("() => ({iframes: document.querySelectorAll('#wone-embed iframe').length, playing: !document.getElementById('wone-audio').paused})")
    assert s == {"iframes": 0, "playing": True}


def test_phone_page_clears_a_docked_embed(page):  # review I5
    page.set_viewport_size({"width": 390, "height": 844})
    _inject(page, EMBED)
    page.locator("#emb").click()
    page.wait_for_function("() => document.querySelector('#wone-embed iframe') !== null", timeout=5000)
    page.wait_for_timeout(500)
    pad, bar = page.evaluate("() => [parseFloat(getComputedStyle(document.body).paddingBottom), document.getElementById('wone-player').offsetHeight]")
    assert pad >= bar


LAYOUT = """() => [...document.querySelectorAll('main, main > *, main > * > *')].slice(0, 40).map(e => {
    const c = getComputedStyle(e); return [e.tagName, e.className, c.display, c.gridTemplateColumns, c.backgroundColor, c.fontSize].join('|'); })"""


def test_swapped_page_looks_like_a_fresh_load(page):  # Tarik, 4:54 pm: the layout went funky after changing pages
    fresh = page.evaluate(LAYOUT)                                 # the front page, loaded fresh
    page.goto(f"{BASE}/radio/uk-jazz/index.html", wait_until="networkidle")   # start somewhere else, fresh
    page.evaluate("() => { window.__marker = 1 }")
    _click(page, "header.site nav a:has-text('News')")            # then reach the front page by a swap
    assert page.evaluate("() => window.__marker") == 1            # a swap, not a reload
    assert page.evaluate(LAYOUT) == fresh


def test_swap_keeps_styles_added_by_scripts(page):  # MusicKit adds its own <style>; a swap must not remove it
    page.evaluate("() => { const s = document.createElement('style'); s.id = 'injected'; s.textContent = '.x{color:red}'; document.head.append(s); }")
    _click(page, "header.site nav a:has-text('Settings')")
    assert page.evaluate("() => !!document.getElementById('injected')")


def test_older_page_without_the_new_strip_loads_fresh(page):  # review I1: its old styles would restyle the bar and strip
    def old(route):
        html = route.fetch().text().replace('<div class="wrap strip-panel" hidden></div>', "")
        route.fulfill(body=html, headers={"content-type": "text/html"})
    page.route("**/_checks/shell-e2e/settings/index.html", old)
    _click_nav = page.locator("header.site nav a:has-text('Settings')").first
    _click_nav.click()
    page.wait_for_url("**/settings/index.html", timeout=10000)
    page.wait_for_load_state("load")
    assert page.evaluate("() => window.__marker") is None      # a full load: the page looks as it was built


def test_strip_keeps_its_buttons_between_redraws(page):  # review I2: no lost taps, focus stays put
    page.wait_for_selector("#wone-strip [data-strip-more]", timeout=10000)
    page.evaluate("() => { document.querySelector('#wone-strip [data-strip-more]').__kept = 1; document.dispatchEvent(new CustomEvent('wone:song')); }")
    assert page.evaluate("() => document.querySelector('#wone-strip [data-strip-more]').__kept") == 1
    page.locator("#wone-strip [data-strip-more]").focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    assert page.evaluate("() => document.activeElement && document.activeElement.hasAttribute('data-strip-more')")
    assert page.locator("#wone-strip .strip-panel").is_visible()


def test_older_page_gets_the_strip_styles(page):  # Tarik, 5:27 pm: ONE Jazz built at 4:48 drew an unstyled strip
    import re as _re
    normal = page.evaluate("() => getComputedStyle(document.querySelector('#wone-strip .st-name')).backgroundColor")
    def old(route):
        html = route.fetch().text()
        html = _re.sub(r"/\* wone-shell-css \*/.*?/\* /wone-shell-css \*/", "", html, flags=_re.S)   # as built before shell.css
        route.fulfill(body=html, headers={"content-type": "text/html"})
    page.route("**/_checks/shell-e2e/index.html", old)
    page.goto(f"{BASE}/index.html", wait_until="networkidle")
    page.wait_for_selector("#wone-strip .st-name", timeout=10000)
    page.wait_for_timeout(500)
    assert page.evaluate("() => getComputedStyle(document.querySelector('#wone-strip .st-name')).backgroundColor") == normal
