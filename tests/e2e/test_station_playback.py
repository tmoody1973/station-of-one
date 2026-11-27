"""Plan C Task 3: a clock station in the player bar, with a stand-in MusicKit (no Apple account needed).
Runs only with STATION_E2E=1, in system Chrome, against the test copy (spikes/shell_e2e_publish.py)."""
import json
import os
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("STATION_E2E") != "1", reason="end-to-end: set STATION_E2E=1")
BASE = os.environ.get("STATION_E2E_BASE", "https://patient-mountain-3400.fly.storage.tigris.dev/_checks/shell-e2e")
STUB = """
window.__mk = {calls: [], authorizeRejects: false, configureRejects: false, failSongs: [], authorized: false};
(() => {
  const PS = {none: 0, loading: 1, playing: 2, paused: 3, stopped: 4, ended: 5, seeking: 6, waiting: 8, stalled: 9, completed: 10};
  const on = {};
  const inst = {
    queue: {items: []}, idx: 0, isPlaying: false, playbackState: 0, currentPlaybackTime: 0, currentPlaybackDuration: 240,
    get isAuthorized() { return __mk.authorized; },
    get nowPlayingItem() { const id = this.queue.items[this.idx]; return id ? {id, title: "Song " + id, artistName: "Artist " + id} : undefined; },
    async authorize() { __mk.calls.push(["authorize"]); if (__mk.authorizeRejects) throw new Error("declined"); __mk.authorized = true; return "t"; },
    async unauthorize() { __mk.calls.push(["unauthorize"]); __mk.authorized = false; },
    async _start() {
      const id = this.queue.items[this.idx];
      if (id === undefined) { this.isPlaying = false; this.playbackState = PS.completed; return; }
      if (__mk.failSongs.includes(id)) { this.isPlaying = false; throw new Error("unavailable " + id); }
      this.isPlaying = true; this.playbackState = PS.playing;
      (on.nowPlayingItemDidChange || []).forEach((f) => f({item: this.nowPlayingItem}));
    },
    async setQueue(o) { __mk.calls.push(["setQueue", o.songs, o.startTime]); this.queue = {items: [...o.songs]}; this.idx = 0;
                        this.currentPlaybackTime = o.startTime || 0; await this._start(); },
    async play() { __mk.calls.push(["play"]); this.isPlaying = true; this.playbackState = PS.playing; },
    pause() { __mk.calls.push(["pause"]); this.isPlaying = false; this.playbackState = PS.paused; },
    async skipToNextItem() { __mk.calls.push(["skip"]); this.idx += 1; this.currentPlaybackTime = 0; await this._start(); },
    addEventListener(n, f) { (on[n] = on[n] || []).push(f); },
  };
  window.MusicKit = {PlaybackStates: PS, getInstance: () => inst,
    async configure(cfg) { __mk.calls.push(["configure", cfg.developerToken]); if (__mk.configureRejects) throw new Error("bad token"); return inst; }};
})();
"""
STATION = ('<button id="tune" data-play=\'{"kind": "station", "src": "/data/radio/test-station/queue.json", '
           '"title": "Test Station", "label": "Test Station · live"}\'>tune</button>')


def queue(offset_s=100):
    start = datetime.now(UTC) - timedelta(seconds=offset_s)
    items = [{"starts_at": (start + timedelta(seconds=240 * i)).isoformat(), "kind": "song", "song_id": f"s{i + 1}",
              "duration_ms": 240000, "title": f"T{i}", "artist": f"A{i}"} for i in range(6)]
    return {"station": "test-station", "items": items}


@pytest.fixture
def make_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])

        def make(stub=True, token=True):
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            pg.apple_requests = []
            pg.on("request", lambda r: pg.apple_requests.append(r.url) if "js-cdn.music.apple.com" in r.url else None)
            if stub:
                pg.add_init_script(STUB)
            pg.route("**/data/musickit.json", lambda route: route.fulfill(json={"developerToken": "stub", "app": {"name": "t", "build": "1"}})
                     if token else route.fulfill(status=404, body="no"))
            pg.route("**/test-station/queue.json", lambda route: route.fulfill(json=queue()))
            pg.goto(f"{BASE}/index.html", wait_until="networkidle")
            pg.evaluate("() => { window.__marker = 1 }")
            pg.evaluate("h => document.querySelector('main').insertAdjacentHTML('beforeend', h)", STATION)
            return pg
        yield make
        b.close()


def calls(pg, name=None):
    c = pg.evaluate("() => window.__mk.calls")
    return [x for x in c if x[0] == name] if name else c


def tune(pg):
    pg.locator("#tune").click()
    pg.wait_for_function("() => window.__mk.calls.some(c => c[0] === 'setQueue') || document.getElementById('wone-msg').textContent", timeout=10000)


