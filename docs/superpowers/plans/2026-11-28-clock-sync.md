# Clock Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** What a listener hears starts at the time the page shows, within a few seconds: breaks are scheduled at their real length, the leftover before :00/:30 is filled with music, and the player follows the clock at every boundary.

**Architecture:** Evidence (Nov 28, 5:43 am): Tarik's Rhythm Lab player played "Kerala" (scheduled 6:30:08) at 5:43, 47 minutes early. The player never waits and never re-syncs: when a segment ends early (a break shorter than its planned slot, a skipped song, an unvoiced slot) the next starts at once, and nothing pulls it back. Planned-but-unplayed break time alone measured 16-93 s per hour on Rhythm Lab. Two fixes: the player rejoins live at the first segment boundary after each top of the hour when it is more than 30 s off; the schedule replaces each voiced item's planned length with its real length.

**Tech Stack:** `templates/shell.js`, `templates/live.js`, Python (`station/radio/voicing.py`), Playwright e2e with the stand-in MusicKit.

**Spec:** Tarik, Nov 28 5:47 am: "why can't it sync to the clock when the song is actually played" → chose "Per-song sync" (replacing his 5:45 choice "Rejoin live at :00": "At the top of each hour, if the player is more than 30 s off the clock, it jumps to the station ID on time, like tapping Back to live. Cost: if it was ahead, you may hear a song or two again." Earlier: "can the time a song and break plays sync to the computer's clock".

## Global Constraints

- Sync acts only at a segment boundary, never cutting into a song or a break that is playing.
- Never dead air beyond a few seconds: a wait is under 10 s; leftover time is filled with music.
- Per-song sync ships only together with real lengths (Task 1 before Task 2 goes live).
- One sound at a time (Plan C/B2 rules stand).
- The page's "Now" keeps following the player while listening.

## Review Focus

1. **Player 47 minutes ahead at 5:59:** the first boundary after 6:00 rejoins the clock's segment (Task 1 `test_rejoins_live_after_the_hour`).
2. **Player within 30 s of the clock:** no rejoin, nothing interrupted (Task 1 `test_no_rejoin_when_close`).
3. **Player behind the clock** (buffering, a paused tab): the same rejoin catches it up (Task 1 `test_rejoins_when_behind`).
4. **The tab was asleep across several hours:** one rejoin, not one per missed hour (Task 1 `test_one_rejoin_per_hour`).
5. **A voiced item's real length differs from its slot:** the published queue carries the real length; items after it in the same hour move up so the plan matches what plays (Task 2 `test_real_lengths_retime_the_hour`).

---

### Task 1: Real lengths in the schedule, leftover filled with music

**Files:** `station/radio/voicing.py` (after voicing an item, set its `duration_ms` to its audio length and move the later items of its segment up to the next :00/:30 fixed point earlier by the difference), `station/radio/scheduler.py` (reuse the extra-song rule: when the leftover before a fixed point is at least the shortest rested song, insert the best-fitting one; any remainder goes to the last spoken item before the fixed point); tests `tests/radio/test_voicing.py`, `tests/radio/test_scheduler.py`.

- [ ] Failing tests: `test_real_lengths_retime_the_hour` (a break voiced at 20 s in a 60 s slot: the next song starts 40 s earlier, the fixed point doesn't move); `test_leftover_before_a_fixed_point_gets_a_song` (a 3-minute leftover gets a rested song of 3 minutes or less, separation rules held); `test_short_leftover_goes_to_the_last_spoken_item`.
- [ ] Implement; commit.

### Task 2: The player follows the clock at every boundary

**Files:** `templates/live.js` (`syncAction(seg, nowMs, slackMs) -> {kind: "play"|"wait"|"seek"|"rejoin", ms}`: early by under 10 s, wait; late by under 30 s, seek that far in; early by up to the leftover before a fixed point, play (no dead air); otherwise rejoin live), `templates/shell.js` (in `nextSegment`, act on `syncAction`); tests `tests/js/segments.test.mjs`, e2e `tests/e2e/test_station_playback.py`.

- [ ] Failing tests: JS `test_waits_a_few_seconds_when_early`, `test_seeks_in_when_late`, `test_plays_through_leftover_near_a_fixed_point`, `test_rejoins_when_far_off`; e2e `test_player_rejoins_the_clock` (next segment 10 minutes ahead of now: the next setQueue is the clock's song with a start offset), `test_short_wait_then_play`.
- [ ] Implement; republish the test copy; run all suites; commit.

### Task 3: Review and live

- [ ] Fresh review; fix Critical/Important test-first.
- [ ] With Tarik's go: merge; publish the player; check the live queue's spoken items carry real lengths and the times on the page match what plays within a few seconds.
