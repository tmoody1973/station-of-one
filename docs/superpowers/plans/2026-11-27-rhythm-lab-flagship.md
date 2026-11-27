# Rhythm Lab Flagship Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The flagship station is **Rhythm Lab**: Tarik's 13-year Rhythm Lab Radio library (563 shows, 10,701 tracks; 2,513 already matched on Apple Music) programmed by the agent in the show's own style. The station keeps:
- **its rotation:** library tiers become categories
- **its hour shape:** hour 2 builds energy, with real openers and closers
- **its pairings:** tracks Tarik played back to back
- **its seasons:** holiday tags

New finds from music feeds are judged against that sound.

**Architecture:** This plan supplies the station's catalog and its programming knowledge. Plan B1 (approved) supplies the machinery: categories, clocks, the scheduler, the music meeting and the queue. Execution order: B1 Tasks 1–3 → this plan's Tasks 1–5 → B1 Tasks 4–8, where the B1 scheduler gains this plan's soft rules (energy from the library, opener/closer slots, pairings, holiday slot). The library lives only in the Sprite's private database (`data/station.db`, table `library_tracks`, imported Nov 27 by `scripts/library_match.py`). It never goes in the public repo or onto a public page. That includes the Drive links in the shows file and the raw show notes.

**Tech Stack:** Python 3.13, SQLite, TypeSafe Jev, Apple Music API (custom_api connector), the Plan B1 tables.

