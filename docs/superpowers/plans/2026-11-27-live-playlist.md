# Live Playlist and Station Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** What a listener sees always matches what they hear; the Rhythm Lab page reads like a radio station's playlist; the strip opens station pages; updated pages reach everyone; the program director's page shows the schedule.

**Architecture:** Plan C plays songs back to back and skips the schedule's ID, news and break slots (no audio until Plan B2), so a listener's player runs ahead of the clock (353 s in the 4 pm hour, Nov 27). So "now" has two sources: the player's own song while this browser plays the station, otherwise the station clock. The station page, strip and playlist all ask `shell.js` which applies. Pages and data files that change are published `private, no-cache` so Tigris's regional cache stops serving overwritten copies (Tigris docs: objects marked `private` or `no-store` aren't cached).

**Tech Stack:** Python/Jinja templates, `templates/shell.js`, Playwright e2e with the stand-in MusicKit, pytest.

**Spec:** Tarik, Nov 27, 4:35-4:38 pm: "why is the player playing a different song than what is displayed in the header", "when I click Rhythm Lab it doesn't go to its page", "should we show playlist live when a song is played, not what is coming up", "should the schedule of songs be shown on the program director page"; approved fixes a-f plus g.

## Global Constraints

- Text from feeds, Apple or the schedule goes into pages as text only (`textContent`, Jinja autoescape).
- Nothing plays without a tap; one sound at a time (Plan C rules stand).
- Permanent assets (audio, images, fonts, renamed files) keep their long cache; only pages, JSON, XML and JS go `private, no-cache`.
- No change to the scheduler or the queue format beyond adding fields.

## Review Focus

1. **The listener's player is minutes ahead of the clock:** On now, the strip chip and the playlist name the song they hear (Task 3 `test_now_follows_the_player`).
2. **Nobody is listening in this browser:** On now follows the clock; a break shows "Up next" (Task 3 `test_now_follows_the_clock_when_not_listening`).
3. **An overwritten page or JSON file:** a plain request gets the new copy (Task 1 `test_changing_files_are_private_no_cache` plus a live check).
4. **Older pages and the sampler station (ONE Jazz):** no playlist script errors, its chip still opens its page (Task 2 `test_sampler_chip_opens_page`).
5. **A queue with no songs left:** the station page and the strip say "Nothing scheduled", no blank box (Task 3 `test_empty_queue_page`).

---

### Task 1: Pages that reach everyone, and the Music link (fixes f, b)

**Files:** `station/steps/publish.py` (`cache_control`); `templates/shell.js` (page-swap fetch with `cache: "no-cache"`); `templates/_masthead.html` (Music → `/radio/rhythm-lab/index.html`); tests in `tests/test_publish.py`, `tests/test_shell_templates.py`.

- [ ] **Step 1: Failing tests:** `test_changing_files_are_private_no_cache` (`index.html`, `data/stations.json`, `feed.xml`, `shell.js` → `"private, no-cache"`; an immutable asset and the MP4 unchanged); `test_music_link_goes_to_the_flagship`.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run, plus the e2e suite (tests that reached ONE Jazz through "Music" now go through its strip chip). Expected: PASS. Commit.

### Task 2: A KCRW-pattern station strip that follows the player (fixes a, c for the strip, d)

Tarik's KCRW screenshots (structure only, in our Bauhaus look; no real outlet's design is copied): an "on air" pill; per station a **name box with ▶ that plays it**, then **what's on now** (a link to the station page); at the right **"More station info"**, opening a panel with one column per station: name, on-air pill, artwork, start time, what's on, description, **Next up** with its time, and links to the station page (and for clock stations, the program director's page).

**Files:** `station/radio/onair.py` (`latest.json` tracks for clock stations cover 3 hours, each with `starts_at`, `ends_at`, `at`, `song_id`, `title`, `artist`, `artwork_url`); `station/steps/stations.py` (every entry: `now` and `next` as `{at, title, art}`; clock stations add `schedule`; News: the current newscast and the next one's time); `templates/shell.js` (renders the strip and panel; a clock station's now/next come from `schedule` by the clock, **or from the player's own song while this browser plays that station**; redrawn on every song change); `templates/_bauhaus.css`; tests in `tests/test_stations_json.py` and e2e.

- [ ] **Step 1: Failing tests:** `test_strip_entries_have_now_next_and_description`, `test_clock_station_publishes_its_schedule`, `test_news_next_is_the_next_newscast`; e2e `test_strip_name_box_plays` (News ▶ plays the newscast; Rhythm Lab ▶ tunes in), `test_strip_now_links_to_station_page`, `test_more_station_info_panel`, `test_strip_follows_the_player` (Focus 1: the player plays a song the schedule doesn't have now; Rhythm Lab's strip text names the player's song), `test_sampler_chip_opens_page` (Focus 4).
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run. Expected: PASS. Commit.

### Task 3: The station page as a live playlist (fixes c, e)

**Files:** `station/radio/onair.py` (`station_page(db, station, prefs, now) -> str`: the queue window from 3 hours back to 2 ahead, rows newest first, each row with `data-song`, `data-starts`, `data-ends`; used by `run_clock` and the e2e publisher); `templates/radio.html` (clock stations: "Now playing" box, then one "Playlist" list where `shell.js` labels rows "Up next", "Now" or the start time and hides later songs); `templates/shell.js` (`markNow` uses the player's song id while this browser plays the station, else the clock); `spikes/shell_e2e_publish.py` (publishes a Rhythm Lab page from the real queue); tests in `tests/radio/test_onair.py`, e2e.

- [ ] **Step 1: Failing tests:** `test_station_page_lists_played_newest_first` (rows reverse-chronological, 3 hours back); e2e `test_now_follows_the_player` (Focus 1: stub plays a song 3 rows ahead of the clock; box, highlighted row and strip chip show it), `test_now_follows_the_clock_when_not_listening` (Focus 2), `test_empty_queue_page` (Focus 5).
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run. Expected: PASS. Commit.

### Task 4: The schedule on the program director's page (g)

**Files:** `station/radio/onair.py` (`meeting_view` also returns the next 2 hours of queue items with category and energy); `templates/meeting.html` (first section "On the schedule": time, slot, category, song, energy; IDs, news and breaks shown as slots; page heading "The program director"); `templates/radio.html` (link text "The program director: schedule and music meeting"); tests in `tests/radio/test_onair.py`.

- [ ] **Step 1: Failing tests:** `test_pd_page_shows_the_schedule` (times in Central, slot kinds, category letters, escaped titles).
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run. Expected: PASS. Commit.

### Task 5: Live, review

- [ ] **Step 1:** Fresh Opus review of the branch with this Review Focus; fix Critical/Important test-first.
- [ ] **Step 2:** Merge; publish by hand (page, publish, Rhythm Lab schedule-only); check a plain request gets each changed page; screenshot the Rhythm Lab page and the PD page.
