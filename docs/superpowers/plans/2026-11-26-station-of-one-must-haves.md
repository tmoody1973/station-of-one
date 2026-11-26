# Station of One: "Must have by Sunday" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An hourly pipeline on the Sprite that scrapes public posts, lets Jev pick the stories, writes and voices a five-minute newscast with chapters, publishes a front page, hour pages, control room and read-only settings page to a public bucket, archives each newscast to Box, and renders one daily vertical video.

**Architecture:** A Python package `station/` with one module and one CLI subcommand per pipeline step. Each step reads the previous step's JSON from a run folder (`data/runs/<YYYY-MM-DDTHH>/`) and writes its own, so every step can be run and tested alone. A thin build command runs the steps in order, holds the Sprite awake with the Tasks API, and hands failures to the station manager (headless Claude CLI). All external calls go through the Sprites connector gateway with no keys anywhere.

**Tech Stack:** Python 3.13 (stdlib `urllib`, `sqlite3`, `wave`, `zoneinfo`), Jinja2 (autoescaping HTML templates), pytest, ffmpeg 8.0.1 (apt), Remotion 4.0.547 (Node 24) for the video, GitHub Actions for the hourly trigger.

**Spec:** `docs/SPEC.md` (source of truth for scope). Also read: `CLAUDE.md`, `docs/THURSDAY-CHECKS.md` (every request and response shape here was proven there), `docs/RESEARCH-NOTES.md`, `docs/decisions/001-sting-from-lyria.md`, `docs/decisions/002-air-rule.md`, `docs/reference/gemini-tts-prompting.md`, `mockups/` (PNGs for layout, `.dc.html` for copy and colors).

## Global Constraints

Copied from `docs/SPEC.md` and `CLAUDE.md`; every task includes these.

