# Clock Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A listener's player stays with the station clock: once an hour it rejoins live at the top of the hour when it has drifted, and breaks are scheduled at their real length so drift builds more slowly.

**Architecture:** Evidence (Nov 28, 5:43 am): Tarik's Rhythm Lab player played "Kerala" (scheduled 6:30:08) at 5:43, 47 minutes early. The player never waits and never re-syncs: when a segment ends early (a break shorter than its planned slot, a skipped song, an unvoiced slot) the next starts at once, and nothing pulls it back. Planned-but-unplayed break time alone measured 16-93 s per hour on Rhythm Lab. Two fixes: the player rejoins live at the first segment boundary after each top of the hour when it is more than 30 s off; the schedule replaces each voiced item's planned length with its real length.

**Tech Stack:** `templates/shell.js`, `templates/live.js`, Python (`station/radio/voicing.py`), Playwright e2e with the stand-in MusicKit.

**Spec:** Tarik, Nov 28 5:45 am, choosing "Rejoin live at :00": "At the top of each hour, if the player is more than 30 s off the clock, it jumps to the station ID on time, like tapping Back to live. Cost: if it was ahead, you may hear a song or two again." Earlier: "can the time a song and break plays sync to the computer's clock".

## Global Constraints

- The rejoin happens only at a segment boundary, never cutting into a song or a break that is playing.
- Threshold 30 s; once per hour.
- One sound at a time (Plan C/B2 rules stand).
- The page's "Now" keeps following the player while listening.

## Review Focus

1. **Player 47 minutes ahead at 5:59:** the first boundary after 6:00 rejoins the clock's segment (Task 1 `test_rejoins_live_after_the_hour`).
2. **Player within 30 s of the clock:** no rejoin, nothing interrupted (Task 1 `test_no_rejoin_when_close`).
3. **Player behind the clock** (buffering, a paused tab): the same rejoin catches it up (Task 1 `test_rejoins_when_behind`).
4. **The tab was asleep across several hours:** one rejoin, not one per missed hour (Task 1 `test_one_rejoin_per_hour`).
5. **A voiced item's real length differs from its slot:** the published queue carries the real length; items after it in the same hour move up so the plan matches what plays (Task 2 `test_real_lengths_retime_the_hour`).

---

### Task 1: Rejoin live after the top of the hour

**Files:** `templates/live.js` (`shouldResync(segStartsAt, nowMs, lastResyncHour, nowHour) -> boolean`: true when `nowHour !== lastResyncHour` and `|Date.parse(segStartsAt) - nowMs| > 30000`), `templates/shell.js` (in `nextSegment`, before playing a segment: if `shouldResync`, record the hour and `join(false)` instead); tests `tests/js/segments.test.mjs`, e2e `tests/e2e/test_station_playback.py`.

- [ ] Failing tests: JS `test_rejoins_live_after_the_hour`, `test_no_rejoin_when_close`, `test_rejoins_when_behind`, `test_one_rejoin_per_hour`; e2e `test_player_rejoins_the_clock` (a queue whose next segment is 10 minutes ahead of now, with the hour just turned: the next setQueue is the clock's song with a start offset).
- [ ] Implement; republish the test copy; run all suites; commit.

### Task 2: Real lengths in the schedule

**Files:** `station/radio/voicing.py` (after voicing, set the item's `duration_ms` to its audio length and shift later items in the same segment up to the next :00/:30 fixed point earlier by the difference; the gap before the fixed point goes to the last spoken item), test `tests/radio/test_voicing.py`.

- [ ] Failing test: `test_real_lengths_retime_the_hour`.
- [ ] Implement; run all suites; commit.

### Task 3: Review and live

- [ ] Fresh review; fix Critical/Important test-first.
- [ ] With Tarik's go: merge; publish the player; check the live queue's spoken items carry real lengths.
