# Site Shell: Persistent Player and Station Strip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every page shares three things:
- **A masthead.**
- **A station strip:** each station with ▶ and what's on now, expandable to a panel with each station's description and what's next.
- **One player bar** that keeps playing, with no gap, while the listener moves between pages, including Back and Forward.

**Architecture:** The site stays static files in the bucket. After the first page load, a small script turns link clicks into background fetches:
- **What changes:** only the page content swaps. The address bar and history update as normal.
- **What never reloads:** the masthead, the strip and the player bar.
- **How audio survives:** it lives in the page's memory, never in the swapped content.

Two ways to do this are compared in a spike against the real bucket:
- **(a) Turbo Drive** with the player marked `data-turbo-permanent` (Turbo moves permanent elements into each new page).
- **(b) Content-only swap:** only `<main>` is replaced, so the player is never moved. This keeps YouTube and Bandcamp embeds alive too, because browsers reload an iframe that is moved.

The one that keeps audio and an embed playing through five navigations, Back and Forward wins. Every page template then includes the shared partials. Page scripts move to one `shell.js` that works for both first loads and swaps. A small `stations.json` (published every hour) feeds the strip.

**Tech Stack:** Jinja2 partials, plain JavaScript (no build step), possibly Turbo 8 (ESM, vendored into the bucket, not a CDN), Playwright (system Chrome) end-to-end checks against `_checks/shell/` pages in the bucket.

**Spec:** Tarik, Nov 27:
- "the stations are connected to a persistent player which should be on every page and continues playing when switching pages with no stoppage"
- the KCRW station-strip pattern ("I like how KCRW.com displays multiple stations")

Project rule (CLAUDE.md): "No real station's name, call letters, theme or look. Do not copy any real outlet's design." So we take the pattern (a strip of stations with ▶ and now-playing, an expandable panel) in our Bauhaus style, not KCRW's look. PRD (music stations): "Voice breaks, station IDs and the newscast are our own audio files, played between songs by a second player."

## Global Constraints

- Playback never starts without a tap (browsers and Apple require it). After a tap, nothing interrupts it except the listener.
- One player bar for the whole site. Every ▶ on any page plays through it, so starting something new stops the old.
- Apple previews still play one at a time, only on tap, and never advance on their own.
- Links still work without JavaScript (plain full page loads), and every page has its own address.
- No real outlet's look: Bauhaus tokens from `templates/_bauhaus.css`.
- Scraped text stays escaped; the strip's JSON is rendered with `textContent`, never `innerHTML`.
- Turbo, if chosen, is served from our bucket (`/vendor/turbo.es2017-esm.js`, version pinned), not a third-party CDN.

## Review Focus

1. **Back and Forward during playback:** audio continues, and the right page content shows (Task 3 e2e `test_back_forward_keeps_playing`).
2. **A link that must not be swapped:** external sites, `target=_blank`, downloads, `#anchors`, the RSS feed and the MP4. These navigate normally (Task 3 `test_external_and_download_links_untouched`).
3. **Page scripts after a swap:** the story Listen button, Table chapters, pick "Play here" and sampler previews all work on a page reached by a swap, not only on a first load (Task 4 e2e `test_controls_work_after_swap`).
4. **A failed fetch** (offline, 404) falls back to a normal page load. It never leaves a blank page (Task 3 `test_failed_fetch_falls_back`).
5. **The phone layout:** the player bar stays pinned at the bottom, the strip scrolls sideways, and neither covers page controls (Task 5 screenshot at 390 px).

---

### Task 1: Spike, decision 010

**Files:** `spikes/shell/{a,b}/{index,one,two}.html` and `shell-a.js`/`shell-b.js`, uploaded to `_checks/shell/`; `spikes/check19_shell.py` (Playwright); check 19; `docs/decisions/010-persistent-player.md`.

- [ ] **Step 1:** Build three tiny pages per approach. Each has the same player bar: an `<audio>` playing a newscast MP3 from the bucket, plus a docked YouTube iframe. Each has links between the pages.
- [ ] **Step 2:** Playwright script against the bucket:
  1. Tap play.
  2. Navigate 5 times, then Back twice and Forward once.
  3. After each move, record `audio.paused`, `audio.currentTime` (must keep rising), and the iframe's load count (an `onload` counter; must stay 1).
