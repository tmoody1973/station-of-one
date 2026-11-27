# Music Station, Plan A: Discovery to Sampler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The UK jazz station's agent reads its feeds every hour, pulls out the tracks and releases they mention, has Jev score each against the station brief, matches them to Apple Music, programs a one-hour block, and publishes a public sampler page: tracklist, the agent's note, the source link, a tap-to-play 30-second preview and a "Listen on Apple Music" link per track.

**Architecture:** A new package `station/radio/` runs as one more step at the end of the hourly build (`radio`, retry or skip). It reuses what the newscast already proved: Apify readers for feeds and subreddits, Ollama for extraction, Jev for scoring, the bucket for pages. The Apple Music API is reached through a `custom_api` connector holding a developer token Tarik signs on his Mac, so no key reaches the Sprite. Plan B (Perplexity cards, voice breaks, news at :00) and Plan C (MusicKit full playback, more stations, station creation) build on this plan's tables and block file.

**Tech Stack:** Python 3.13, SQLite (same `station.db`), Jinja2, Sprites connector gateway (Apify RSS reader and subreddit actor, Ollama, TypeSafe Jev, Apple Music API via `custom_api`), pytest with `FakeGateway`.

**Spec:** `~/Downloads/Station of One Agent-Programmed Music Stations PRD.md` (Tarik, Nov 27), kept out of the public repo like the original PRD. Sections used: "Station model", "Discovery pipeline", "Resolve and playback: Resolve", "Without Apple Music" (sampler), "Hackathon scope" milestones 1–2. Decisions taken Nov 27 (AskUserQuestion): build milestones 1–7 in three plans; UK jazz flagship; Perplexity through `custom_api`; Apple Music API now (Tarik has the MusicKit key).

## Global Constraints

- All external calls through the Sprites connector gateway. The Apple Music developer token and the Perplexity key live only in `custom_api` connectors; never in the Sprite, the code, the config or the repo, and never pasted through Claude.
- No Apple Music audio touches our servers. We store song IDs, preview URLs and links only, never audio.
- Previews play only when tapped, one at a time, never auto-advancing to the next track, and every preview sits beside a "Listen on Apple Music" link (PRD: App Review Guideline 5.2.5).
- Every track on the sampler links to the feed item where the agent found it.
- Jev decides fit; code applies the threshold. A language model never picks what airs.
- A candidate whose best Apple Music match scores below 0.8 is held, not programmed. With no match at all it is kept as "not on Apple Music".
- No artist twice within 3 hours (PRD flow example).
- Scraped text is escaped; links are http(s) only.
- The `radio` step failing never blocks a newscast: retry, then skip; the last sampler page stays up.
- Station settings live in `config/stations/<id>.json` with the PRD fields: `brief`, `feeds`, `seeds`, `era_mix`, `flow`, `talk`, `voice`, `news`, `storefront`, `type`.

## Review Focus

1. **An album review that names no track:** the resolver picks one or two tracks from the album, preferring tracks the item names (Task 6 `test_release_picks_named_track_first`).
2. **The wrong version** (remaster, live take, radio edit, clean edit) must lose to the original unless the item asked for that version (Task 6 `test_original_beats_remaster_and_live`).
3. **A common artist name:** label and year from the item break the tie (Task 6 `test_year_and_album_disambiguate`).
4. **An expired or refused Apple token (401/403):** the run notes it and keeps the last page; it does not crash the build (Task 8 `test_apple_refusal_keeps_last_page`).
5. **A tapped preview ends:** nothing else starts playing (Task 8 `test_previews_never_autoplay_next`).

---

### Task 1: Connectors, spike, station config

**Files:**
- Create: `scripts/apple_music_token.py`
- Create: `spikes/check17_music_station.py`
- Create: `config/stations/uk-jazz.json`
- Create: `docs/decisions/008-music-stations.md`
- Modify: `docs/THURSDAY-CHECKS.md` (check 17)

- [ ] **Step 1:** Write `scripts/apple_music_token.py`.
  - It signs an ES256 developer token (header `kid`; claims `iss` = team id, `iat`, `exp` ≤ 180 days) from Tarik's `.p8` file and copies it to the clipboard with `pbcopy`. It never prints the token.
  - Run with `uv run --with pyjwt --with cryptography scripts/apple_music_token.py --key AuthKey_X.p8 --key-id X --team-id Y`.
- [ ] **Step 2: Tarik adds two `custom_api` connectors** in the Sprites dashboard, each with the "Allow all sprites" policy.
  - **Apple Music:** base `https://api.music.apple.com`, token in header `Authorization`, value `Bearer <pasted token>`.
  - **Perplexity** (used in Plan B): base `https://api.perplexity.ai`, header `Authorization`, value `Bearer <key>`.
