# ONE Jazz, Around the Clock: a General Jazz Station Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ONE Jazz stops being an hourly sampler and becomes a 24/7 general jazz station run by the program director: jazz styles in daypart clocks, rotation categories with rest times, a weekly music meeting, and a weekly scout for new releases and for the thin styles.

**Architecture:** Reuses Plan B1's program director (rotation, scheduler, meeting, queue, pages) and Plan C's playback. New: a second dimension. Rhythm Lab's clock slots name rotation categories; jazz clock slots name **styles** (from Tarik's `jazz_clocks.json`), and the song's rotation category still sets how long it rests. Catalog: the 1,019 core tracks in Tarik's jazz cut of the Rhythm Lab library, matched on Apple Music, plus scouted new releases and catalog deepening, every addition judged by Jev and logged.

**Tech Stack:** Python, SQLite, TypeSafe Jev, the Apple Music API (Custom API connector; endpoints verified in Task 4 before use), Apify for feeds.

**Spec:** Tarik, Nov 27, 6:04 pm: "create general jazz stream instead of sampler like rhythm lab using program director best practices, `~/Downloads/rhythm_lab_jazz_programming`, a plan on how to search for new releases that fits this, then create categories for different jazz, rotations". Source folder (read Nov 27): `README.md` (tiers, styles, clocks, rules, thin spots), `jazz_clocks.json` (rules + five daypart clocks), `jazz_library.csv` (1,954 tracks: 1,019 core, 935 adjacent), `jazz_artists.csv` (729 artists, "the control file"), `jazz_sample_day.csv` (264-track example day).

## What the data says (Nov 27, Sprite database)

| Style | Core playable on Apple Music | Core not yet matched |
|---|---|---|
| contemporary | 88 | 224 |
| uk_jazz | 61 | 124 |
| spiritual_avant | 44 | 118 |
| jazz_funk_fusion | 35 | 109 |
| heritage | 31 | 63 |
| vocal | 22 | 35 |
| latin_brazilian_afro | 16 | 35 |

297 of 1,019 core tracks are playable; 705 core tracks are Rhythm Lab single spins, never matched. A 24/7 stream at 11 tracks an hour is 264 tracks a day; with the README's 72-hour minimum between repeats it needs roughly 800 playable tracks, spread across the styles the clocks call for.

## Global Constraints

- **Format:** core tier only (README: "A strict jazz format plays only these"); `beats_nu_jazz` and all adjacent tracks stay out. Guest-mix tracks stay out. `holiday_only` tracks join the pool Thanksgiving week through Dec 25 (README rule), never otherwise.
- **Clocks (verbatim from `jazz_clocks.json`):** five dayparts by local hour: rise 6-9, workday 10-14, drive 15-18, after_hours 19-23, overnight 0-5; each 11 style slots in the given order; breaks after positions 4 and 8; station ID and news at the top of the hour. :00 is the only fixed point (no :30 tease in these clocks).
- **Rules (from `jazz_clocks.json`):** artist separation 4 hours; no track repeats within 72 hours (every category rests at least 72 h); weighting by how often Tarik played a track comes through its category (Rhythm Lab tier).
- **Rotation categories (rest times; sizes hold the catalog):**

  | Category | Holds | Rest |
  |---|---|---|
  | P | Rhythm Lab core and rotation tiers | 72 h |
  | M | repeat tier | 5 days |
  | G | single spins and catalog deepening | 10 days |
  | N | new releases Jev adds | 72 h |

- **Styles** are the 7 core styles above; every rotation row carries one. A new song gets its style from Jev (a choice among the 7, plus "not jazz", which is never added).
- Jev decides adds and styles (logged with `record_decision`); code applies thresholds (add at 0.6, the Plan B1 churn cap); a language model never picks the next song.
- Tarik's library stays private (Rhythm Lab plan rules): no Drive links, no notes, no raw library on any page.

## Review Focus

1. **A thin style runs out** (only 16 Latin tracks rested): the slot falls back along that style's fallback list, then any rested jazz, never an empty slot while anything fits (Task 3 `test_style_slot_falls_back`).
2. **The same track inside 72 hours, the same artist inside 4 hours:** never (Task 3 `test_jazz_rules_hold_over_a_day`).
3. **A new release Jev calls "not jazz"**, or rates under 0.6: never added (Task 4 `test_not_jazz_never_added`).
4. **The holiday pool after Dec 25:** holiday-only tracks never scheduled (Task 1 `test_holiday_only_outside_window`).
5. **An Apple Music lookup refused or rate-limited mid-scout:** what was found is kept, the rest retried next week, the station keeps playing (Task 4 `test_scout_survives_apple_errors`).