- [ ] **Step 3:** Expected: approach (b) keeps both the audio and the iframe alive. Approach (a) keeps the audio, but reloads the iframe. Record check 19.
- [ ] **Step 4:** Write decision 010 and pick the winner. If (b) passes everything, it wins: less code to ship, and embeds keep playing.
- [ ] **Step 5:** Commit.

### Task 2: Shared partials and the player API

**Files:**
- Partials: `templates/_masthead.html` (logo, nav, station strip), `templates/_player.html` (player bar)
- Every page template includes them: front/hour, story, music pick, sampler, Table, control room, settings, music meeting
- `templates/shell.js` (published as `/shell.js`, replaces `player.js`)

**Player API:** `window.wone.play({kind, src, title, subtitle, startMs, chapters, link})`, plus `pause()`, `seek()` and `now()`.
- **Kinds:** `newscast`, `story`, `table`, `preview`, `embed`
- **`preview`** plays once and never chains.
- **`embed`** puts a YouTube/Bandcamp player into the bar's embed slot.

- [ ] **Step 1: Failing tests** (`tests/test_shell_templates.py`):
  - `test_every_page_has_masthead_strip_and_player`: render each template, and find `id="wone-player"` and `id="wone-strip"` exactly once
  - `test_player_markup_has_no_autoplay`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 3: Soft navigation (the approach chosen in Task 1)

**Files:** `templates/shell.js` (navigation part); e2e `tests/e2e/test_shell_nav.py`.
- **Runs only** when `STATION_E2E=1`.
- **Uploads** the rendered sample pages to `_checks/shell-e2e/` first, then drives system Chrome.

- [ ] **Step 1: Failing e2e tests:**
  - `test_navigation_keeps_audio_playing`
  - `test_back_forward_keeps_playing`
  - `test_external_and_download_links_untouched`
  - `test_failed_fetch_falls_back`
  - `test_title_and_address_update`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 4: Page controls go through the player

**Files:**
- `shell.js`: one delegated click handler on `document` for `[data-play]` buttons, so controls work on first loads and after swaps alike
- Templates swap their inline scripts for `data-play` attributes:
  - front Play buttons and the newscast rows
  - story Listen
  - Table chapters
  - pick "Play here" (`embed` kind)
  - sampler previews (`preview` kind)
  - the big player on a music pick's page

- [ ] **Step 1: Failing tests:**
  - template tests `test_no_inline_page_scripts_left` and `test_data_play_attributes_escaped`
  - e2e `test_controls_work_after_swap`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 5: Station strip and `stations.json`

**Files:**
- `station/steps/page.py`: `stations_json(prefs, latest_newscast, stations) -> dict`, written to `stations.json` by the page step and the radio step
- `_masthead.html` strip markup
- `shell.js` strip code: fetch on load and every 60 s, render with `textContent`, expand and collapse

**Entries in `stations.json`:**
- **News:** the hour label and the lead headline; ▶ plays the newscast.
- **Each music station:** name, description, "on now" and "next", from `queue.json` (Plan B1) or the latest sampler set until then. ▶ opens the station page. Until Apple Music is connected (Plan C), it shows "Connect Apple Music for full songs".

- [ ] **Step 1: Failing tests:**
  - `test_stations_json_shape`
  - `test_strip_renders_text_not_html` (e2e with a station name containing `<b>`)
  - screenshots at 1440 and 390 px
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 6: Live, docs, review

- [ ] **Step 1:** Merge and let the next hourly build publish. On the live site, start the newscast, then visit:
  1. a story page
  2. the jazz sampler
  3. a music pick
  4. the control room
  5. Back twice

  Expected: no gap in the audio. Record it as a GIF for the demo.
- [ ] **Step 2:** Docs: check 19 live result, README "How the site plays".
- [ ] **Step 3:** Final review by a fresh Opus reviewer with this Review Focus. Fix Critical/Important findings test-first.
