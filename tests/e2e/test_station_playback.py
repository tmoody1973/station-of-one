"""Plan C Task 3: a clock station in the player bar, with a stand-in MusicKit (no Apple account needed).
Runs only with STATION_E2E=1, in system Chrome, against the test copy (spikes/shell_e2e_publish.py)."""
import json
import os
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("STATION_E2E") != "1", reason="end-to-end: set STATION_E2E=1")
BASE = os.environ.get("STATION_E2E_BASE", "https://patient-mountain-3400.fly.storage.tigris.dev/_checks/shell-e2e")
STUB = """
window.__mk = {calls: [], authorizeRejects: false, configureRejects: false, failSongs: [], authorized: false,
               authorizeDelayMs: 0, playBlocked: false, completeAfterQueue: false, noIsPlaying: false, queueFetches: 0};
(() => {
  const PS = {none: 0, loading: 1, playing: 2, paused: 3, stopped: 4, ended: 5, seeking: 6, waiting: 8, stalled: 9, completed: 10};
  const on = {};
  const inst = {
    queue: {items: []}, idx: 0, isPlaying: false, playbackState: 0, currentPlaybackTime: 0, currentPlaybackDuration: 240,
    get isAuthorized() { return __mk.authorized; },
    get nowPlayingItem() { const id = this.queue.items[this.idx]; return id ? {id, title: "Song " + id, artistName: "Artist " + id} : undefined; },
    async authorize() { __mk.calls.push(["authorize"]); await new Promise((r) => setTimeout(r, __mk.authorizeDelayMs));
                        if (__mk.authorizeRejects) throw new Error("declined"); __mk.authorized = true; return "t"; },
    async unauthorize() { __mk.calls.push(["unauthorize"]); __mk.authorized = false; },
    async _start() {
      const id = this.queue.items[this.idx];
      if (id === undefined) { this.isPlaying = false; this.playbackState = PS.completed; return; }
      if (__mk.failSongs.includes(id)) { this.isPlaying = false; throw new Error("unavailable " + id); }
      if (__mk.playBlocked) { __mk.playBlocked = false; this.isPlaying = false; const e = new Error("blocked"); e.name = "NotAllowedError"; throw e; }
      if (__mk.completeAfterQueue) { this.isPlaying = false; this.playbackState = PS.completed; return; }
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
  const real = Object.getOwnPropertyDescriptor(inst, "isPlaying");
  Object.defineProperty(inst, "isPlaying", {get() { return __mk.noIsPlaying ? undefined : this._p; }, set(v) { this._p = v; }});
  inst._p = false;
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
            pg.route("**/test-station/queue.json", lambda route: (pg.evaluate("() => window.__mk && window.__mk.queueFetches++") if stub else None,
                                                                  route.fulfill(json=queue()))[1])
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
    pg2.wait_for_function("() => document.getElementById('wone-msg').textContent.includes('available in your country')", timeout=5000)
    assert "subscription" in pg2.locator("#wone-msg").inner_text()


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


def test_strip_name_box_tunes_in(make_page):
    pg = make_page()
    pg.wait_for_selector("#wone-strip .st-name:has-text('Rhythm Lab')", timeout=10000)
    pg.locator("#wone-strip .st-name", has_text="Rhythm Lab").click()
    pg.wait_for_function("() => window.__mk.calls.some(c => c[0] === 'setQueue')", timeout=10000)


def test_older_pages_keep_their_player(make_page):  # review C1: pages built before Plan C have no Skip/Back to live/msg
    pg = make_page()
    def strip(route):
        html = route.fetch().text()
        for el in ('<span class="msg" id="wone-msg" hidden></span>',):
            html = html.replace(el, "")
        import re as _re
        html = _re.sub(r'<button class="ctl station-only"[^>]*>[^<]*</button>', "", html)
        route.fulfill(body=html, headers={"content-type": "text/html"})
    pg.route("**/_checks/shell-e2e/index.html", strip)
    pg.goto(f"{BASE}/index.html", wait_until="networkidle")
    assert pg.evaluate("() => !!window.wone && !document.getElementById('wone-live')")
    pg.locator("main .btn-dark[data-play]").first.click()
    pg.wait_for_function("() => !document.getElementById('wone-audio').paused", timeout=15000)


def test_newscast_tapped_during_slow_sign_in_wins(make_page):  # review I2: never two sounds
    pg = make_page()
    pg.evaluate("() => { window.__mk.authorizeDelayMs = 2000 }")
    pg.locator("#tune").click()
    pg.wait_for_timeout(300)
    pg.locator("main .btn-dark[data-play]").first.click()
    pg.wait_for_timeout(3000)
    assert pg.evaluate("() => !document.getElementById('wone-audio').paused")
    assert not calls(pg, "setQueue") and pg.evaluate("() => MusicKit.getInstance().isPlaying") is not True


def test_blocked_play_asks_for_a_tap(make_page):  # review I3: a browser that refuses to start sound isn't a missing song
    pg = make_page()
    pg.evaluate("() => { window.__mk.playBlocked = true }")
    tune(pg)
    pg.wait_for_function("() => document.getElementById('wone-msg').textContent.includes('Tap ▶')", timeout=5000)
    assert not calls(pg, "skip")
    pg.locator("#wone-play").click()
    pg.wait_for_function("() => window.__mk.calls.some(c => c[0] === 'play')", timeout=5000)


def test_finished_queue_rejoins_once_without_repeats(make_page):  # review I4 and I5
    pg = make_page()
    pg.evaluate("() => { window.__mk.completeAfterQueue = true }")
    tune(pg)
    pg.wait_for_timeout(3500)
    assert pg.evaluate("() => window.__mk.queueFetches") <= 2                 # not twice a second
    for _, songs, _start in calls(pg, "setQueue")[1:]:
        assert "s1" not in songs and "s2" not in songs                       # never back to songs already queued


def test_pause_works_without_isplaying(make_page):  # review I6: isPlaying isn't in the confirmed API
    pg = make_page()
    pg.evaluate("() => { window.__mk.noIsPlaying = true }")
    tune(pg)
    pg.locator("#wone-play").click()
    pg.wait_for_function("() => window.__mk.calls.some(c => c[0] === 'pause')", timeout=5000)


def test_strip_follows_the_player(make_page):  # live-playlist Focus 1: the header names the song you hear
    pg = make_page()
    pg.route("**/data/radio/rhythm-lab/queue.json", lambda route: route.fulfill(json=queue()))
    pg.wait_for_selector("#wone-strip .st-name:has-text('Rhythm Lab')", timeout=10000)
    pg.locator("#wone-strip .st-name", has_text="Rhythm Lab").click()
    pg.wait_for_function("() => window.__mk.calls.some(c => c[0] === 'setQueue')", timeout=10000)
    pg.wait_for_function("""() => [...document.querySelectorAll('#wone-strip .st')].some(s =>
        s.textContent.includes('Rhythm Lab') && s.querySelector('.st-now').textContent.includes('Song s1'))""", timeout=5000)
    pg.locator("#wone-skip-song").click()
    pg.wait_for_function("""() => [...document.querySelectorAll('#wone-strip .st')].some(s =>
        s.textContent.includes('Rhythm Lab') && s.querySelector('.st-now').textContent.includes('Song s2'))""", timeout=5000)


def test_label_follows_the_song_even_without_an_event(make_page):  # Tarik, 5:04 pm: the bar named a song that wasn't playing
    pg = make_page()
    tune(pg)
    pg.wait_for_function("() => document.getElementById('wone-now').textContent.includes('Song s1')", timeout=5000)
    pg.evaluate("() => { MusicKit.getInstance().idx += 1 }")      # Apple moved on to the next song, and said nothing
    pg.wait_for_function("() => document.getElementById('wone-now').textContent.includes('Song s2')", timeout=3000)


def test_bar_and_strip_name_songs_the_same_way(make_page):  # one order everywhere: Artist · Title
    pg = make_page()
    tune(pg)
    pg.wait_for_function("() => document.getElementById('wone-now').textContent === 'Artist s1 · Song s1'", timeout=5000)


def _rhythm_lab(pg):
    pg.goto(f"{BASE}/radio/rhythm-lab/index.html", wait_until="networkidle")
    pg.evaluate("() => { window.__marker = 1 }")
    pg.wait_for_selector("main li.trk", state="attached", timeout=10000)   # the newest rows are later songs, hidden by design


def test_now_follows_the_clock_when_not_listening(make_page):  # live-playlist Focus 2
    pg = make_page()
    _rhythm_lab(pg)
    pg.wait_for_timeout(500)
    bad = pg.evaluate("""() => [...document.querySelectorAll('main li.trk')].filter(r => getComputedStyle(r).display !== 'none'
        && Date.parse(r.dataset.starts) > Date.now() && !r.classList.contains('next')).length""")
    assert bad == 0                                              # no later song shows, except an "Up next" during a break
    now = pg.evaluate("""() => { const r = document.querySelector('main li.trk.now');
        return r ? Date.parse(r.dataset.starts) <= Date.now() && Date.now() < Date.parse(r.dataset.ends) : 'none' }""")
    assert now in (True, "none")


def test_now_follows_the_player(make_page):  # live-playlist Focus 1: the page names the song you hear
    pg = make_page()
    _rhythm_lab(pg)
    pg.locator("main button:has-text('Listen live')").click()
    pg.wait_for_function("() => window.__mk.calls.some(c => c[0] === 'setQueue')", timeout=10000)
    for _ in range(2):
        pg.locator("#wone-skip-song").click()
    pg.wait_for_timeout(1200)
    s = pg.evaluate("""() => ({playing: String(MusicKit.getInstance().nowPlayingItem.id),
        now: (document.querySelector('main li.trk.now') || {dataset: {}}).dataset.song,
        box: document.querySelector('#onnow h2').textContent})""")
    assert s["now"] == s["playing"]
