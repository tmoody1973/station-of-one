# Clean Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Clean mode: skip explicit songs" switch in Settings. When it is on, the listener's player leaves out songs Apple Music marks explicit, and any host break that back-announces one.

**Architecture:** Apple's catalog marks each song `contentRating: "explicit"` (checked Nov 27: "Top Again (feat. Saba)" is explicit). The station records that mark per song, the queue carries it, and the player filters in the browser. Apple doesn't let a website read or change a listener's own explicit setting (MusicKit on the Web v3 docs, Context7 `/websites/js-cdn_music_apple_musickit_v3`), so this is our player's choice, saved in the browser like the Apple Music connection.

**Tech Stack:** Python, SQLite, the Apple Music API (Custom API connector), `templates/live.js`, `templates/shell.js`, `templates/settings.html`.

**Spec:** Tarik, Nov 27, 11:41 pm: "can we do via api and maybe create setting on our settings"; plan approved in principle: "Yes, plan it".

## Global Constraints

- Default off: the station plays what Apple allows the listener's account to play.
- The switch is per browser (`localStorage` "wone-clean"); no account, no server state.
- A break never names a song the listener didn't hear (the honest-breaks rule): a break after a block with a removed explicit song is skipped.
- No new connector; one Apple lookup per 300 songs to fill in the existing catalog.

## Review Focus

1. **Clean mode on, a whole block explicit:** the player moves on to the next segment, never stalls (Task 2 `test_clean_drops_an_all_explicit_block`).
2. **Clean mode on, the break after an explicit song:** skipped (Task 2 `test_clean_skips_the_break_that_names_it`).
3. **A song with no rating recorded yet:** treated as not explicit; it plays (Task 1 `test_unknown_rating_is_not_explicit`).
4. **Clean mode switched while listening:** applies from the next tune-in or block, never cuts a song mid-play (Task 2, by design; noted on the Settings page).
5. **Apple lookup fails during the fill-in:** songs stay unknown, nothing else changes (Task 1 `test_ratings_fill_survives_apple_errors`).

---

### Task 1: Record each song's rating

**Files:** `station/radio/resolve.py` (`Match.explicit: bool`, from `attributes.contentRating == "explicit"`), `station/radio/model.py` (candidates gain `explicit INTEGER`), the seed/scout/library writers store it, `station/radio/onair.py` (`window()` and `queue.json` items carry `explicit`), `scripts/fill_ratings.py` (`fill_ratings(gw, conn, db) -> int`: `GET /v1/catalog/us/songs?ids=` in batches of 300 for candidates with a song id and no rating); tests `tests/radio/test_ratings.py`.

- [ ] Failing tests: `test_explicit_recorded_on_match`, `test_queue_items_carry_explicit`, `test_unknown_rating_is_not_explicit`, `test_ratings_fill_in_batches`, `test_ratings_fill_survives_apple_errors`.
- [ ] Implement; run on a database copy first; commit.

### Task 2: The switch and the player

**Files:** `templates/settings.html` (a "Listening" section: the switch, one line on what it does and that it applies from the next block), `templates/shell.js` (reads `wone-clean`; passes it to `liveSegments`), `templates/live.js` (`liveSegments(items, nowMs, {clean})`: drops explicit songs; drops the next `break`/`backsell` after any dropped song); tests `tests/js/segments.test.mjs`, e2e `tests/e2e/test_station_playback.py`.

- [ ] Failing tests: JS `test_clean_drops_explicit_songs`, `test_clean_skips_the_break_that_names_it`, `test_clean_drops_an_all_explicit_block`, `test_clean_off_changes_nothing`; e2e `test_settings_clean_switch_saved`.
- [ ] Implement; republish the test copy; run all suites; commit.

### Task 3: Review and live

- [ ] Fresh review; fix Critical/Important test-first.
- [ ] With Tarik's go: merge; run `scripts/fill_ratings.py` on the real database (backup first); publish the player and Settings; check a known explicit song ("Top Again") is marked and skipped in clean mode.