---

### Task 1: Match the jazz deep cuts and load the jazz rotation

**Files:** `station/radio/jazz.py` (`seed_jazz_rotation(db, station, jazz_csv) -> dict[str, dict[str, int]]`: core tier, holiday flag, guest mixes out, category from Rhythm Lab tier, `style` from the file); `station/radio/model.py` (rotation gains `style TEXT`); `scripts/jazz_golive.py` (match the unmatched core jazz tracks with `match_library`, then seed; rehearse with `--db`); tests `tests/radio/test_jazz.py`.

- [ ] Failing tests: `test_core_only_and_styles_kept`, `test_tiers_map_to_jazz_categories`, `test_holiday_only_outside_window`, `test_unmatched_never_loaded`.
- [ ] Implement; rehearse on a database copy; record per-style playable counts in check 22.

### Task 2: The station config

**Files:** `config/stations/jazz.json` (id `jazz`, name "ONE Jazz", type `genre`, `programmer: "clock"`, general jazz brief, the four categories, the five clocks and rules above, a `styles` block with each style's fallback list, `meeting` ladder: new→N, catalog→G, up N→P); `config/stations/uk-jazz.json` retired (its page points to `/radio/jazz/`); tests in `tests/radio/test_model.py`.

- [ ] Failing tests: `test_jazz_clocks_match_tarik_file` (each daypart's slots equal `jazz_clocks.json`), `test_jazz_dayparts_cover_every_hour`.
- [ ] Implement; commit.

### Task 3: Style slots in the scheduler

**Files:** `station/radio/scheduler.py` (a slot that names a style draws from songs of that style across categories, each rested per its own category; fallback along the style's list, then any style); tests in `tests/radio/test_scheduler.py`.

- [ ] Failing tests: `test_style_slot_draws_that_style`, `test_style_slot_falls_back`, `test_jazz_rules_hold_over_a_day` (schedule 24 hours from a fixture library: no track within 72 h, no artist within 4 h, every hour's breaks after songs 4 and 8).
- [ ] Implement; commit.

### Task 4: The new-release scout (weekly)

How it finds new music that fits, in order of trust:
1. **Artists the station already plays:** for every artist on the station (the 729 in `jazz_artists.csv`, core tier), Apple Music's catalog lists their albums; anything released in the last 60 days is a candidate.
2. **Jazz-focused feeds:** label and press feeds checked live first (check 22: newest post dates), read through Apify like the other stations.
3. **Apple's jazz new releases** if the catalog offers a genre-filtered listing (verified in check 22 against the Apple Music API docs before any code relies on it).

Each candidate gets two Jev questions in one batch: fit to the brief (noul) and style (choice: the 7 styles or `not_jazz`). The weekly music meeting then decides adds to N, with the style attached.

**Files:** `station/radio/scout.py` (`scout_new_releases(gw, station, db, since) -> ScoutResult`), Jev questions, run inside the meeting; tests `tests/radio/test_scout.py`.

- [ ] Failing tests: `test_recent_albums_from_station_artists_become_candidates`, `test_style_choice_logged_and_attached`, `test_not_jazz_never_added`, `test_scout_survives_apple_errors`.
- [ ] Implement; commit.

### Task 5: Deepen the thin styles

Targets (playable core, at least): heritage 150, vocal 120, latin_brazilian_afro 120. For a style under target, take its artists from `jazz_artists.csv`, look up their best-known recordings in the Apple Music catalog, and put them through the same Jev fit and style questions; the meeting adds passing ones to G (catalog). Never more than the meeting's churn cap per week; reported per style on the program director's page.

**Files:** `station/radio/scout.py` (`deepen_styles(gw, station, db, targets) -> dict[str, int]`); tests.

- [ ] Failing tests: `test_only_styles_under_target_are_deepened`, `test_deepened_tracks_go_to_catalog_with_style`.
- [ ] Implement; commit.

### Task 6: Pages and the switch

- The ONE Jazz station page becomes a tracklist with Listen live (Plan C); its strip box plays it.
- The explainer and the program director's page show styles and the five dayparts (clock drawings from the jazz clocks).
- The strip, playlists page and README move from `uk-jazz` to `jazz`.

- [ ] Failing tests for the pages; implement; commit.

### Task 7: Live, docs, review

- [ ] Run `scripts/jazz_golive.py` on the real database (with Tarik's go), first meeting by hand, first hours scheduled; check 22; decision 013 (the jazz format and its sources); README.
- [ ] Fresh Opus review with this Review Focus; fix Critical/Important test-first; merge.