- [ ] **Step 3: Spike on the Sprite.**
  - From `/v1/gateway/list`: the connection id for each connector.
  - Apple: `GET /v1/catalog/us/search?term=<artist title>&types=songs,albums&limit=5` for three known UK jazz tracks (Ezra Collective, Nubya Garcia, Yussef Dayes). Record the song attributes used: `name`, `artistName`, `albumName`, `durationInMillis`, `isrc`, `releaseDate`, `previews[0].url`, `url`, `artwork.url`.
  - Also an album's tracks: `GET /v1/catalog/us/albums/<id>/tracks`.
  - Apify RSS reader over the candidate feeds: UK Vibe, Jazz Views, Brownswood, Bandcamp Daily, Guardian jazz, Jazzwise. Note which return items through Apify.
  - Subreddit actor on `r/Jazz`.
  - Expected: three matches with previews, and at least four live feeds.
- [ ] **Step 4:** Write `config/stations/uk-jazz.json`.
  - Feeds: only the ones proven in Step 3.
  - Seeds (artists and labels): Ezra Collective, Nubya Garcia, Shabaka, Yussef Dayes, Moses Boyd, Sons of Kemet, Kokoroko, Alfa Mist; Brownswood, Jazz re:freshed, Impulse!, Gearbox.
  - `era_mix` `{"new": 0.5, "recent": 0.3, "older": 0.2}`
  - `flow` `{"artist_gap_hours": 3, "block_minutes": 50}`
  - `talk` `{"every": 3, "seconds": [20, 30]}`
  - `voice` `{"name": "Sulafat", "style": "warm, unhurried, late-night"}`
  - `news` `true`, `storefront` `"us"`, `type` `"flagship"`
- [ ] **Step 5:** Record check 17, and write decision 008 (Apple Music API through `custom_api`; sampler first; three plans), leaving "What actually happened" blank.
- [ ] **Step 6:** Commit.

### Task 2: Station config and tables (`station/radio/model.py`)

**Interfaces — Produces:**
- `StationConfig` (frozen dataclass of the PRD fields; `feeds: tuple[Feed, ...]` where `Feed(type: Literal["rss", "subreddit"], ref: str)`); `load_station(station_id: str, root: Path = Path("config/stations")) -> StationConfig`
- `open_radio(db) -> None` creates these tables:
  - `feed_items(id, station_id, feed, guid, title, link, published_at, excerpt, seen_at)`
  - `candidates(id, feed_item_id, kind, artist, title, release, label, year, version, status, song_id, match_confidence, apple_url, preview_url, artwork_url, duration_ms, isrc, release_date)`
  - `station_candidates(station_id, candidate_id, fit_score, decided_at, scheduled_at)`
- `candidate_id(artist, title, release) -> str` (sha1 of the normalized text)

- [ ] **Step 1: Failing tests:**
  - `test_load_station_reads_prd_fields`
  - `test_open_radio_is_idempotent`
  - `test_candidate_id_ignores_case_and_punctuation`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 3: Poller (`station/radio/poll.py`)

**Interfaces — Produces:** `FeedItem(id, feed, guid, title, link, published_at, excerpt)`; `poll(gw, station: StationConfig, db, now: datetime) -> tuple[list[FeedItem], list[str]]` (new items only, notes).

- [ ] **Step 1: Failing tests:**
  - `test_poll_dedupes_by_guid_or_link`
  - `test_poll_first_run_looks_back_7_days_then_uses_cursor`
  - `test_one_feed_failing_is_a_note` (fixtures shaped from the Task 1 spike)
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement with `run_actor` and `actor_input` from `station/steps/scrape.py`. Excerpt is the first 600 characters of plain text. The cursor is stored per station, like the newscast's.
- [ ] **Step 4:** Run them. Expected: PASS. Commit.

### Task 4: Extractor (`station/radio/extract.py`)

**Interfaces — Produces:** `Extracted(kind: Literal["track", "release"], artist, title, release, label, year: int | None, version: str)`; `extract(gw, model: str, items: list[FeedItem]) -> tuple[dict[str, list[Extracted]], list[str]]` (by feed item id; at most 8 items per Ollama call; JSON reply).

- [ ] **Step 1: Failing tests:**
  - `test_parses_tracks_and_releases_from_json_reply`
  - `test_drops_entries_without_artist_or_title`
  - `test_keeps_version_strings` ("VIP", "Extended Mix", "Live at …")
  - `test_bad_json_retries_once_then_notes`
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. The prompt says: list only music explicitly named in the item, never guess, return `[]` when none.
- [ ] **Step 4:** Run them. Expected: PASS. Commit.

### Task 5: Fit by Jev (`station/radio/fit.py`)

**Interfaces — Produces:** `fit_scores(gw, station: StationConfig, cands: list[tuple[str, Extracted, FeedItem]]) -> tuple[dict[str, float], dict[str, dict], str | None]`. One batched `/v1/systemone` request per 25 candidates. Question `fit_{i}` (noul): "Does `candidates[{i}]` belong on a station whose brief is `brief`?" Every answer is logged with `record_decision(db, f"radio:{candidate_id}", f"fit:{station_id}", ...)` by the caller.

