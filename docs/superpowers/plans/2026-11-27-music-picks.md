# Music Picks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Once a day the station picks three new releases (Bandcamp albums from chosen labels and new videos from chosen YouTube channels), Jev ranks them, and the front page shows them as official Bandcamp and YouTube players that load only when tapped.

**Architecture:** A daily `picks` step runs after the 7 am newscast, like Corrections and The Table. It gathers candidates through Apify (YouTube channel RSS through the existing RSS reader; Bandcamp label pages and album pages through the approved Cheerio Scraper), asks Jev one batched question, and writes `data/picks/<day>.json`. The page step reads the newest picks file and renders a "music picks" section. Players are built in code from a validated numeric Bandcamp album id or an 11-character YouTube id, never from a scraped URL, and the iframe is only inserted when the reader taps Play.

**Tech Stack:** Python 3.13, Jinja2, Sprites connector gateway (Apify `santamaria-automations~rss-feed-reader` and `apify~cheerio-scraper`, TypeSafe Jev), pytest with `FakeGateway`.

**Spec:** `docs/SPEC.md` §3 beats table ("Music: Bandcamp tags and labels, YouTube channels, music picks only") and §7 ("music picks section with Bandcamp and YouTube embeds that load on tap"); CLAUDE.md "No licensed music in audio, feed or video. Music appears only as official embeds on the page." Approved by Tarik Nov 27 ("do 1 and 2"). Note: the old `music` beat became a newscast beat the same day, so picks get their own preferences block instead of a beat.

## Global Constraints

- Music appears only as official Bandcamp or YouTube embeds on the page. Never in audio, the feed, the video, or the Box archive.
- Nothing loads from Bandcamp or YouTube until the reader taps Play (no iframe, no thumbnail fetched from their servers before the tap).
- Embed URLs are built from validated ids only: Bandcamp album id `^\d{1,12}$`; YouTube video id `^[A-Za-z0-9_-]{11}$`. Embed hosts are `https://bandcamp.com/EmbeddedPlayer/` and `https://www.youtube-nocookie.com/embed/`.
- Jev ranks the candidates; code takes the top 3 with at most one per source. A language model never picks.
- Every Jev answer is logged with its probability (`record_decision`).
- All calls through the connector gateway. Scraped titles are escaped; links http(s) only.
- A failed picks step never blocks a newscast: manager fallback retry, skip. With no picks file, the section is not shown.
- Runnable by hand: `uv run python -m station picks --day 2026-11-27`.

## Review Focus

1. **A scraped title or artist with HTML or quotes** must render as text, and can never change the embed URL (Task 5 `test_picks_escape_text_and_build_embed_from_id`).
2. **A Bandcamp page with no album id** (a track page, a merch page, a page with a changed layout) is dropped, not shown as a broken player (Task 2 `test_album_id_missing_is_dropped`).
3. **A YouTube link that is a Short, a playlist or a live stream URL** gives the right 11-character id or is dropped (Task 2 `test_youtube_id_forms`).
4. **One source failing (label page 404, channel feed gone)** costs only that source's candidates (Task 4 `test_picks_survive_one_source_failing`).
5. **The same release in two places, or yesterday's pick again** is not picked twice in a week (Task 3 `test_no_repeat_within_a_week`).

---

### Task 1: Spike and source list

**Files:** Create `spikes/check16_music_picks.py`; modify `docs/THURSDAY-CHECKS.md` (check 16), `config/preferences.json` (new `music_picks` block: `bandcamp_labels`, `youtube_channels`, `count: 3`).

- [ ] **Step 1:** Get the list of sources from Tarik: Bandcamp label subdomains and YouTube channel ids.
- [ ] **Step 2:** Spike on the Sprite, recording the item shapes, cost and seconds.
  - RSS reader on `https://www.youtube.com/feeds/videos.xml?channel_id=<id>` for 2 channels.
  - Cheerio Scraper on `https://<label>.bandcamp.com/music`: album links.
  - Cheerio Scraper on 3 album pages: the `og:video` or `bc-page-properties` meta, to read the album id.
- [ ] **Step 3:** Build one Bandcamp and one YouTube embed URL from the spike ids and open them in a browser. Expected: both play.
- [ ] **Step 4:** Record check 16 and commit.

