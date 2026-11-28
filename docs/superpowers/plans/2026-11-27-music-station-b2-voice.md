# Music Station B2: Voice Breaks and News in the Stream — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rhythm Lab and ONE Jazz sound like radio: a station ID at the top, the newscast at :00 in newscast hours, and a 20–30 second voice break every few songs that back-announces what played with one cited fact, all in the listener's stream between full songs.

**Architecture:** Plan B1 already reserves the spoken slots in each hour's queue (`id`, `id_tease`, `break`, `backsell`, `news`); Plan C plays only the songs. B2 fills the slots on the Sprite, ahead of air (facts → script → Jev check → Gemini voice → MP3 in the bucket, linked from the queue item), and the browser plays the queue in order: songs through MusicKit in blocks, our audio between blocks, never both at once. Facts come from Perplexity Sonar (Tarik, Nov 27: "Add Perplexity"), with the station's own facts (Apple Music, where the record was found, Rhythm Lab's first-aired date) as the fallback.

**Tech Stack:** Python, SQLite, Perplexity Sonar through a new Sprites connector, TypeSafe Jev, Ollama Cloud (the newscast's writer), Gemini `gemini-3.8-flash-tts` (memory: v1beta, `speech_metadata`, WAV out), ffmpeg, `templates/shell.js` + `templates/live.js`, Playwright e2e with the stand-in MusicKit.

**Spec:** `~/Downloads/Station of One Agent-Programmed Music Stations PRD.md`, sections "The hour", "Enrichment: Perplexity API", "Voice breaks and news" (read Nov 27). Tarik's decisions, Nov 27 9 pm: facts from Perplexity; a host voice per station; no overnight recap.

## Global Constraints

- **Cite or cut** (PRD): a fact with no source URL is dropped before the break is written. Links come only from Sonar's `citations` / `search_results`, never from model-written text (Perplexity docs, Context7 `/llmstxt/perplexity_ai_llms_txt`: "Avoid asking for links inside the JSON").
- **Break script rules** (PRD, verbatim): "Back-announce what just played, give one cited fact, say where the agent found it, tease what is next." "One idea per break. No lists of facts." "Never claim to have been somewhere or met someone." Each station has its own voice and style prompt.
- **Jev decides; code applies thresholds** (CLAUDE.md): Jev answers whether a script states anything not in its facts; code drops a script at 0.3 or more, logged with `record_decision`. A language model never picks a song.
- **Our audio never plays over a song** (Apple terms; `docs/LATER.md`): spoken items play only between MusicKit blocks; MusicKit is paused or finished first.
- **Budget** (PRD): track cards only for songs a break back-announces; artist cards cached 30 days, track cards forever; low search context. TTS only for spoken items in the next 2 hours.
- **No API key** in the Sprite, code, config or repo: Perplexity goes through a Sprites connector Tarik adds (CLAUDE.md).
- Voices are synthetic and the stations machine-programmed, stated on the pages (already) and in the explainer's breaks section.
- No real person's voice is imitated; voices are Gemini prebuilt voices.
- Overnight (7 pm–7 am): no news slot (already `news_for_hour`); no recap.

## Review Focus

1. **Perplexity down, refusing or rate-limited:** the break uses the station's own facts; the hour still has breaks; the build keeps its time (Task 2 `test_cards_fall_back_to_own_facts`).
2. **A script that says more than its facts:** Jev's check drops it and the break falls back to a plain back-announce with no fact (Task 3 `test_script_beyond_facts_is_cut`).
3. **A spoken item with no audio** (TTS failed, not yet voiced): the browser skips it; songs keep playing (Task 5 e2e `test_unvoiced_item_is_skipped`).
4. **A listener tuning in mid-break, or with the player ahead of the clock:** playback starts at the right item; never two sounds at once (Task 5 e2e `test_join_mid_break` and `test_one_sound_at_a_time`).
5. **News slot with no fresh newscast** (late, failed, or older than 70 minutes): skipped, never an old newscast (Task 5 `test_stale_news_is_skipped` in `tests/js/`).

---

### Task 1: Check 23 — Perplexity through the connector (Tarik adds it first)

**Tarik's step:** add a Perplexity connector in the Sprites dashboard (Custom API, base `https://api.perplexity.ai`, his API key). Name it; the name goes in `config/preferences.json` as `perplexity.connection`.

- [ ] **Step 1:** Spike `spikes/perplexity_check.py` on the Sprite: one `POST /v1/sonar` (model `sonar`) for one Rhythm Lab track with `response_format` json_schema `{facts: [{text, citation}]}` where `citation` is the `[n]` marker number. Record in `docs/THURSDAY-CHECKS.md` as check 23: status, latency, the response's `citations`/`search_results` shape, whether markers map to `citations`, cost from `usage`. If `/v1/sonar` is refused, try `/chat/completions` and record which works.
- [ ] **Step 2:** Pin the working path, model and schema in the check. Commit.

### Task 2: Fact cards

**Files:** Create `station/radio/cards.py`; modify `station/radio/model.py` (table `cards(kind TEXT, key TEXT, facts TEXT, fetched_at TEXT, PRIMARY KEY(kind, key))`); test `tests/radio/test_cards.py`.

**Interfaces — Produces:** `facts_for(gw, db, station, candidate_id, now) -> list[dict]` — each `{"text", "source_url", "source_name"}`, at most 5, every one with an http(s) URL. Order: the track card (Sonar, cached forever), the artist card (Sonar, cached 30 days, first time an artist is scheduled), then own facts: Apple Music (album, release year; source the Apple Music URL), where the record was found (the feed item's title and link), Rhythm Lab's "first aired" (the library's public note; source the station page).

- [ ] **Step 1: Failing tests:** `test_track_card_keeps_only_cited_facts` (a fact whose marker is out of range or has no URL is dropped); `test_cards_are_cached` (second call makes no request; artist card refetched after 30 days); `test_cards_fall_back_to_own_facts` (Sonar 500, 429 or refused → own facts only, a note, no exception — Focus 1); `test_disambiguation_in_query` (the request names album and year).
- [ ] **Step 2:** Run: FAIL. **Step 3:** Implement with the path and schema pinned in check 23. **Step 4:** Run: PASS. Commit.

### Task 3: Break scripts, IDs, teases

**Files:** Create `station/radio/breaks.py`; modify `config/stations/rhythm-lab.json` and `jazz.json` (`host: {"voice": <Gemini prebuilt voice>, "style": <one short string>}`); test `tests/radio/test_breaks.py`.

**Interfaces — Produces:** `script_for(gw, db, station, item, prev_songs, next_song, now, prefs) -> dict` — `{"text", "sources": [{url, name}], "kind"}` for queue item kinds `break`, `backsell` (back-announce + fact + where found + tease next, Ollama with the PRD rules and 55–75 words), `id` and `id_tease` (templates from `prefs.station` ID lines and the station name, no model), `news` (no script; the browser plays the newscast).

- [ ] **Step 1: Failing tests:** `test_break_names_what_played_and_one_fact`; `test_script_beyond_facts_is_cut` (Jev's "states anything not in the facts?" at 0.4 → the plain back-announce, decision logged — Focus 2); `test_no_facts_means_plain_back_announce`; `test_id_lines_from_preferences`; `test_script_never_reads_urls` (no `http` in text).
- [ ] **Step 2:** Run: FAIL. **Step 3:** Implement. Voices: Rhythm Lab and ONE Jazz get different prebuilt voices from the newscast's two (recorded as a ruling; Tarik can swap). **Step 4:** Run: PASS. Commit.

### Task 4: Voice the queue's spoken items

**Files:** Create `station/radio/voicing.py`; modify `station/radio/onair.py` (`run_clock` voices spoken items in the next 2 hours lacking audio), `station/radio/model.py` (queue gains `text`, `sources`, `audio_url`); tests `tests/radio/test_voicing.py`.

**Interfaces — Consumes:** `script_for` (Task 3), the newscast's `synthesize_request` (`station/steps/voice.py`). **Produces:** queue items in `queue.json` carry `audio_url` (`/audio/radio/<station>/<item hash>.mp3`, immutable cache), `text`, `sources`.

- [ ] **Step 1: Failing tests:** `test_spoken_items_get_audio_once` (a second run voices nothing new); `test_tts_failure_leaves_item_unvoiced` (no `audio_url`, a note, songs untouched — Focus 3 server side); `test_id_audio_reused` (one file per ID line per station); `test_voicing_window_is_two_hours`.
- [ ] **Step 2:** Run: FAIL. **Step 3:** Implement: WAV → MP3 with ffmpeg, upload through `put_object`. Planned slot lengths stay as scheduled; real lengths are stored and used by the browser (ruling). **Step 4:** Run: PASS. Commit.

### Task 5: Play songs and voice in order

**Files:** Modify `templates/live.js` (`liveSegments(items, nowMs) -> {segments: [{kind: "songs", songIds, startTime} | {kind: "voice", src, offset} | {kind: "news"}], ...}`), `templates/shell.js` (a station plays segment by segment: MusicKit `setQueue` for a song block; on its end, our `<audio>` for a voice item; `news` plays the current newscast from the strip data when it is under 70 minutes old, else skipped); tests `tests/js/test_live.js`, e2e `tests/e2e/test_station_playback.py`.

- [ ] **Step 1: Failing tests:** JS `test_segments_in_order`, `test_join_mid_break` (offset into the voice item), `test_stale_news_is_skipped` (Focus 5), `test_unvoiced_items_dropped`; e2e `test_break_plays_between_songs`, `test_one_sound_at_a_time` (MusicKit paused or ended whenever our audio plays — Focus 4), `test_unvoiced_item_is_skipped` (Focus 3), `test_join_mid_break`.
- [ ] **Step 2:** Run: FAIL. **Step 3:** Implement. **Step 4:** Run (with the test copy republished): PASS. Commit.

### Task 6: Show the work, docs, review, live

- [ ] **Step 1:** Tracklists list breaks between songs: "Host break", the script as text, its sources linked, ▶ to hear it. The explainer's "Breaks, IDs and news" section describes what now airs. Test `test_tracklist_shows_breaks_with_sources`.
- [ ] **Step 2:** Decision 014 (Perplexity for facts, a host voice per station, what B2 costs per day); README.
- [ ] **Step 3:** Fresh Opus review with this Review Focus; fix Critical/Important test-first.
- [ ] **Step 4:** With Tarik's go: merge; watch one hour of each station on the Sprite (breaks voiced, Jev answers logged, Perplexity spend); listen to one break per station; e2e against the live pages.
