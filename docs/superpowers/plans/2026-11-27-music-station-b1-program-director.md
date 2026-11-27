# Music Station, Plan B1: The Agent as Program Director Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The station programs like a real one, 24 hours a day.
- **Songs** live in rotation categories (Power, Medium, Light/New, Recurrent, Gold), each with its own rest time.
- **Every hour** follows a clock: day and overnight differ.
- **A scheduler** fills each slot with the longest-rested song that passes the separation rules.
- **A weekly music meeting:** Jev decides adds, moves and drops. Every decision is logged and shown on a public page.
- **A queue** with exact start times is kept ahead around the clock and published for the player.

**Architecture:** The PD's judgment is Jev's (typed questions, logged). The PD's rules are code: categories, rests, clocks, separation, sizes. That is the same split as the newscast: "Jev decides; code applies the thresholds". Plan A's simple `program_block` is replaced by `schedule_hour`, which writes `queue` rows. The `radio` step runs every hour, overnight too (radio only, no newscast). Plan B2 renders the voice items this plan only reserves (`id`, `break`, `tease`, `backsell`, `news`). Plan C plays the queue live through MusicKit.

**Tech Stack:** Python 3.13, SQLite, Jinja2, TypeSafe Jev, Cloudflare Worker cron (`trigger/`), pytest with `FakeGateway`.

