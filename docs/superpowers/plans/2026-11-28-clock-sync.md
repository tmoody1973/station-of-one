# Clock Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** What a listener hears starts at the time the page shows, within a few seconds: breaks are scheduled at their real length, the leftover before :00/:30 is filled with music, and the player follows the clock at every boundary.

**Architecture:** Evidence (Nov 28, 5:43 am): Tarik's Rhythm Lab player played "Kerala" (scheduled 6:30:08) at 5:43, 47 minutes early. The player never waits and never re-syncs: when a segment ends early (a break shorter than its planned slot, a skipped song, an unvoiced slot) the next starts at once, and nothing pulls it back. Planned-but-unplayed break time alone measured 16-93 s per hour on Rhythm Lab. Three fixes: the schedule carries each voiced item's real length; each break is written to fill its slot (the host back-times, as on air); the player follows the clock at every segment boundary (wait a few seconds, seek in, or rejoin live).

**Tech Stack:** `templates/shell.js`, `templates/live.js`, Python (`station/radio/voicing.py`), Playwright e2e with the stand-in MusicKit.

**Spec:** Tarik, Nov 28 5:47 am: "why can't it sync to the clock when the song is actually played" → chose "Per-song sync" (replacing his 5:45 choice "Rejoin live at :00": "At the top of each hour, if the player is more than 30 s off the clock, it jumps to the station ID on time, like tapping Back to live. Cost: if it was ahead, you may hear a song or two again." Earlier: "can the time a song and break plays sync to the computer's clock".

## Global Constraints

- Sync acts only at a segment boundary, never cutting into a song or a break that is playing.
- Never dead air beyond a few seconds: a wait is under 10 s; leftover time is filled with music.
- Per-song sync ships only together with real lengths (Task 1 before Task 2 goes live).
- One sound at a time (Plan C/B2 rules stand).
- The page's "Now" keeps following the player while listening.

## Review Focus

1. **Player 47 minutes ahead:** the next boundary rejoins the clock's segment (Task 2 `test_rejoins_when_far_off`, e2e `test_player_rejoins_the_clock`).
2. **Player a few seconds early:** a short wait, never more than 10 s of silence (Task 2 `test_waits_a_few_seconds_when_early`).
3. **Player behind** (buffering, a slow load): the next item starts that far in (Task 2 `test_seeks_in_when_late`).
4. **A long break slot (80 s):** the host's break is written to about that length, so the next song starts near its scheduled time (Task 1 `test_break_written_to_its_slot`).
5. **A voiced break still shorter than its slot (no facts):** the player plays through without dead air and the next boundary's sync absorbs the gap (Task 2 `test_plays_through_leftover_near_a_fixed_point`).

---

### Task 1: Breaks fill their slot, and the schedule carries real lengths

The scheduler already tries extra songs before each fixed point; the leftover exists because no rested song fits (`scheduler._close_gap` gives it to the segment's last break, which is why Rhythm Lab plans 42-89 s breaks). So the leftover is filled the radio way: the host talks to time.

**Files:** `station/radio/breaks.py` (`script_for(..., target_s)`: the writer is asked for about 2.5 words per second of the slot, capped at 90 s; with more time it may use a second cited fact; the plain back-announce is unchanged), `station/radio/voicing.py` (passes each item's planned slot; after voicing, the queue row keeps the planned `duration_ms` and stores `audio_ms`; the browser plays real lengths and syncs at boundaries); tests `tests/radio/test_breaks.py`, `tests/radio/test_voicing.py`.

- [ ] Failing tests: `test_break_written_to_its_slot` (an 80 s slot asks the writer for about 200 words; a 25 s slot for about 60); `test_long_slot_may_use_two_facts`; `test_voicing_passes_the_slot_length`.
- [ ] Implement; rehearse on a database copy and measure real vs planned lengths; commit.

### Task 2: The player follows the clock at every boundary

**Files:** `templates/live.js` (`syncAction(seg, nowMs, slackMs) -> {kind: "play"|"wait"|"seek"|"rejoin", ms}`: early by under 10 s, wait; late by under 30 s, seek that far in; early by up to the leftover before a fixed point, play (no dead air); otherwise rejoin live), `templates/shell.js` (in `nextSegment`, act on `syncAction`); tests `tests/js/segments.test.mjs`, e2e `tests/e2e/test_station_playback.py`.

- [ ] Failing tests: JS `test_waits_a_few_seconds_when_early`, `test_seeks_in_when_late`, `test_plays_through_leftover_near_a_fixed_point`, `test_rejoins_when_far_off`; e2e `test_player_rejoins_the_clock` (next segment 10 minutes ahead of now: the next setQueue is the clock's song with a start offset), `test_short_wait_then_play`.
- [ ] Implement; republish the test copy; run all suites; commit.

### Task 3: Review and live

- [ ] Fresh review; fix Critical/Important test-first.
- [ ] With Tarik's go: merge; publish the player; check the live queue's spoken items carry real lengths and the times on the page match what plays within a few seconds.