def test_station_joins_live(make_page):
    pg = make_page()
    tune(pg)
    names = [c[0] for c in calls(pg)]
    assert names.index("configure") < names.index("authorize") < names.index("setQueue")
    _, songs, start = calls(pg, "setQueue")[0]
    assert songs[0] == "s1" and abs(start - 100) <= 5 and songs[-1] == "s6"
    pg.wait_for_function("() => document.getElementById('wone-now').textContent.includes('Song s1')", timeout=5000)


def test_skip_and_back_to_live(make_page):
    pg = make_page()
    tune(pg)
    pg.locator("#wone-skip-song").click()
    pg.wait_for_function("() => window.__mk.calls.some(c => c[0] === 'skip')", timeout=5000)
    pg.locator("#wone-live").click()
    pg.wait_for_function("() => window.__mk.calls.filter(c => c[0] === 'setQueue').length === 2", timeout=5000)


def test_station_keeps_playing_across_pages(make_page):
    pg = make_page()
    tune(pg)
    for nav in ("Settings", "News"):
        before = pg.evaluate("() => location.pathname")
        pg.locator(f"header.site nav a:has-text('{nav}')").first.click()
        pg.wait_for_function(f"() => location.pathname !== {before!r}", timeout=10000)
        pg.wait_for_timeout(800)
    assert pg.evaluate("() => window.__marker") == 1 and len(calls(pg, "setQueue")) == 1
    assert pg.evaluate("() => MusicKit.getInstance().isPlaying") is True


def test_one_sound_at_a_time(make_page):  # Review Focus 3
    pg = make_page()
    tune(pg)
    pg.locator("main .btn-dark[data-play]").first.click()      # the newscast
    pg.wait_for_function("() => !document.getElementById('wone-audio').paused", timeout=15000)
    assert pg.evaluate("() => MusicKit.getInstance().isPlaying") is False
    pg.locator("#tune").click()                                  # back to the station
    pg.wait_for_function("() => MusicKit.getInstance().isPlaying", timeout=5000)
    assert pg.evaluate("() => document.getElementById('wone-audio').paused") is True


def test_declined_sign_in_keeps_previews(make_page):  # Review Focus 1
    pg = make_page()
    pg.evaluate("() => { window.__mk.authorizeRejects = true }")
    tune(pg)
    assert not calls(pg, "setQueue")
    assert "Apple Music subscription" in pg.locator("#wone-msg").inner_text()
    pg.locator("main .btn-dark[data-play]").first.click()      # our own audio still plays
    pg.wait_for_function("() => !document.getElementById('wone-audio').paused", timeout=15000)


def test_missing_token_fails_quietly(make_page):  # Review Focus 4
    pg = make_page(token=False)
    tune(pg)
    assert not calls(pg, "configure") and not calls(pg, "setQueue")
    assert "aren't available right now" in pg.locator("#wone-msg").inner_text()


def test_unavailable_songs_skip(make_page):  # Review Focus 5
    pg = make_page()
    pg.evaluate("() => { window.__mk.failSongs = ['s1'] }")
    tune(pg)
    pg.wait_for_function("() => document.getElementById('wone-now').textContent.includes('Song s2')", timeout=5000)
    pg2 = make_page()
    pg2.evaluate("() => { window.__mk.failSongs = ['s1', 's2', 's3', 's4'] }")
    tune(pg2)
    pg2.wait_for_function("() => document.getElementById('wone-msg').textContent.includes(\"aren't available in your country\")", timeout=5000)


def test_musickit_not_loaded_until_tap(make_page):
    pg = make_page(stub=False)
    pg.wait_for_timeout(1000)
    assert pg.apple_requests == []


def test_connect_from_settings(make_page):
    pg = make_page()
    pg.locator("header.site nav a:has-text('Settings')").first.click()
    pg.wait_for_selector("main [data-apple='connect']", timeout=10000)
    pg.locator("main [data-apple='connect']").click()
    pg.wait_for_function("() => document.querySelector('[data-apple-status]').textContent.includes('Connected')", timeout=5000)
    assert calls(pg, "authorize")
    pg.locator("main [data-apple='disconnect']").click()
    pg.wait_for_function("() => document.querySelector('[data-apple-status]').textContent.includes('Not connected')", timeout=5000)
    assert calls(pg, "unauthorize")


def test_strip_chip_tunes_in(make_page):
    pg = make_page()
    pg.wait_for_function("() => [...document.querySelectorAll('#wone-strip .chip')].some(c => c.textContent.includes('Rhythm Lab'))", timeout=10000)
    pg.locator("#wone-strip .chip", has_text="Rhythm Lab").click()
    pg.wait_for_function("() => window.__mk.calls.some(c => c[0] === 'setQueue')", timeout=10000)