- All external calls go through the Sprites connector gateway. Never put an API key in the Sprite, in code, in config, or in the repo.
- Gateway base URLs come from `GET https://api.sprites.dev/v1/gateway/list` → `connections[].gateway_base_url`. Never hard-code a connection id. Gateway calls only work from inside the Sprite.
- Jev decides; code applies thresholds. A language model never chooses what airs.
- Airs: the five highest Q1 scores among posts with Q1 at or above the air floor (start 0.40, tune Friday).
- Dropped and never shown if Q6 is at or above 0.20.
- Every answer and probability is logged with post id, question id and timestamp (also log Jev's returned `model`, e.g. `jev-1.14.0`).
- Scripts are written only from posts that passed selection.
- Every claim is attributed to where it was posted. Scraped claims are never stated as fact.
- Summaries are in the show's own words. At most one short quoted line per story, author named.
- Public sources only in this build. No inbox, calendar or logged-in feeds.
- No licensed music in audio, feed or video.
- The page and feed state that voices are synthetic and the show is machine-edited. Footer copy: "Voices are synthetic. This show is machine-edited from public posts, with every source linked."
- No real station's name, call letters, theme or look. Do not copy any real outlet's design.
- Station ID: "WONE, 1.0 FM. One station, one listener." and "Listener-supported. Listener, singular." rotate in the open or sign-off.
- Tone: calm, dry, public-radio pacing. No jokes written into the script.
- Voices: host `Kore`, reporter `Charon`, style `"brisk, warm, conversational news read"` (chosen by ear Nov 26). Model `gemini-3.8-flash-tts` via `generateContent` only (the Interactions API is refused by the connector).
- Broadcast hours from preferences (default 7 am to 7 pm, 13 newscasts), timezone `America/Chicago`.
- The whole build finishes in under ten minutes.
- One MP3 per newscast, mono, loudness-normalized; each chapter generated separately, then joined; chapter markers embedded and written to a chapters JSON.
- Public files go to the bucket; every public link names its file (`/index.html`), because Tigris serves no index documents.
- Small steps, each runnable by hand: every step has a CLI entry point that reads and writes files.
- Keep a run log per build (step, tool, counts, seconds, status). Log notes from the station manager.

## Review Focus

The five failure modes most likely to bite a listener, with the task whose tests pin each one.

1. **Scraped text carrying markup or reserved characters** (`<script>`, `{{ }}`, `=`, `;`, `#`, newlines) must appear as plain text on every page and must not break chapter metadata. Tests: Task 12 `test_front_page_escapes_post_html`, Task 10 `test_chapter_title_escaping`.
2. **A connector call fails mid-build** (429/529/5xx/timeout): transient errors retry with backoff; a failed story chapter is dropped and the newscast still publishes. Tests: Task 2 `test_retries_429_then_succeeds`, Task 11 `test_build_survives_failed_story_chapter`.
3. **A quiet hour** (zero new posts, or fewer than three eligible stories): a short newscast still airs and says so on air. Tests: Task 7 `test_short_when_fewer_than_three`, Task 8 `test_short_newscast_line`.
4. **Overlapping builds** (the next :48 trigger, or a hand trigger, while a build is running): the second build exits without touching the first; a lock older than 20 minutes is treated as stale. Test: Task 11 `test_lock_blocks_second_build`, `test_stale_lock_is_broken`.
5. **Local time edges** (Central time, the 7 pm last newscast, "today" resetting at local midnight): the open says the local hour and counts reset at local midnight. Tests: Task 8 `test_open_says_local_hour`, Task 3 `test_posts_today_resets_at_local_midnight`.

## Manual steps for Tarik (by when)

| When | Step |
| --- | --- |
| Before Task 1 | Approve creating the public GitHub repo (`gh repo create`). |
| Before Task 8 | Fly dashboard → Sprites → Connectors → add **Ollama Cloud** (key from ollama.com/settings/keys), grant `brave-indigo-lion`. |
| Before Task 10 | Make the sting in AI Studio with Lyria (decision 001), export WAV, put it at `assets/sting.wav`. A generated tone stands in until then. |
| Friday | Buy the Apify Starter plan (decided Nov 26). |
| Before Task 14 | Create a public Tigris bucket (no dots in the name; payment method required for public buckets) and add the **Tigris** connector. |
| Before Task 15 | Add the **Box** connector (OAuth, whole-account access) and create a folder for archives. |
| Before Task 16 | Add the **Pinecone** connector (key from the Pinecone console). |
| Before Task 18 | Create a Sprites token at sprites.dev/account; store it as GitHub secret `SPRITES_TOKEN`. |
| Before Task 19 | Add the **Deepgram** connector (saving the key runs a ~18 s paid test). |

## File Structure

```
station/
  __init__.py
  __main__.py        # CLI: python -m station <step> --run <dir> | build | video | ...
  config.py          # Prefs dataclasses, load_prefs()
  gateway.py         # Gateway client: base URLs, JSON requests, retries
  store.py           # SQLite: posts, decisions, source_state, aired
  runlog.py          # RunLog: per-step timing, counts, status, notes
  runs.py            # run folder paths and JSON read/write helpers
  sprite.py          # Tasks API hold (heartbeat), checkpoint
  steps/
    scrape.py  dedupe.py  judge.py  rundown.py  write.py
    voice.py   assemble.py  page.py  publish.py  archive.py  finish.py
    captions.py  video.py
  manager.py         # station manager: headless Claude CLI on step failure
  build.py           # runs steps in order with lock, hold and manager
templates/           # Jinja2: base.html, front.html, hour.html, control_room.html, settings.html, player.js
video/               # Remotion project (Task 19)
assets/sting.wav     # Lyria sting (Tarik); tone placeholder until then
config/preferences.json
scripts/start_build.sh
.github/workflows/hourly.yml
tests/
  conftest.py  fakes.py
  fixtures/          # real payloads captured Nov 26 (Task 1)
  test_<module>.py
data/                # gitignored: station.db, runs/
```

### Data contract: `newscast.json` (one per newscast)

Shaped for the future collections in `CLAUDE.md` (newscasts, stories, sources, beats).

```json
{
  "id": "2026-11-27T09",
  "hour_local": "2026-11-27T09:00:00-06:00",
  "show": "The Hourly Scroll", "station": "WONE", "frequency": "1.0 FM",
  "short": false,
  "counts": {"posts_read_hour": 164, "posts_read_today": 2140, "stories_aired": 5, "posts_not_aired_today": 2119},
  "stories": [{"id": "hn:50656036", "beat_id": "ai-dev", "part": "lead", "headline": "...", "summary": "...",
               "score_matter_week": 0.62, "seconds": 90,
               "sources": [{"post_id": "hn:50656036", "url": "...", "author": "...", "source_name": "Hacker News", "posted_at": "..."}]}],
  "almost": [{"post_id": "...", "title": "...", "url": "...", "score_matter_week": 0.39}],
  "overheard": null,
  "chapters": [{"index": 0, "title": "Open", "kind": "open", "story_id": null, "start_ms": 0, "end_ms": 10400}],
  "audio": {"file": "newscast.mp3", "duration_ms": 300000},
  "voices_synthetic": true
}
```

Run folder files, written by the step named: `posts.json` (scrape), `clusters.json` (dedupe), `judged.json` (judge), `rundown.json` (rundown), `scripts.json` (write), `audio/ch_NN.wav` (voice), `newscast.mp3` + `chapters.json` (assemble), `newscast.json` (assemble), `site/**` (page), `run_log.json` (every step).

---

# Friday: one complete newscast by hand trigger

### Task 1: Repo, package skeleton, preferences, test fixtures

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `station/__init__.py`, `station/config.py`, `station/runs.py`, `config/preferences.json`, `tests/conftest.py`, `tests/fixtures/*.json`, `tests/test_config.py`
- Move: `spikes/` stays as-is (reference only; not imported by `station/`)

**Interfaces:**
- Produces: `load_prefs(path: Path) -> Prefs`; frozen dataclasses `Prefs(station: Station, voices: Voices, thresholds: Thresholds, beats: tuple[Beat, ...], writer: Writer)`, `Thresholds(air_min_probability: float, private_harm_max_probability: float, min_stories: int, max_stories: int)`, `Voices(host: str, reporter: str, style: str)`, `Beat(id: str, name: str, used_in: str, color: str, sources: tuple[Source, ...])`, `Source(type: str, ref: str, visibility: str)`, `Station(name, show_name, call_sign, timezone, first_newscast, last_newscast, frequency, id_lines_newscast: tuple[str, ...])`, `Writer(model: str)`.
- Produces: `runs.run_dir(hour_id: str) -> Path` (`data/runs/<hour_id>`), `runs.read_json(run: Path, name: str) -> Any`, `runs.write_json(run: Path, name: str, data: Any) -> Path` (atomic: temp file then rename).

- [ ] **Step 1: Create the repo.** `git init`; `.gitignore` with `data/`, `.venv/`, `spikes/output/`, `__pycache__/`, `node_modules/`, `video/out/`. Ask Tarik before `gh repo create station-of-one --public --source . --push`.
- [ ] **Step 2: `pyproject.toml`** with `requires-python = ">=3.13"`, dependencies `jinja2`, dev dependency `pytest`. Run `uv sync`.
- [ ] **Step 3: Write `config/preferences.json`** from the example, with real sources from check 3: HN (`hackernews`, `topstories`), subreddits `LocalLLaMA` (ai-dev) and `milwaukee` (milwaukee), and the 21 RSS feeds listed in `spikes/check3_apify.py` under `rss_full` (the three Google News RSS URLs excluded), each under its beat. Add `"writer": {"model": "gemma4:31b"}`. Thresholds: `air_min_probability: 0.4`, `private_harm_max_probability: 0.2`, `min_stories: 3`, `max_stories: 5`. Voices as in Global Constraints.
- [ ] **Step 4: Capture fixtures (on the Sprite, free reads).** With `spikes/gw.py`, fetch dataset items of the Nov 26 Apify runs `YhriFC0z5QovknSSM` (RSS), `T6bjjyxdYK7X3mdXl` (HN), `hAp038QPHLPTAjOzh` (Reddit) into `tests/fixtures/apify_rss.json`, `apify_hn.json`, `apify_reddit.json`; copy the check 1 Jev response into `tests/fixtures/jev_response.json`. Pull with `sprite file pull` (never `exec cat`), compare byte sizes.
- [ ] **Step 5: Write failing tests** in `tests/test_config.py`:

```python
def test_loads_thresholds():
    p = load_prefs(Path("config/preferences.json"))
    assert p.thresholds.air_min_probability == 0.4
    assert p.thresholds.private_harm_max_probability == 0.2
    assert (p.thresholds.min_stories, p.thresholds.max_stories) == (3, 5)

def test_voices():
    v = load_prefs(Path("config/preferences.json")).voices
    assert (v.host, v.reporter) == ("Kore", "Charon")

def test_rejects_missing_threshold(tmp_path):  # fail fast at the boundary
    bad = tmp_path / "p.json"; bad.write_text('{"thresholds": {}}')
    with pytest.raises(ValueError, match="air_min_probability"):
        load_prefs(bad)

def test_write_json_is_atomic(tmp_path):
    write_json(tmp_path, "x.json", {"a": 1})
    assert read_json(tmp_path, "x.json") == {"a": 1}
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 6: Run** `uv run pytest tests/test_config.py -v` → FAIL (module missing).
- [ ] **Step 7: Implement** `config.py` and `runs.py`. `load_prefs` raises `ValueError` naming the missing key.
- [ ] **Step 8: Run** → PASS.
- [ ] **Step 9: Commit** `git add -A && git commit -m "feat: package skeleton, preferences, fixtures"`.

### Task 2: Gateway client

**Files:** Create `station/gateway.py`, `tests/fakes.py`, `tests/test_gateway.py`

**Interfaces:**
- Produces: `class GatewayError(Exception)` with `.provider: str`, `.status: int`, `.body: str` (first 500 chars).
- Produces: `class Gateway` with `__init__(self, list_url: str = "https://api.sprites.dev/v1/gateway/list", sleep=time.sleep, urlopen=urllib.request.urlopen)`, `base(provider: str) -> str` (cached per instance), `request(method: str, provider: str, path: str, body: dict | list | bytes | None = None, headers: dict | None = None, timeout: float = 120) -> Response`, `json(method, provider, path, body=None, timeout=120) -> Any`.
- Produces: `@dataclass(frozen=True) Response(status: int, headers: dict[str, str], body: bytes)`.
- Produces (tests): `FakeGateway(routes: dict[tuple[str, str, str], list[Response]])` keyed by `(method, provider, path_prefix)`, popping responses in order; `.calls: list[tuple[str, str, str, Any]]`. Same `request`/`json`/`base` methods.

- [ ] **Step 1: Write failing tests:**

```python
def test_base_reads_listing():  # listing JSON shape from check 1
    gw = Gateway(urlopen=fake_urlopen({"connections": [{"provider": "typesafe",
          "gateway_base_url": "https://api.sprites.dev/v1/gateway/typesafe/abc"}]}))
    assert gw.base("typesafe") == "https://api.sprites.dev/v1/gateway/typesafe/abc"

def test_missing_connection_names_provider():
    gw = Gateway(urlopen=fake_urlopen({"connections": []}))
    with pytest.raises(GatewayError, match="ollama"):
        gw.base("ollama")

def test_retries_429_then_succeeds():  # Review Focus 2
    sleeps = []
    gw = gateway_with_responses([Response(429, {"Retry-After": "1"}, b""), Response(200, {}, b'{"ok":1}')],
                                sleep=sleeps.append)
    assert gw.json("POST", "typesafe", "/v1/systemone", {}) == {"ok": 1}
    assert sleeps == [1]

def test_403_not_retried_and_raises():  # connector refusals (check 2, check 3) are permanent
    gw = gateway_with_responses([Response(403, {}, b'{"error":"endpoint is not supported"}')])
    with pytest.raises(GatewayError) as e:
        gw.json("POST", "apify", "/v2/x", {})
    assert e.value.status == 403 and "not supported" in e.value.body
```

- [ ] **Step 2: Run** `uv run pytest tests/test_gateway.py -v` → FAIL.
- [ ] **Step 3: Implement.** No auth header is ever sent. Retry statuses `{429, 500, 502, 503, 504, 529}` and `URLError`/timeouts up to 3 times; wait `Retry-After` seconds if present, else 2, 4, 8. `json()` raises `GatewayError` on any non-2xx after retries.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat: gateway client with retries`.

### Task 3: Store and run log

**Files:** Create `station/store.py`, `station/runlog.py`, `tests/test_store.py`, `tests/test_runlog.py`

**Interfaces:**
- Produces: `open_db(path: Path = Path("data/station.db")) -> sqlite3.Connection` creating tables `posts(id PK, source, beat, kind, author, title, url, text, posted_at, engagement_json, visibility, scraped_at)`, `decisions(post_id, question_id, answer_type, value, probability, confidence, raw, model, asked_at, PRIMARY KEY(post_id, question_id, asked_at))`, `source_state(source_key PK, last_success_at)`, `aired(post_id, newscast_id, part, score_matter_week, aired_at)`.
- Produces: `@dataclass(frozen=True) Post(id: str, source: str, beat: str, kind: str, author: str | None, title: str, url: str, text: str, posted_at: str, engagement: dict, visibility: str)` (`kind` ∈ `"story" | "comment"`).
- Produces: `upsert_posts(db, posts: Iterable[Post]) -> list[Post]` (returns only posts not seen before), `record_decision(db, post_id: str, question_id: str, answer: dict, model: str, asked_at: str) -> None`, `posts_read_since(db, since_utc: datetime) -> int`, `local_midnight_utc(now_utc: datetime, tz: str) -> datetime`, `get_cursor(db, key) -> datetime | None`, `set_cursor(db, key, when) -> None`, `record_aired(db, newscast_id, stories) -> None`.
- Produces: `class RunLog(path: Path)` with context manager `step(name: str, tool: str) -> StepRecord` (`StepRecord.counts: dict`, `.notes: list[str]`, `.status` set to `"done"`, `"failed"` or `"repaired"`), writing `run_log.json` after every step as `{"run_id", "started_at", "steps": [{"name","tool","status","seconds","counts","notes"}], "total_seconds"}`.

- [ ] **Step 1: Write failing tests:** `test_upsert_returns_only_new`, `test_record_decision_stores_noul_probability` (noul answer `{"type":"noul","noul":0.48}` → `probability == 0.48`, `value == "no"`; choice answer → `value == choice`, `probability == probabilities[choice]`, `confidence` kept), `test_posts_today_resets_at_local_midnight` (Review Focus 5: `local_midnight_utc(datetime(2026,11,28,5,30,tzinfo=UTC), "America/Chicago") == datetime(2026,11,27,6,0,tzinfo=UTC)`), `test_runlog_marks_failed_step_and_reraises`, `test_runlog_records_seconds_and_counts`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat: sqlite store and run log`.

### Task 4: `scrape` step (Apify)

**Files:** Create `station/steps/scrape.py`, `station/__main__.py` (argparse with one subcommand per step), `tests/test_scrape.py`

**Interfaces:**
- Consumes: `Gateway.json`, `Prefs.beats`, `store.upsert_posts`, `get_cursor`/`set_cursor`, `RunLog`.
- Produces: `ACTORS = {"hackernews": "constructive_calm~hacker-news-scraper", "subreddit": "automation-lab~reddit-scraper", "rss": "santamaria-automations~rss-feed-reader"}`.
- Produces: `actor_input(source_type: str, refs: list[str], since: datetime) -> dict`, `run_actor(gw, actor_id: str, actor_input: dict, cap_usd: float = 0.25, memory_mb: int | None = None, timeout_s: int = 240) -> list[dict]`, `normalize(source_type: str, item: dict, beat_id: str) -> list[Post]`, `scrape(gw, prefs, db, now: datetime) -> list[Post]`. CLI: `python -m station scrape --run <dir>` writes `posts.json` (new posts only).

Facts from check 3 (do not re-derive): `run-sync-get-dataset-items` returns **403** through the connector. Use `POST /v2/actors/<id>/runs?timeout=240&maxTotalChargeUsd=0.25` (201, `data.id`, `data.defaultDatasetId`), poll `GET /v2/actor-runs/<id>?waitForFinish=60` while `data.status` ∈ `READY, RUNNING, TIMING-OUT, ABORTING`, then `GET /v2/datasets/<id>/items?clean=1&format=json`. Inputs: HN `{"mode":"topstories","maxItems":30,"includeComments":true,"maxCommentDepth":1,"dateFromUnix":<since>}`; Reddit `{"urls":["https://www.reddit.com/r/<sub>/"],"sort":"new","postedAfter":"<ISO since>","maxPostsPerSource":25,"includeComments":true,"maxCommentsPerPost":3,"commentDepth":1,"includeNsfw":false}` (all subreddits in one run); RSS `{"feedUrls":[...],"maxItemsPerFeed":25,"includeContent":true,"filterByDate":"<ISO since>"}` (skip items with `type != "feed_item"`). HN runs pass `memory_mb=1024` (cuts the per-GB start fee; inferred, verify charges in the first real run's log).

- [ ] **Step 1: Write failing tests** using the Task 1 fixtures:

```python
def test_normalize_hn_story_and_comments():
    posts = normalize("hackernews", load_fixture("apify_hn.json")[0], "ai-dev")
    story = posts[0]
    assert story.id.startswith("hn:") and story.kind == "story"
    assert story.engagement == {"points": ANY_INT, "comments": ANY_INT}
    assert any(p.kind == "comment" for p in posts[1:])

def test_normalize_reddit_post():     # fields: author, title, selfText, permalink, score, numComments, createdAt
def test_normalize_rss_skips_feed_summary():
def test_run_actor_polls_until_succeeded():  # FakeGateway: 201 READY -> RUNNING -> SUCCEEDED -> items
def test_run_actor_sends_spend_cap():   # path contains "maxTotalChargeUsd=0.25"
def test_scrape_returns_only_new_posts_and_advances_cursor():
def test_one_failed_source_does_not_stop_others():  # GatewayError on reddit; HN and RSS posts still returned; counts note it
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** `since` = per-source cursor, else `now - 2h`. Every post gets `visibility="public"`. Only beats with `used_in == "newscast"` are scraped (music is a later, nice-to-have section). **Step 4: Run** → PASS.
- [ ] **Step 5: Real run on the Sprite** (spends Apify credit, approved scope): `python -m station scrape --run data/runs/test-friday`; check `run_log.json` counts and each run's `usageTotalUsd`.
- [ ] **Step 6: Commit** `feat: scrape step via Apify runs API`.

### Task 5: `dedupe` step (link matching first; Pinecone added in Task 16)

**Files:** Create `station/steps/dedupe.py`, `tests/test_dedupe.py`

**Interfaces:**
- Produces: `normalize_url(url: str) -> str` (lowercase host, drop `www.`, scheme, fragment, trailing `/`, and `utm_*`/`ref` query params), `title_key(title: str) -> str` (lowercase, punctuation stripped, stopwords `a an the` dropped), `@dataclass(frozen=True) Cluster(primary_id: str, member_ids: tuple[str, ...])`, `cluster(posts: list[Post], recent_aired: list[Post]) -> tuple[list[Cluster], list[tuple[str, str]]]` returning clusters merged by identical normalized URL and the candidate pairs (same `title_key`, different URL) that Jev Q5 must confirm. CLI writes `clusters.json`.

- [ ] **Step 1: Failing tests:** `test_same_url_with_utm_merges`, `test_hn_discussion_and_article_merge_by_linked_url`, `test_same_title_different_url_is_candidate_not_merge`, `test_primary_is_highest_engagement`.
- [ ] **Step 2–4:** run FAIL, implement, run PASS. **Step 5: Commit** `feat: dedupe by link match`.

### Task 6: `judge` step (Jev)

**Files:** Create `station/steps/judge.py`, `tests/test_judge.py`

**Interfaces:**
- Consumes: `Gateway.json("POST", "typesafe", "/v1/systemone", req)`, `record_decision`, clusters from Task 5.
- Produces: `PER_POST_QUESTIONS: dict` (exact `matter_week`, `new_or_reaction`, `part`, `primary_source`, `private_harm` definitions from `spikes/check1_jev.py`); `same_story_question(i: int) -> dict` (`{"type":"noul","instructions":"Is \`post\` about the same story as \`earlier_posts[<i>]\`?"}`); `build_request(post: Post, earlier: list[Post]) -> dict`; `@dataclass(frozen=True) Judged(post: Post, answers: dict, model: str)` with properties `matter_week: float`, `private_harm: float`, `primary_source: float`, `part: str`, `is_reaction: bool` and classmethod `from_response(post: Post, response: dict) -> Judged`; `judge_all(gw, db, posts, candidates, concurrency: int = 8) -> list[Judged]`; `seconds_question() -> dict` (score, 4 described levels from check 1); `seconds_from_score(score: float, levels: int = 4) -> int` = `round(20 + score / (levels - 1) * 25)`; `judge_seconds(gw, stories: list[Post]) -> dict[str, int]`. CLI writes `judged.json`.

- [ ] **Step 1: Failing tests:**

```python
def test_request_shape_matches_check1():
    req = build_request(post, earlier=[])
    assert req["model"] == "jev-latest" and set(req["questions"]) == set(PER_POST_QUESTIONS)
    assert req["state"]["post"]["text"] == post.text

def test_parses_check1_fixture():
    j = Judged.from_response(post, load_fixture("jev_response.json"))
    assert (j.matter_week, j.private_harm, j.part, j.model) == (0.48, 0.08, "story", "jev-1.14.0")

def test_every_answer_logged(db):   # 5 questions -> 5 decision rows with model and asked_at
def test_seconds_from_score():
    assert seconds_from_score(0.0) == 20 and seconds_from_score(3.0) == 45 and seconds_from_score(0.92) == 28
def test_same_story_candidate_adds_question():
```

- [ ] **Step 2–4:** FAIL, implement (thread pool, `concurrency=8`; rate limits are unknown, so rely on the gateway's 429 retry), PASS.
- [ ] **Step 5: Real run** on the Sprite against Task 4's `posts.json`; record total Jev input tokens in run log counts.
- [ ] **Step 6: Commit** `feat: judge step with Jev`.

### Task 7: `rundown` step (thresholds in code)

**Files:** Create `station/steps/rundown.py`, `tests/test_rundown.py`

**Interfaces:**
- Consumes: `list[Judged]`, `Prefs.thresholds`, `judge_seconds`.
- Produces: `@dataclass(frozen=True) Rundown(stories: tuple[Judged, ...], seconds: dict[str, int], overheard: Judged | None, dropped_ids: tuple[str, ...], almost: tuple[Judged, ...], short: bool, corrections: bool)`; `select(judged: list[Judged], t: Thresholds, first_of_day: bool) -> Rundown`. CLI writes `rundown.json`.

Rules (spec §2, §4, decision 002): drop if `private_harm >= 0.20` (never shown anywhere, not even in `almost`); exclude `is_reaction` and `part == "none"` from stories; eligible if `matter_week >= 0.40`; stories = top `max_stories` by `matter_week`, lead = first; `short = len(stories) < min_stories`; `almost` = top five eligible-or-not, non-dropped, non-aired by `matter_week`; overheard = the `kind == "comment"` post with the highest `part == "overheard"` probability among non-dropped posts (Overheard is first in the cut order; skip when none); seconds: lead 60 (90 when `corrections` is False), others from `judge_seconds` (20–45). `corrections` is False this build (should-have).

- [ ] **Step 1: Failing tests:** `test_private_harm_at_threshold_dropped` (0.20 dropped, 0.19 kept), `test_floor_is_at_or_above` (0.40 airs, 0.39 not), `test_top_five_only`, `test_lead_is_highest_score`, `test_reaction_and_none_excluded`, `test_short_when_fewer_than_three` (Review Focus 3), `test_dropped_never_in_almost`, `test_lead_gets_90_without_corrections`.
- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** `feat: rundown applies thresholds in code`.

### Task 8: `write` step (Ollama Cloud)

**Files:** Create `station/steps/write.py`, `tests/test_write.py`

**Prerequisite:** Tarik adds the Ollama Cloud connector. First step proves it.

**Interfaces:**
- Consumes: `Rundown`, `Prefs`, `Gateway.json("POST", "ollama", "/api/chat", ...)`, counts from `store`.
- Produces: `@dataclass(frozen=True) Turn(speaker: str, text: str)` (`speaker` ∈ `"host" | "reporter"`); `@dataclass(frozen=True) Chapter(index: int, kind: str, title: str, story_id: str | None, turns: tuple[Turn, ...])` (`kind` ∈ `open, lead, story, overheard, signoff`); `open_chapter(hour_local: datetime, id_line: str) -> Chapter` and `signoff_text(read_today: int, not_aired_today: int, short: bool = False) -> str` and `signoff_chapter(read_today: int, not_aired_today: int, id_line: str, short: bool) -> Chapter` (templates in code, no model; numbers formatted with thousands separators); `messages_for(kind: str, story: Judged, sources: list[Post], seconds: int) -> list[dict]`; `parse_turns(text: str) -> tuple[Turn, ...]` (lead only: model writes `HOST:`/`REPORTER:` lines; labels are stripped here and never reach the voice); `problems(chapter: Chapter, seconds: int) -> list[str]`; `write_all(gw, rundown, prefs, counts) -> list[Chapter]` (max 3 concurrent Ollama requests). CLI writes `scripts.json`.

Request (Ollama docs, RESEARCH-NOTES §6.5): `{"model": prefs.writer.model, "messages": [...], "stream": false, "think": false, "options": {"temperature": 0.4}}` → text at `message.content`. Cloud models have no structured output: plain text only.

Prompt rules (from the spec and `docs/reference/gemini-tts-prompting.md`; put them in the system message verbatim): write only from the given posts; attribute every claim to where it was posted ("posters on Hacker News say", "according to <outlet>"); never state a scraped claim as fact; hedge more when `primary_source < 0.5`; at most one short quoted line, author named; plain spoken words only, no stage directions, no names in brackets; pauses with punctuation, `--`, `...` or `<short pause>`; CAPS only for rare emphasis; calm, dry public-radio pacing, no jokes; target words = `seconds × 2.8` (≈168 wpm, measured Nov 26 for Kore).

- [ ] **Step 1: Prove the connector** on the Sprite: one `/api/chat` call with `gemma4:31b`, `stream:false`, `think:false`; record request, response shape and seconds in `docs/THURSDAY-CHECKS.md` under a new "Friday checks" heading.
- [ ] **Step 2: Failing tests:**

```python
def test_open_says_local_hour():   # Review Focus 5
    ch = open_chapter(datetime(2026, 11, 27, 21, 0, tzinfo=ZoneInfo("America/Chicago")), "WONE, 1.0 FM. One station, one listener.")
    text = " ".join(t.text for t in ch.turns)
    assert "nine o'clock" in text and "here's the last hour on your internet" in text.lower()

def test_signoff_counts():
    assert "I've read 2,140 posts today so you didn't. 2,119 didn't make air." in signoff_text(2140, 2119)

def test_short_newscast_line():    # Review Focus 3
    assert "quiet hour" in signoff_text(40, 39, short=True).lower()

def test_parse_turns_strips_labels():
    assert parse_turns("HOST: Here's our lead.\nREPORTER: Mozilla says...") == (Turn("host", "Here's our lead."), Turn("reporter", "Mozilla says..."))

def test_problems_flags_label_bracket_and_length():
    assert problems(Chapter(1, "story", "x", "s", (Turn("host", "Host: (calmly) hi"),)), 40)
```

- [ ] **Step 3–5:** FAIL, implement (one retry when `problems()` is non-empty; second failure → the chapter is dropped and noted), PASS.
- [ ] **Step 6: Real run** on Task 7's `rundown.json`; read the scripts aloud-test in Task 9.
- [ ] **Step 7: Commit** `feat: write step with Ollama Cloud`.

### Task 9: `voice` step (Gemini TTS)

**Files:** Create `station/steps/voice.py`, `tests/test_voice.py`

**Interfaces:**
- Consumes: `list[Chapter]`, `Prefs.voices`.
- Produces: `tts_request(chapter: Chapter, voices: Voices) -> dict`; `synthesize(gw, chapter, voices, out: Path) -> float` (seconds); `voice_all(gw, chapters, voices, run: Path) -> list[Path]` (one call per chapter, 4 in parallel, writes `audio/ch_NN.wav`; a failed chapter raises `ChapterFailed(index)` collected by the build).

Facts from check 2 (do not re-derive): `POST /v1beta/models/gemini-3.8-flash-tts:generateContent`. Two speakers (lead): one `part` per turn with `"speech_metadata": {"speaker": "Host"|"Reporter", "style": voices.style}`, `generationConfig.speechConfig.multiSpeakerVoiceConfig.speakerVoiceConfigs = [{"speaker":"Host","voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Kore"}}}, {"speaker":"Reporter",...,"Charon"}]`. One speaker: `"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Kore"}}}`, part carries `speech_metadata.style`. Response audio: `candidates[0].content.parts[0].inlineData.data` (base64), `mimeType: "audio/wav"`, 24 kHz mono 16-bit, already a WAV.

- [ ] **Step 1: Failing tests:** `test_lead_request_is_two_speaker`, `test_story_request_is_single_speaker_kore`, `test_style_on_every_part`, `test_writes_wav_without_rewrapping` (bytes start `RIFF`, written unchanged), `test_rejects_non_riff_audio`.
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Real run** on Task 8's scripts; pull one chapter with `sprite file pull` for Tarik to listen.
- [ ] **Step 6: Commit** `feat: voice step with Gemini TTS`.

### Task 10: `assemble` step (ffmpeg)

**Files:** Create `station/steps/assemble.py`, `assets/sting.wav` (placeholder: 2 s 440 Hz tone, 24 kHz mono, until Tarik's Lyria sting), `tests/test_assemble.py`

**Interfaces:**
- Consumes: `audio/ch_NN.wav`, `list[Chapter]`, `Rundown`, counts.
- Produces: `escape_meta(value: str) -> str` (backslash before `= ; # \` and newline); `chapter_metadata(chapters: list[tuple[str, int, int]], title: str) -> str` (FFMETADATA1, `TIMEBASE=1/1000`); `durations_ms(wavs: list[Path]) -> list[int]` (stdlib `wave`); `assemble(run: Path, chapters: list[Chapter], sting: Path) -> dict` (newscast dict per the data contract). Writes `newscast.mp3`, `chapters.json`, `newscast.json`.

Commands (check 4, proven): concat demuxer list of `sting.wav` + chapters + `sting.wav` (sting time folds into the Open and Sign-off chapters); `ffmpeg -f concat -safe 0 -i list.txt -i chapters.ffmeta -map 0:a -map_metadata 1 -map_chapters 1 -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 44100 -ac 1 -c:a libmp3lame -b:a 64k -id3v2_version 3 newscast.mp3`. Do not use `chapter_per_file` (not in ffmpeg 8.0.1). If `assets/sting.wav` is not 24 kHz mono, convert it first with `-ar 24000 -ac 1`.

- [ ] **Step 1: Failing tests:** `test_chapter_title_escaping` (Review Focus 1: title `Q&A = "yes"; #1` → `Q&A \= "yes"\; \#1`), `test_chapter_times_are_cumulative`, `test_newscast_json_matches_contract` (keys and `voices_synthetic: true`), and on the Sprite `test_mp3_has_chapters` (marked `@pytest.mark.ffmpeg`: `ffprobe -show_chapters` count equals chapters, file starts `ID3`).
- [ ] **Step 2–4:** FAIL, implement, PASS (`uv run pytest -m ffmpeg` on the Sprite).
- [ ] **Step 5: Commit** `feat: assemble MP3 with chapters`.

### Task 11: Build command, lock, hold, deploy to the Sprite — **Friday milestone**

**Files:** Create `station/build.py`, `station/sprite.py`, `scripts/start_build.sh`, `tests/test_build.py`

**Interfaces:**
- Consumes: every step's entry function; `RunLog`.
- Produces: `STEPS: list[tuple[str, str, Callable]]` = (name, tool, fn) in spec order; `build(hour_local: datetime, steps=STEPS, lock_path=Path("data/build.lock")) -> Path` (run folder); `acquire_lock(path: Path, max_age_s: int = 1200) -> bool`; `sprite.hold(name: str = "build", expire: str = "5m") -> contextmanager` (heartbeat thread: `PUT http://sprite/v1/tasks/<name>` over `/.sprite/api.sock` every 60 s, `DELETE` on exit; no-op when the socket is absent, e.g. in tests). CLI: `python -m station build [--hour 2026-11-27T09]`. `scripts/start_build.sh`: `cd ~/station && git pull --ff-only && nohup setsid uv run python -m station build > data/last_build.out 2>&1 &` (returns immediately; the build holds the Sprite awake itself).
- Station-manager hook: `build()` calls `on_failure(step_name, exc, run)`; this task passes a stub that records the error in the run log; Task 17 replaces it.

- [ ] **Step 1: Failing tests:** `test_steps_in_spec_order`, `test_lock_blocks_second_build` (Review Focus 4), `test_stale_lock_is_broken`, `test_build_survives_failed_story_chapter` (Review Focus 2: `ChapterFailed(3)` → chapter 3 dropped, MP3 still assembled, run log note), `test_failed_required_step_stops_and_logs`.
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Deploy.** On the Sprite: `git clone <public repo> ~/station`, `uv sync`, `sudo apt-get install -y ffmpeg` (already installed Thursday), copy `config/preferences.json`. `uv run pytest` on the Sprite → all pass, including `-m ffmpeg`.
- [ ] **Step 6: Milestone.** `sprite exec -s brave-indigo-lion -- bash -lc 'cd ~/station && uv run python -m station build'`. Pass when: under 10 minutes; `newscast.mp3` ≈ 5:00 (or a short newscast that says so); `ffprobe -show_chapters` lists Open, Lead, stories, Sign-off; Tarik listens via `sprite file pull` and tunes the air floor (decision 002) in `config/preferences.json`.
- [ ] **Step 7: Commit** `feat: build command; first full newscast`.

---

# Saturday: on the hour, on the page

### Task 12: `page` step: front page and hour page

**Files:** Create `station/steps/page.py`, `templates/base.html`, `templates/front.html`, `templates/hour.html`, `templates/player.js`, `tests/test_page.py`

**Interfaces:**
- Consumes: `newscast.json` (this hour), today's earlier `newscast.json` files, counts.
- Produces: `env() -> jinja2.Environment` (`FileSystemLoader("templates")`, `autoescape=select_autoescape(enabled_extensions=("html", "xml"), default_for_string=True)`); `render_front(current: dict, today: list[dict]) -> str`; `render_hour(newscast: dict) -> str`; `hour_path(newscast_id: str) -> str` = `h/<YYYY-MM-DD>/<HHMM>/index.html`; `page(run: Path) -> list[Path]` writing `site/index.html` and `site/<hour_path>`. Audio URL `audio/<id>.mp3` (relative to the bucket root).

Layout and copy: match `mockups/Front page.png` for layout and `mockups/Main.dc.html` for copy, sizes and colors (white ground, ink `#141414`, accent `#C8102E`, Space Grotesk headings, Inter body, beat colors from preferences). Must-have parts only (spec §7): header with show name and date; sticky player (play, −15 s, +15 s, time) holding the latest newscast; lead story (beat-colored card instead of an image, beat tag, headline, two-sentence summary, "Jev: NN% likely to matter in a week", source links, "Play from this story" seeking to its chapter `start_ms`); story cards; today's newscasts newest first (play, hour, duration, link to its page); counts module; footer copy from Global Constraints. Leave out The Table card, music picks, Corrections and almost-made-air (later section). Works at phone width (player bar at the bottom on narrow screens, PRD P26). Every internal link ends in `index.html`. `player.js` is plain JavaScript: one `<audio>`, seek by `data-start-ms`.

- [ ] **Step 1: Failing tests:** `test_front_page_escapes_post_html` (Review Focus 1: headline `<script>alert(1)</script>` appears as `&lt;script&gt;`), `test_links_end_in_index_html`, `test_footer_synthetic_line`, `test_play_from_story_uses_chapter_start`, `test_today_list_newest_first`.
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Visual check:** render Friday's newscast locally, open `site/index.html` at desktop and phone widths, compare with the PNG. Screenshots to Tarik.
- [ ] **Step 6: Commit** `feat: front page and hour pages`.

### Task 13: Control room and read-only settings pages

**Files:** Create `templates/control_room.html`, `templates/settings.html`, add `render_control_room(run_log: dict, decisions: list[dict], newscast: dict) -> str` and `render_settings(prefs: Prefs, posts_yesterday: dict[str, int], aired: dict[str, int]) -> str` to `station/steps/page.py`; `tests/test_page_extras.py`

Control room: match `mockups/Control room.png` and `ControlRoom.dc.html` (dark `#111214`, panels `#1b1d21`, JetBrains Mono for times and the decision log). Four stat tiles (posts read this hour / today, Jev decisions with "N questions per post", cleared for air with "floor 40%", build time with "budget 10:00"); each step with tool badge, detail from run-log counts, seconds, colored dot (green done, amber repaired, grey waiting); Jev's decisions list with verdict `AIR | CUT | DROP | MERGE`, percentage and post title; Station manager notes; Sprite card. Rebuilt at the end of every run (live updating is a stretch, skip).

Settings: match `mockups/Settings.png` and `Settings.dc.html`, read-only (no forms, no buttons that act). Beats table with sources count, posts yesterday, aired; broadcast hours, show name, voices "Host and reporter · Gemini TTS · synthetic"; editorial rules "Airs if likely to matter in a week: top five at 40% or higher", "Dropped if it may harm a private person: 20% or higher"; connections list (Apify, TypeSafe Jev, Ollama Cloud, Google Gemini, Pinecone, Box, Tigris, Anthropic) with the note "Keys are held by the Fly.io connector gateway and never stored on the Sprite." Leave out music taste, source scout and Blotato.

- [ ] **Step 1: Failing tests:** `test_decision_verdicts` (drop ≥ 0.20 → `DROP`, aired → `AIR`, merged → `MERGE`, else `CUT`), `test_settings_has_no_forms` (`"<form" not in html`), `test_settings_shows_floor_and_harm_rule`, `test_control_room_escapes_titles`.
- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** `feat: control room and settings pages`.

### Task 14: `publish` step: Tigris bucket

**Files:** Create `station/steps/publish.py`, `tests/test_publish.py`

**Prerequisite:** Tarik creates the public bucket and adds the Tigris connector.

**Interfaces:**
- Produces: `CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".mp3": "audio/mpeg", ".json": "application/json", ".js": "text/javascript", ".mp4": "video/mp4", ".png": "image/png"}`; `cache_control(key: str) -> str` (`max-age=60` for `index.html` and `.json`, `public, max-age=31536000, immutable` for hour pages' MP3s); `put_object(gw, bucket: str, key: str, data: bytes, content_type: str, cache: str) -> None`; `publish(gw, run: Path, bucket: str) -> list[str]` (uploads `site/**`, `newscast.mp3` as `audio/<id>.mp3`, `newscast.json` as `data/<id>.json`). Public URL `https://<bucket>.t3.tigrisfiles.io/<key>`.

- [ ] **Step 1: Prove the request shape.** Read Tigris's `usage_snippet` from `/v1/gateway/list`; PUT one 1 KB file with `Content-Type` and `Cache-Control`; `curl -I https://<bucket>.t3.tigrisfiles.io/<key>` and confirm both headers come back. Record in `docs/THURSDAY-CHECKS.md` "Friday checks". If headers don't pass through, stop and ask.
- [ ] **Step 2: Failing tests:** `test_content_types`, `test_hour_pages_and_index_keys`, `test_index_short_cache`.
- [ ] **Step 3–5:** FAIL, implement, PASS. **Step 6: Real run**, open the public URL on a phone. **Step 7: Commit** `feat: publish to Tigris`.

### Task 15: `archive` step: Box

**Files:** Create `station/steps/archive.py`, `tests/test_archive.py`

**Prerequisite:** Tarik adds the Box connector and names an archive folder.

**Interfaces:**
- Produces: `bundle(run: Path) -> Path` (zip of `newscast.json`, `chapters.json`, `scripts.json`, `rundown.json`, `run_log.json`, `decisions.jsonl` for this run, `newscast.mp3`; raises if over 50 MiB); `ensure_day_folder(gw, parent_id: str, day: str) -> str` (`POST /2.0/folders`, on 409 list the parent's items and match by name); `upload(gw, folder_id: str, path: Path) -> str` (multipart, `attributes` part first; returns `entries[0].id`).

- [ ] **Step 1: Prove upload routing** (the open question from research): read Box's `usage_snippet`; upload a 1 KB file to the path it shows. Record in `docs/THURSDAY-CHECKS.md`.
- [ ] **Step 2: Failing tests:** `test_bundle_contains_decision_log`, `test_bundle_size_guard`, `test_multipart_attributes_first`, `test_folder_409_reuses_existing`.
- [ ] **Step 3–5:** FAIL, implement, PASS. **Step 6: Commit** `feat: archive bundles to Box`.

### Task 16: Pinecone duplicate detection and memory of what aired

**Files:** Modify `station/steps/dedupe.py`; create `tests/test_dedupe_pinecone.py`

**Prerequisite:** Tarik adds the Pinecone connector.

**Interfaces:**
- Produces: `PINECONE_VERSION = "2026-07"` (sent on every request as `X-Pinecone-Api-Version`); `upsert_texts(gw, index: str, namespace: str, items: list[tuple[str, str]]) -> None`; `similar(gw, index: str, namespace: str, text: str, top_k: int = 5) -> list[tuple[str, float]]`; `cluster()` gains `pinecone_pairs: list[tuple[str, str]]` (score ≥ 0.85, tune) added to the Jev Q5 candidates. Embed only title plus first 300 characters of new posts (free-tier embedding budget, RESEARCH-NOTES §6.9). Aired stories also go to namespace `aired`.

- [ ] **Step 0 (added Nov 26): cross-hour duplicates.** The 3-hour lookback lets a story carried over from an earlier hour air beside a new copy from another outlet (Venice Biennale, 5 pm Nov 26). Candidate pairs must also compare this run's new stories against recently judged and recently aired stories (Pinecone similarity plus the title-overlap check), with Jev's same-story question deciding.
- [ ] **Step 1: Prove the route.** Try the Documents API through the gateway (create index with an `embed` text field, one upsert, one search). If `/namespaces/<ns>/documents/*` is refused, use the legacy route (`/embed`, then `/indexes/<name>/vectors/upsert` and `/indexes/<name>/query`; create the index with header `2026-04`). Record which in `docs/THURSDAY-CHECKS.md`.
- [ ] **Step 2: Failing tests** (FakeGateway): `test_high_similarity_becomes_candidate`, `test_sends_version_header`, `test_pinecone_failure_falls_back_to_link_matching` (cut order item 4).
- [ ] **Step 3–5:** FAIL, implement, PASS. **Step 6: Commit** `feat: Pinecone duplicate candidates`.

### Task 17: Station manager

**Files:** Create `station/manager.py`, `tests/test_manager.py`; modify `station/build.py`

**Interfaces:**
- Produces: `FALLBACKS: dict[str, list[str]]` (per step: e.g. `scrape: ["retry", "skip_source"]`, `voice: ["retry_chapter", "drop_chapter"]`, `dedupe: ["link_match_only"]`, `write: ["retry_chapter", "drop_chapter"]`); `prompt(step: str, error: str, run: Path) -> str`; `ask_manager(prompt: str, runner=subprocess.run) -> ManagerDecision(action: str, note: str)`; `on_failure(step, exc, run) -> ManagerDecision` (applies the action, marks the step `repaired` in the run log with the note).

Invocation (check 5, proven): `ANTHROPIC_BASE_URL=<anthropic gateway_base_url> ANTHROPIC_AUTH_TOKEN=placeholder-gateway-attaches-real-key claude -p "<prompt>" --model claude-haiku-5-5 --output-format json`, parse `result`. The model only picks one action from `FALLBACKS[step]` and writes a one-sentence note; code applies it. Confirm `claude -p` flags that restrict tools (`--allowedTools`, max turns) against current Claude Code docs before writing the call.

- [ ] **Step 1: Failing tests:** `test_unknown_action_falls_back_to_first_option`, `test_note_written_to_run_log`, `test_manager_timeout_does_not_block_build` (60 s cap).
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Real drill:** point one RSS feed at a 404 URL, run a build, confirm an amber "repaired" step and a note on the control room page.
- [ ] **Step 6: Commit** `feat: station manager on step failure`.

### Task 18: `finish` step and the hourly trigger

**Files:** Create `station/steps/finish.py`, `.github/workflows/hourly.yml`, `tests/test_finish.py`

**Interfaces:**
- Produces: `finish(run: Path) -> None` (final run log write, `record_aired`, `sprite-env checkpoints create --comment "build <id>"`; keeps checkpoints to the newest 24 by deleting older `v*` ones with `sprite-env checkpoints delete` if available, else note it); `in_broadcast_hours(now_local: datetime, prefs) -> bool`.
- Workflow: `on: schedule: - cron: "48 12-23 * * *"` and `- cron: "48 0 * * *"` (UTC; 6:48 am–6:48 pm Central for the 7 am–7 pm newscasts during CST) plus `workflow_dispatch`. One step: `curl -fsS -X POST "https://api.sprites.dev/v1/sprites/brave-indigo-lion/exec?cmd=bash&cmd=/home/sprite/station/scripts/start_build.sh" -H "Authorization: Bearer ${{ secrets.SPRITES_TOKEN }}"`.

- [ ] **Step 1: Failing tests:** `test_broadcast_hours_edges` (6:59 pm local true for the 7 pm build window, 7:30 pm false), `test_finish_records_aired`.
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Real trigger:** run the workflow by hand (`workflow_dispatch`); confirm a build starts on the Sprite and the page updates. Then watch two scheduled runs; note GitHub's actual start delay in `docs/THURSDAY-CHECKS.md`. If runs arrive later than :52, move the cron to :45.
- [ ] **Step 6: Commit** `feat: hourly trigger and finish step`.

---

# Sunday: video and submission

### Task 19: Daily vertical video (Deepgram captions + Remotion)

**Files:** Create `station/steps/captions.py`, `station/steps/video.py`, `video/` (Remotion project from `spikes/check4b_remotion.sh`), `tests/test_captions.py`

**Prerequisite:** Tarik adds the Deepgram connector.

**Interfaces:**
- Produces: `story_clip(newscast: dict, story_id: str, out: Path) -> Path` (ffmpeg cut of the lead chapter, 30–45 s, from `chapters.json` times); `words(gw, clip: Path) -> list[dict]` (`POST /v1/listen?model=nova-3&smart_format=true`, body = MP3 bytes, `Content-Type: audio/mpeg`; returns `results.channels[0].alternatives[0].words[]` as `{word, start, end}` in seconds); `video(day: str) -> Path` (picks the day's highest `score_matter_week` aired story, writes `video/public/props.json` and the clip, runs `npx remotion render Reel out/<day>.mp4 --props=public/props.json`, uploads to the bucket as `video/<day>.mp4`). CLI `python -m station video --day 2026-11-29`.

Remotion composition (simple version, spec §10): 1080x1920, 30 fps, 30–45 s, the story's real audio; count-up of posts read; headline with word-timed captions inside the safe area (keep text between 250 px from the top and 400 px from the bottom); end card with the page address ending in `index.html`. Follow the `remotion-best-practices` skill; check 4b render time was 33 s for 45 s.

- [ ] **Step 1: Prove Deepgram** with one real clip; record the response shape.
- [ ] **Step 2: Failing tests:** `test_words_parsed_in_seconds`, `test_clip_length_between_30_and_45`, `test_props_contain_captions_and_end_card_url`.
- [ ] **Step 3–5:** FAIL, implement, PASS.
- [ ] **Step 6: Render the real video**; Tarik watches it. Link "Download today's video" in the front page footer.
- [ ] **Step 7: Commit** `feat: daily vertical video`.

### Task 20: README and submission

**Files:** Create `README.md` (replace the handoff README)

- [ ] **Step 1:** README lists what the agent does in two sentences (the submission form's description), the live page URL (`.../index.html`), each connector and its job (the nine in `CLAUDE.md`), how to run one step by hand, and that voices are synthetic and the show is machine-edited.
- [ ] **Step 2:** Walk the spec §14 submission checklist; tick each with evidence (link, screenshot).
- [ ] **Step 3: Commit** `docs: README for judges`.

---

# Later: should have, nice to have, The Table

Not in Friday–Sunday tasks above. Pick up in this order if time allows (spec §12).

1. **Corrections** (should have): grade every story aired a week earlier (decided Nov 26). Backfill data exists in `~/spikes/check6/backfill.db` (19 stories scored Nov 26). Steps: follow-up scrape for each aired story, Jev `still_discussed` question, Corrections chapter in the first newscast of the day (lead drops to 60 s), Corrections box on the front page.
2. **Almost made air list** on the front page: `rundown.almost` already exists; add the module from `Main.dc.html`.
3. **RSS podcast feed** (should have): one "latest newscast" item replaced hourly; item description lists chapter timestamps; feed and audio in the bucket.
4. **Preview image** for link unfurls (Playwright screenshot of a template; Chromium installed Thursday).
5. **Bluesky source** (`blueskyscraper~bluesky-posts-scraper`, tested in check 3 round 2).
6. **Designed voices** (needs a test of `voice_...` IDs on `generateContent`, or the Custom API connector).
7. Generated graphics, music picks (nice to have).
8. **The Table**, only after the hourly newscast runs unattended; ship without it if not working by Sunday noon.