### Task 2: Candidate sources (`station/picks/sources.py`)

**Interfaces — Produces:** `Pick(source: str, kind: Literal["bandcamp", "youtube"], embed_id: str, title: str, artist: str, url: str, published_at: str)` (frozen dataclass); `youtube_id(url: str) -> str | None`; `album_id(meta: dict) -> str | None`; `youtube_candidates(gw, channels: list[str]) -> tuple[list[Pick], list[str]]` (notes); `bandcamp_candidates(gw, labels: list[str]) -> tuple[list[Pick], list[str]]`.

- [ ] **Step 1: Failing tests:**
  - `test_youtube_id_forms`: `watch?v=`, `youtu.be/`, `/shorts/` and `/embed/` all give the 11-character id; `/playlist?list=` and a 10-character id give None.
  - `test_album_id_missing_is_dropped`
  - `test_youtube_candidates_from_rss_items` (fixture shaped from the spike)
  - `test_bandcamp_candidates_from_cheerio_items`
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Keep only candidates published in the last 14 days. Each source failing is a note, not an exception.
- [ ] **Step 4:** Run them. Expected: PASS. Commit.

### Task 3: Jev ranks, code chooses (`station/picks/choose.py`)

**Interfaces — Produces:** `rank(gw, picks: list[Pick]) -> tuple[list[tuple[Pick, float]], str | None]` (one batched `/v1/systemone` request, question `interest_{i}` noul: "Is this new release likely to interest a public-radio listener who follows independent music?"); `choose(ranked, count: int, recent_ids: set[str]) -> list[tuple[Pick, float]]` (top by score; at most one per source; skip ids picked in the last 7 days).

- [ ] **Step 1: Failing tests:**
  - `test_choose_one_per_source_top_scores`
  - `test_no_repeat_within_a_week`
  - `test_rank_sends_one_batched_request_and_logs`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 4: The `picks` step

**Files:**
- `station/__main__.py`: `cmd_picks(day)`; first-hour wiring next to `"table"`
- `station/manager.py`: `FALLBACKS["picks"] = ["retry", "skip"]`, plus its `SKIP_MEANS` line
- `station/config.py`: a `MusicPicks` dataclass
- `station/picks/step.py`: `make_picks(gw, prefs, db, day) -> dict`

**Outputs:**
- `data/picks/<day>.json` with `{"day", "picks": [{...Pick, "score"}], "model", "notes"}`
- every Jev answer recorded with `record_decision(db, f"pick:{kind}:{embed_id}", "interest", ...)`

- [ ] **Step 1: Failing tests:**
  - `test_picks_survive_one_source_failing`
  - `test_picks_file_written_and_decisions_logged`
  - `test_first_hour_runs_picks_after_table`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run the whole suite. Expected: PASS. Commit.

### Task 5: Front page section and settings

**Files:**
- `station/steps/page.py`: `latest_picks(picks_root) -> dict | None`, `embed_url(pick) -> str`
- `templates/front.html`: a "5 music picks" section in the main column. Cards show artist, title, source and a "Play here" button; a small script inserts the iframe on tap, with `loading="lazy"` and `allow="encrypted-media"`.
- `templates/settings.html`: a Music picks row listing the sources

- [ ] **Step 1: Failing tests:**
  - `test_picks_escape_text_and_build_embed_from_id`
  - `test_no_iframe_before_tap`: no `<iframe` in the HTML, only `data-embed`
  - `test_no_section_without_picks`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS.
- [ ] **Step 5:** Preview screenshot at 1440 and 390 px. Commit.

### Task 6: Live run, docs, final review

- [ ] **Step 1:** Run `picks --day <today>` by hand on the Sprite, then `page` and `publish` on the newest run. Expected: the section is live, and both players play after a tap.
- [ ] **Step 2:** Update the docs:
  - decision 007: picks are a daily step, Jev-ranked, played on tap, with their own sources block
  - README
  - SPEC beats table row
  - check 16 live numbers
- [ ] **Step 3:** Final review by a fresh Opus reviewer with this plan's Review Focus. Fix Critical/Important findings test-first. Merge.