**Spec:** Tarik, Nov 27 (AskUserQuestion): Rhythm Lab is the flagship, under its own name ("it's mine"); copy the library to the Sprite and match the 2,944 tracks with 2+ plays, guest mixes excluded. The library README (`data/library/rhythm_lab/README.md` on the Sprite) gives the field meanings:
- tiers: `core` 6+ shows, `rotation` 3–5, `repeat` 2, `single_spin` 1
- `hour1_plays` / `hour2_plays` ("hour 2 leans uptempo and electronic")
- `hour_opener_count`, `show_closer_count`
- `special_tags`
- `segments` (guest mixes; not Tarik's picks)
- the plays file's `block` ("tracks sharing a block ran back to back")
- the artist notes: "the agent should rewrite, not read verbatim"

## Global Constraints

- No Drive URL, raw show note or full library dump is ever published or committed. Public pages show only what a station page would: the track, artist, the note "First aired on Rhythm Lab Radio, <date>" and the Apple Music link.
- Guest-mix tracks (`segments` set) are never programmed.
- Only matched tracks (`match_status = 'resolved'`) are programmed; held and not-on-Apple tracks are listed in a private report for Tarik.
- **Categories for Rhythm Lab** (B1 `rotation` block, editable):

  | Category | Holds | Rest |
  |---|---|---|
  | P | Power Gold: `core` | 20 h |
  | M | `rotation` | 3 days |
  | R | `repeat`, last played 2023 or later | 5 days |
  | G | the rest of `repeat` plus matched `single_spin` | 10 days |
  | N | New: feed finds Jev adds | 6 h |

- **Library energy comes from Tarik's own placement** (no Jev call): `hour2_plays / (hour1_plays + hour2_plays)`.

  | Share in hour 2 | Energy |
  |---|---|
  | 0.65 or more | 3 |
  | 0.35 or less | 1 |
  | otherwise | 2 |

- **Clock shape** (day and overnight, from B1):
  - The first half of each hour draws energy 1–2.
  - The second half draws 2–3.
  - The slot after `:00` prefers a track with `hour_opener_count > 0`.
  - The slot before `backsell` prefers a track with `show_closer_count > 0`.
- **Pairings are a soft preference only:** a scheduler bonus for a track Tarik played right after the previous one (same block, next position). They never override hard separation rules.
- **Holiday season** (Nov 26 – Dec 31): one music slot per hour prefers a `holiday`-tagged track.

## Review Focus

1. **A pairing that would break artist separation** never wins (Task 3 `test_pairing_never_beats_hard_rules`).
2. **No published page or JSON contains a Drive URL or a raw note line** (Task 5 `test_no_private_fields_published`).
3. **A core track that is held** (not matched) never appears in a schedule (Task 2 `test_unmatched_never_scheduled`).
4. **Holiday tracks after Dec 31** get no special slot (Task 4 `test_holiday_window`).
5. **Energy for a track with no hour data** is 2, not a crash (Task 2 `test_energy_without_hour_data`).

---

### Task 1: Station config and a private held report

**Files:**
- Create `config/stations/rhythm-lab.json`:
  - `type` `"flagship"`
  - brief (draft, which Tarik edits): "Rhythm Lab: beats, soul, jazz and electronic music from the Rhythm Lab Radio library, new and old, sequenced like the show"
  - feeds: Bandcamp Daily, Stones Throw, Brownswood, plus two more verified with check 20
  - seeds: the top 40 library artists by plays
  - voice, `news: true`, storefront `us`, the same `apple_connection`
- Change `config/stations/uk-jazz.json` to `type: "genre"`.
- Create `scripts/library_report.py`, which writes `data/library/held.csv` (private, for Tarik).

- [ ] **Step 1: Failing tests:**
  - `test_rhythm_lab_station_loads_as_flagship`
  - `test_only_one_flagship`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement and check the feeds (check 20). **Step 4:** Run them. Expected: PASS. Commit.

### Task 2: Library into rotation (`station/radio/library.py`)

**Interfaces — Produces:** `library_energy(h1: int, h2: int) -> int`; `seed_rotation(db, station) -> dict[str, int]`. It writes B1 `rotation` rows from matched library tracks: category by tier and recency, energy from hour placement, an `opener`/`closer` flag, and `source_note = "First aired on Rhythm Lab Radio, <first_played>"`.

- [ ] **Step 1: Failing tests:**
  - `test_tiers_map_to_categories`
  - `test_energy_from_hour_placement`
  - `test_energy_without_hour_data`
  - `test_unmatched_never_scheduled`
  - `test_guest_mix_tracks_excluded`
  - `test_seed_rotation_idempotent`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 3: Pairings (`station/radio/pairs.py`)

**Interfaces — Produces:**
- `import_pairs(db, plays_csv: Path) -> int`: a `library_pairs(a, b, count)` row for consecutive tracks in the same show, hour and block
- `pair_bonus(db, prev_track_id, track_id) -> float`: 0.1 per time played together, capped at 0.3

- [ ] **Step 1: Failing tests:**
  - `test_pairs_only_within_a_block`
  - `test_pair_bonus_capped`
  - `test_pairing_never_beats_hard_rules` (with the B1 scheduler)
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 4: Hour shape and seasons in the scheduler (B1 Task 5 soft rules)

**Files:** `station/radio/scheduler.py` (from B1).
- Half-hour energy bands.
- Opener and closer preference.
- The pairing bonus.
- The holiday slot inside its window.

All soft, ordered after the hard rules.

- [ ] **Step 1: Failing tests:**
  - `test_first_half_lower_energy`
  - `test_opener_after_news`
  - `test_holiday_window`
  - `test_soft_rules_relax_in_order`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 5: Notes for the voice (private) and the public line

**Files:**
- `station/radio/notes.py`: `import_notes(db, notes_json) -> int` into private `artist_notes(artist, date, source, note)`, for Plan B2's break writer, which rewrites and cites and never reads them verbatim
- `templates/radio.html`: the track line "First aired on Rhythm Lab Radio, Nov 2014", with no notes text

- [ ] **Step 1: Failing tests:**
  - `test_notes_imported_privately`
  - `test_no_private_fields_published`: render the sampler and `queue.json`, and assert there is no `docs.google.com`, `drive_url` or note text
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 6: The rest of the library (background)

- [ ] Run `scripts/library_match.py data/library/rhythm_lab 1` on the Sprite overnight: the 7,757 single-spin tracks, about 25–30 minutes, free. Record the counts in check 20.

### Task 7: Live, docs, review

- [ ] **Step 1:** The first Rhythm Lab hour is scheduled and its sampler page is live. In the station strip, Rhythm Lab is first (the flagship).
- [ ] **Step 2:** Docs:
  - decision 012 (Rhythm Lab is the flagship; the library stays private; tiers become categories; energy from hour placement), with "What actually happened" blank for Tarik
  - README
  - check 20
- [ ] **Step 3:** Final review by a fresh Opus reviewer with this Review Focus. Fix Critical/Important findings test-first, then merge.