- [ ] **Step 1: Failing tests:**
  - `test_fit_batches_by_25`
  - `test_fit_state_carries_brief_seeds_and_excerpt`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 6: Resolver (`station/radio/resolve.py`)

**Interfaces — Produces:**
- `Match(song_id, artist, title, album, duration_ms, isrc, release_date, preview_url, apple_url, artwork_url, confidence: float)`
- `match_score(want: Extracted, song: dict) -> float`: artist 0.4, title 0.4, year/album 0.2. Penalty −0.3 for an unrequested version word: remaster, live, edit, clean, instrumental, karaoke.
- `resolve(gw, want: Extracted, storefront: str) -> tuple[list[Match], str]`: a release gives 1–2 tracks; status is `"resolved" | "held" | "not_on_apple"`.
- `MATCH_MIN = 0.8`

- [ ] **Step 1: Failing tests:**
  - `test_original_beats_remaster_and_live`
  - `test_year_and_album_disambiguate`
  - `test_below_threshold_is_held`
  - `test_no_results_is_not_on_apple`
  - `test_release_picks_named_track_first`
  - `test_apple_401_raises_a_clear_error`
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Normalize text: lowercase, strip accents, drop "feat." and punctuation, then `difflib` ratio. Search URL as proven in Task 1.
- [ ] **Step 4:** Run them. Expected: PASS. Commit.

### Task 7: Programmer (`station/radio/program.py`)

**Interfaces — Produces:** `Block(station_id, block_id, built_at, tracks: list[dict])`; `program_block(station: StationConfig, db, now: datetime) -> Block`.
- **Draws from:** resolved candidates with fit ≥ 0.5 that haven't been scheduled.
- **Ordered by fit**, with era buckets filled toward `era_mix`: new ≤ 1 year, recent ≤ 10 years, older.
- **No artist twice** within `artist_gap_hours`.
- **Fills to** `block_minutes` by duration, then marks `scheduled_at`.
- **Each track carries** its note: "Found in <feed title>: <item title>" with the item link.

- [ ] **Step 1: Failing tests:**
  - `test_block_fills_to_minutes_by_duration`
  - `test_no_artist_within_gap`
  - `test_era_mix_is_approximated`
  - `test_low_fit_and_held_are_excluded`
  - `test_scheduled_tracks_not_reused`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run them. Expected: PASS. Commit.

### Task 8: Sampler page, `radio` step, publish

**Files:**
- `templates/radio.html` (Bauhaus)
- `station/radio/page.py` (`render_sampler(station, block) -> str`)
- `station/__main__.py` (`cmd_radio`, `radio --station`, the `radio` step after `finish`)
- `station/manager.py` (`FALLBACKS["radio"] = ["retry", "skip"]`, plus its `SKIP_MEANS` line)
- `station/radio/run.py` (`run_station(gw, station_id, db, now) -> dict`: poll → extract → fit (log) → resolve → program → page → upload `radio/<station>/index.html` and `data/radio/<station>.json`)

**The sampler page shows:**
- the station name, brief and "machine-programmed" line
- a disabled "Connect Apple Music for full songs" button, noting that full playback is coming (Plan C)
- one row per track: artwork (Apple's, hotlinked), title, artist, album and year; the note with its source link; a Preview button (one shared `<audio>`; tap to play; `ended` does nothing); and a "Listen on Apple Music" link
- an "agent log" box: items read, tracks found, matched, held, scheduled

- [ ] **Step 1: Failing tests:**
  - `test_previews_never_autoplay_next`: no `autoplay` attribute, and the script has no `ended`-to-next handler
  - `test_every_track_has_source_and_apple_link`
  - `test_text_is_escaped`
  - `test_apple_refusal_keeps_last_page`
  - `test_build_runs_radio_after_finish`
- [ ] **Step 2:** Run them. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run the whole suite. Expected: PASS.
- [ ] **Step 5:** Preview screenshot at 1440 and 390 px, then tap a preview in Chrome: it plays, it ends, and nothing else starts. Commit.

### Task 9: Live run, docs, review

- [ ] **Step 1:** `radio --station uk-jazz` by hand on the Sprite. Expected: the sampler is live with at least 10 tracks, every preview plays on tap, and every source link opens.
- [ ] **Step 2:** The next hourly build runs `radio` unattended.
- [ ] **Step 3:** Docs: check 17 live numbers (items, extracted, matched, held, cost, seconds), README section "Music stations", and a link from the front page nav ("Radio").
- [ ] **Step 4:** Final review by a fresh Opus reviewer with this plan's Review Focus. Fix Critical/Important findings test-first, then merge. Then write Plan B.