**Spec:** PRD `~/Downloads/Station of One Agent-Programmed Music Stations PRD.md` ("The hour", "Station model: flow, talk", "Flagship (live)", agent tools `get_history`/`get_clock`/`queue_track`). Tarik, Nov 27: rotation categories, hour clocks and a music meeting, "the agent acts like a program director", using Claude's defaults (message "Plan B a"); 24/7 as a shared schedule played in each listener's browser, not a broadcast stream (the PRD's non-goal).

## Global Constraints

- Jev decides adds, moves and drops (typed questions, every answer logged with `record_decision`). Code applies categories, sizes, rests, clocks and separation. A language model never picks the next song.
- **Default rotation** (in `config/stations/uk-jazz.json` `rotation`, editable):

  | Category | Size | Rest (hours) |
  |---|---|---|
  | A Power | 8 | 3.5 |
  | B Medium | 14 | 7 |
  | C Light/New | 14 | 12 |
  | R Recurrent | 35 | 36 |
  | G Gold | 300 | 96 |

- **Default day clock** (07:00–18:59 local), slots in order:

  | Time | Slots |
  |---|---|
  | :00 | `id`, `news` |
  | :05 onward | A, G, C, `break`, B, R, A |
  | :30 | `id_tease`, then G, N, `break`, B, R, C |
  | :55 | `backsell` |

- **Overnight clock** (19:00–06:59):

  | Time | Slots |
  |---|---|
  | :00 | `id`, then G, A, G, R, `break`, G, B |
  | :30 | `id`, then G, R, G, `break`, C, G |
  | :55 | `backsell` |

  `N` means a C song added within the last 7 days.
- **Separation (hard):** no artist twice in 3 hours; no two songs of 7 minutes or longer back to back; energy (1 low, 2 mid, 3 high) never jumps by 2 between neighbours.
- **Separation (soft, in this order of relaxing):** era alternation, then vocal/instrumental balance. Artist separation never relaxes.
- **Fixed points:** `:00` and `:30` items start on time. A song that would cross a fixed point is swapped for a shorter eligible one, or the gap goes to the break before it (PRD "Long tracks squeeze the hour").
- **The queue is kept at least 2 hours ahead.** The radio step runs every hour, around the clock.
- **No Apple audio** touches our servers. Queue rows carry song ids and timing only.

## Review Focus

1. **An empty category** (C has no songs on day one): the slot falls back A→B→C→R→G, then any eligible song, never an empty slot (Task 5 `test_empty_category_falls_back`).
2. **Too few songs to respect separation** (12 songs, 3 artists): soft rules relax, artist separation never does, and the slot is left to a longer break rather than repeating an artist (Task 5 `test_separation_relaxes_soft_rules_first`).
3. **A 10-minute track before :30:** never pushes the :30 ID late (Task 5 `test_fixed_points_start_on_time`).
4. **The music meeting** never moves more than 25% of a category in one meeting, and never leaves A below half its size (Task 4 `test_meeting_caps_churn`).
5. **Daylight saving:** the day/overnight clock is chosen by local time (America/Chicago), so a 25-hour day doesn't double an hour (Task 5 `test_clock_by_local_hour`).

---

### Task 1: Rotation settings and tables

**Files:** `config/stations/uk-jazz.json` (`rotation`, `clocks`, `separation`); `station/radio/model.py` (`Rotation`, `Category`, `Clock` dataclasses on `StationConfig`; `open_radio` adds the tables below); tests in `tests/radio/test_model.py`.

**Tables:**
- `rotation(station_id, candidate_id, category, energy, vocal, added_at, moved_at, plays, last_played_at)`
- `queue(station_id, starts_at, kind, candidate_id, song_id, duration_ms, category, note, source_url, PRIMARY KEY(station_id, starts_at))`

- [ ] **Step 1: Failing tests:**
  - `test_rotation_defaults_load`: the five categories with sizes and rests above
  - `test_clocks_load_day_and_overnight`
  - `test_tables_created`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 2: Song tags by Jev (`station/radio/tags.py`)

**Interfaces — Produces:** `tag_songs(gw, items: list[dict]) -> tuple[dict[str, dict], dict[str, dict], str | None]`. One batched request with two questions per song:
- `energy_{i}`: choice `low | mid | high`
- `vocal_{i}`: noul, "has sung vocals"

Code maps energy to 1, 2, 3.

- [ ] **Step 1: Failing tests:**
  - `test_tags_map_choice_and_noul`
  - `test_tags_batch_by_20`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 3: Buzz (`station/radio/buzz.py`)

**Interfaces — Produces:** `buzz(db, station_id, artist: str, since: datetime) -> int`. It counts the station's feed items in the window that mention the artist (normalized whole-word match in title or excerpt). Seed-list items don't count.

- [ ] **Step 1: Failing tests:**
  - `test_buzz_counts_mentions_in_window`
  - `test_seed_items_do_not_count`
  - `test_partial_name_does_not_count` ("Shabaka" vs "Shabakaville")
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 4: The music meeting (`station/radio/meeting.py`)

**Interfaces — Produces:** `MeetingResult(adds, moves, drops, notes)`; `music_meeting(gw, station, db, now) -> MeetingResult`.

**Who's considered:**
- **Add candidates:** resolved songs not in rotation, with fit ≥ 0.5.
- **Members:** every song in rotation.

**Jev's questions, one batch:**
- `add_{i}` (noul): "Should `songs[i]` join the station's rotation now?" State: brief, fit, buzz, source, era.
- `up_{i}` (noul) for C and B songs.
- `burned_{i}` (noul) for A songs.

**Code then applies:**
- **Adds:** add ≥ 0.6 joins C. Catalog finds older than 10 years join G instead.
- **Moves up:** up ≥ 0.6 moves C→B and B→A.
- **Burn-out:** burned ≥ 0.6, or 4 weeks in A, moves A→R.
- **Library:** R songs older than 1 year move to G.
- **Over size:** the lowest-scored songs drop down a category.

**Churn cap:** at most 25% of any category moves per meeting, and A never drops below 4.

**Logging:** every decision gets `record_decision(db, f"radio:{cid}", f"meeting:{kind}", ...)` plus a `meeting` row (`station_id, held_at, candidate_id, action, from_cat, to_cat, p, reason`).

**Schedule:** runs weekly (Mondays 6 am local), daily during the station's first 7 days, and on demand with `radio --station uk-jazz --meeting`.

- [ ] **Step 1: Failing tests:**
  - `test_adds_go_to_C_catalog_to_G`
  - `test_moves_up_and_burnout`
  - `test_meeting_caps_churn`
  - `test_every_decision_logged_with_reason`
  - `test_first_week_meets_daily_then_weekly`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 5: The scheduler (`station/radio/scheduler.py`)

**Interfaces — Produces:** `schedule_hour(station, db, hour_start_local: datetime) -> list[QueueItem]`, where `QueueItem(starts_at, kind, candidate_id, song_id, duration_ms, category, note, source_url)`. It writes `queue` rows and increments `plays`/`last_played_at`.

**Planning durations for spoken items** (Plan B2 replaces them with the real lengths):

| Item | Planned length |
|---|---|
| `id` | 8 s |
| `id_tease` | 12 s |
| `break` | 25 s |
| `backsell` | 30 s |
| `news` | the latest newscast's length, or 0 when the station's `news` is off |

**For each music slot:**
1. Take the eligible songs in the slot's category: rested at least the category's rest time, and passing the hard rules.
2. Order them by soft-rule fit, then oldest `last_played_at`.
3. If the slot is empty, fall back along A→B→C→R→G.

- [ ] **Step 1: Failing tests:**
  - `test_fills_clock_in_order`
  - `test_rest_times_respected`
  - `test_empty_category_falls_back`
  - `test_separation_relaxes_soft_rules_first`
  - `test_fixed_points_start_on_time`
  - `test_clock_by_local_hour`
  - `test_energy_never_jumps_two`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 6: Queue publishing, schedule page, meeting page

**Files:**
- `station/radio/run.py`: meeting when due → schedule the hours missing in the next 2 → publish `data/radio/<id>/queue.json` (the last hour plus the next 2)
- `templates/radio.html`: the sampler shows "On now / next hour" from the queue
- `templates/meeting.html` at `radio/<id>/meeting/index.html`: this week's adds, moves and drops with Jev's probability and reason, plus the rotation board (categories, songs, plays, last played)

- [ ] **Step 1: Failing tests:**
  - `test_queue_json_shape` (starts_at ISO UTC, kind, song_id, duration_ms, note, source_url)
  - `test_queue_kept_two_hours_ahead`
  - `test_meeting_page_shows_reasons_escaped`
  - `test_sampler_shows_on_now`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 7: 24 hours a day

**Files:**
- `station/__main__.py`: `cmd_build` outside newscast hours runs only the `radio` step, with no newscast and no Sprite checkpoint
- `trigger/wrangler.jsonc`: crons `["48 * * * *"]`
- `docs/decisions/009-24-7-music.md`

- [ ] **Step 1: Failing tests:**
  - `test_overnight_build_runs_radio_only`
  - `test_day_build_unchanged`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.
- [ ] **Step 5: Ask Tarik before deploying** the Worker, since it changes the live trigger. Then `npx wrangler deploy` and confirm `wrangler deployments list`.

### Task 8: Live, docs, review

- [ ] **Step 1:** Run the first meeting by hand (`--meeting`) and confirm the meeting page is live. Then schedule 2 hours and check `queue.json` and the sampler's "on now".
- [ ] **Step 2:** One overnight hour runs unattended, and the queue stays 2 hours ahead.
- [ ] **Step 3:** Docs: check 18, README, decision 009 (Tarik fills "What actually happened").
- [ ] **Step 4:** Final review by a fresh Opus reviewer with this Review Focus. Fix Critical/Important findings test-first, then merge.
