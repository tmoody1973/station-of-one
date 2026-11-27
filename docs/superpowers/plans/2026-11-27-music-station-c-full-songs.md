# Music Station, Plan C: Full Songs Through Apple Music Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A listener with an Apple Music subscription taps "Listen live" (or "Connect Apple Music" in settings), signs in once, and hears Rhythm Lab's full songs in the site's one player bar, joined at the current song and second, with working play, pause, skip and "Back to live", playing on across page changes. Listeners without Apple Music keep the tap-to-play previews.

**Architecture:** Plan B1 publishes `data/radio/rhythm-lab/queue.json` (start times and Apple song ids). The browser does the rest: `shell.js` (the site shell's player, decision 010) loads MusicKit on the Web v3 from Apple's CDN only when a listener taps, configures it with a public, origin-locked web developer token from `/data/musickit.json`, and asks a small pure module, `live.js`, which songs are live and how far into the first one to start. Songs play on the listener's device through their own subscription; nothing of Apple's audio touches our servers.

**Tech Stack:** MusicKit on the Web v3 (`https://js-cdn.music.apple.com/musickit/v3/musickit.js`, checked in Context7 Nov 27: `musickitloaded`, `MusicKit.configure({developerToken, app})`, `getInstance()`, `authorize()`, `unauthorize()`, `isAuthorized`, `setQueue({songs, startTime, startPlaying})`, `skipToNextItem()`, `play()`, `pause()`, `nowPlayingItem`, `currentPlaybackTime`, `currentPlaybackDuration`, `addEventListener('nowPlayingItemDidChange', ...)`); plain browser JavaScript; Node's built-in test runner (`node --test`, Node 26) for `live.js`; Playwright (system Chrome) e2e with a stub MusicKit; Python/Jinja for pages.

**Spec:** PRD `~/Downloads/Station of One Agent-Programmed Music Stations PRD.md`: "Listener experience" (Connect, Tune in mid-song), "Without Apple Music", "Playback" (`now - starts_at`, skip unavailable songs), "Requirements and limits" (terms checked 27 Nov: listeners start playback, working play/pause/skip, rejoining live is a separate button, no ads/paywall/data collection gating playback, never our audio over a song). Tarik, Nov 27: "I assume a user can authorize Apple Music premium in the settings" (answered yes, Plan C). Decision 008.

## Global Constraints

- **The web developer token is public by design and origin-locked.** Signed on Tarik's Mac with `scripts/apple_music_token.py --origin https://patient-mountain-3400.fly.storage.tigris.dev --bare --days 60`, separate from the server token in the Apple Music connector (which never leaves the gateway). It reaches the Sprite only through Tarik's own interactive command, lives in git-ignored `data/musickit_token`, and is published as `/data/musickit.json`. Never committed, never printed in logs, never handled by Claude. **Needs Tarik's OK at plan review** (it is the one key-like value outside the gateway); recorded as decision 012.
- MusicKit loads only after a listener taps (no Apple script on page load for everyone); nothing plays without a tap.
- Play, pause and skip always work; "Back to live" is a separate button.
- One sound at a time: starting the station pauses our audio and any docked embed; starting our audio or an embed pauses the station. Our audio never plays over a song.
- Previews stay tap-to-play, never advance on their own, and keep their "Listen on Apple Music" link.
- In this plan the station stream is songs only: the client skips the queue's spoken items (IDs, breaks, news). Voice breaks and news inside the stream are Plan B2.
- No ads, sign-up or data collection in front of playback. We store nothing about the listener; MusicKit keeps its own sign-in.

## Review Focus

1. **The listener declines sign-in, or has no subscription:** `authorize()` rejects; the bar says "Full songs need an Apple Music subscription", nothing plays, previews still work (Task 3 `test_declined_sign_in_keeps_previews`).
2. **Joining during a break or ID:** no song is live; playback starts the next song at 0 s, not partway into the wrong song (Task 2 `joins next song at zero during a break`).
3. **The newscast tapped while the station plays, and the station tapped while the newscast plays:** never two sounds (Task 3 `test_one_sound_at_a_time`).
4. **No token yet, or an expired one** (`/data/musickit.json` 404 or `configure()` rejects): a station tap says "Full songs aren't available right now"; the page keeps working (Task 3 `test_missing_token_fails_quietly`).
5. **A song not available in the listener's country:** skipped; after 3 in a row the bar says so (Task 3 `test_unavailable_songs_skip`).

---

### Task 1: The web token, published

**Files:** `station/steps/page.py` (write `site/data/musickit.json` when `data/musickit_token` exists); `.gitignore` (`data/` is already ignored: assert it); `scripts/set_web_token.sh` (Tarik runs on his Mac: `pbpaste | sprite exec -s brave-indigo-lion -- bash -c 'cat > /home/sprite/station/data/musickit_token'`, prints only the byte count); tests in `tests/test_page.py`.

**Interfaces — Produces:** `musickit_config(token_path: Path) -> dict | None` returning `{"developerToken": str, "app": {"name": "ONE 1.0 FM", "build": "2026.11.27"}}`, or None with no file or an empty one.

- [ ] **Step 1: Failing tests:**
  - `test_musickit_json_written_from_token_file`: a temp token file `abc.def.ghi` → `site/data/musickit.json` holds it and the app name; listed in the files the page step writes.
  - `test_no_token_no_musickit_json`
  - `test_token_file_is_git_ignored`: `git check-ignore data/musickit_token` succeeds.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run. Expected: PASS. Commit.

### Task 2: What's live (`templates/live.js`)

**Files:** `templates/live.js` (published beside `shell.js` by the page step); `tests/js/live.test.mjs`.

**Interfaces — Produces:** a plain script defining `window.woneLive = { liveStart(items, nowMs) }` (and `module.exports` under Node). `liveStart` takes queue items (`{starts_at, kind, song_id, duration_ms}`) and returns `{songIds: string[], startTime: number}`: the song playing at `nowMs` and every later song, in order; `startTime` is seconds into the first one (`(nowMs - start) / 1000`, floored at 0). Spoken items and items without `song_id` are left out.

- [ ] **Step 1: Failing tests** (`node --test tests/js/`):
  - `joins mid-song`: now 90 s into a 240 s song → that song first, `startTime` 90.
  - `joins next song at zero during a break`: now inside a `break` → the next song first, `startTime` 0.
  - `nothing after the last song`: → `{songIds: [], startTime: 0}`.
  - `skips spoken items and missing ids`.
  - `uses UTC ISO times`: `starts_at` with `+00:00` compared as instants, not text.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run. Expected: PASS. Commit.

### Task 3: The station in the player bar (`templates/shell.js`, `templates/_player.html`)

**Files:** `templates/shell.js`, `templates/_player.html` (add `#wone-skip-song` "Skip" and `#wone-live` "Back to live", hidden unless a station plays; a `#wone-msg` line for short messages); `tests/e2e/test_station_playback.py` (Playwright with a stub `window.MusicKit` installed by `add_init_script`, so no Apple account is needed; the stub records calls and can be told to reject `authorize`/`configure` or fail a song); `spikes/shell_e2e_publish.py` (also publishes a test `queue.json` around "now" and a fake `musickit.json`).

**Interfaces:**
- Consumes: `/data/musickit.json` (Task 1), `woneLive.liveStart` (Task 2).
- Produces: `data-play` kind `"station"`: `{"kind": "station", "src": "/data/radio/<id>/queue.json", "title": "<station name>", "label": "<station name> · live"}`; `window.wone.connect(): Promise<boolean>` and `window.wone.disconnect(): Promise<void>` for Task 4.

**Behavior:** on a station tap: load `live.js` and MusicKit (use an existing `window.MusicKit` if present, else inject Apple's v3 script and wait for `musickitloaded`), fetch `musickit.json`, `configure`, `authorize` (inside the tap), fetch the queue, `liveStart(items, Date.now())`, then `setQueue({songs, startTime, startPlaying: true})`. The bar shows the now-playing title and artist (`nowPlayingItemDidChange`), time and progress; ▶ toggles `play()`/`pause()`; Skip calls `skipToNextItem()`; Back to live repeats the join. When the queue runs out it rejoins live. A playback error skips to the next song; 3 in a row shows "Some songs aren't available in your country".

- [ ] **Step 1: Failing tests:**
  - `test_station_joins_live`: tap → stub saw `authorize`, then `setQueue` with the live song first and `startTime` within 2 s of expected.
  - `test_skip_and_back_to_live`: Skip → `skipToNextItem` called; Back to live → a fresh `setQueue` from live.
  - `test_station_keeps_playing_across_pages`: swap to settings and back; stub still playing, no second `setQueue`.
  - `test_one_sound_at_a_time` (Focus 3)
  - `test_declined_sign_in_keeps_previews` (Focus 1)
  - `test_missing_token_fails_quietly` (Focus 4)
  - `test_unavailable_songs_skip` (Focus 5)
  - `test_musickit_not_loaded_until_tap`: no request to `js-cdn.music.apple.com` on page load.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run (`STATION_E2E=1 ... tests/e2e`). Expected: PASS, and the 11 shell tests still pass. Commit.

### Task 4: Where listeners connect and tune in

**Files:**
- `templates/settings.html`: an "Apple Music" section: status ("Connected" / "Not connected"), `Connect Apple Music` and `Disconnect` buttons (`data-apple="connect" | "disconnect"`, handled by `shell.js`), and one line on what connecting does ("Full songs play through your own Apple Music subscription; this station stores nothing about you").
- `templates/radio.html`: for a clock station, the disabled "coming soon" button becomes `Listen live` with `data-play` kind `station`; the sampler (ONE Jazz) keeps the disabled button reworded "Full songs come when this station runs around the clock".
- `station/steps/stations.py`: clock stations get `"play": {"kind": "station", ...}` so the strip chip tunes in.
- Tests: `tests/test_shell_templates.py`, `tests/test_stations_json.py`, plus e2e `test_connect_from_settings` and `test_strip_chip_tunes_in`.

- [ ] **Step 1: Failing tests** (template markup, stations.json play item for `rhythm-lab` and none for `uk-jazz`, the two e2e flows with the stub).
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run. Expected: PASS. Commit.

### Task 5: Live, docs, review

- [ ] **Step 1 (Tarik):** sign the web token on his Mac and run `scripts/set_web_token.sh`; the next build publishes `/data/musickit.json`.
- [ ] **Step 2 (Tarik + Claude):** on Tarik's subscribed account in Chrome and Safari (iPhone): Listen live joins mid-song, skip, Back to live, change pages, tap the newscast and back. Record it for the demo (the judges likely have no subscription; PRD "Judge access").
- [ ] **Step 3:** Docs: decision 012 (the public web token), check 21 (real playback results), README "How the site plays".
- [ ] **Step 4:** Final review by a fresh Opus reviewer with this Review Focus. Fix Critical/Important findings test-first, then merge.
