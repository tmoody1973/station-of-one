# Thursday checks

Prove these before writing the implementation plan. Each is a small spike with a script
in `spikes/`. Record the result and anything surprising under each item.

1. **Jev answers from the Sprite.**
   Get an early-access key at console.typesafe.ai, add the TypeSafe AI connector, and send
   one typed question through the gateway. Note the real request and response shape and
   update `config/jev_questions.json` mapping notes.
   Result: **PASS** (Nov 26, 16:13 UTC). Spike `spikes/check1_jev.py`.
   - Gateway base: `https://api.sprites.dev/v1/gateway/typesafe/<connection_id>` (read from
     `GET /v1/gateway/list` → `connections[].gateway_base_url`; never hard-code the id).
     No auth header. Connector's own snippet also says SDKs work with
     `TYPESAFE_BASE_URL=<gateway base>` and any placeholder `TYPESAFE_API_KEY`.
   - `GET /v1/models` → 200, `{"models":[{"name":"jev-latest",...,"release_date":"2026-10-22..."},{"name":"jev-preview",...}]}`.
   - `POST /v1/systemone` → **200 in 0.21 s**, 760 input / 163 output tokens (≈ $0.00003).
     Request: `{"model":"jev-latest","state":{"post":{...},"earlier_posts":[{...}]},"questions":{...}}`
     with all seven questions in one call (6 per-post + seconds). Response (abridged):
     ```json
     {"model": "jev-1.14.0",
      "answers": {
        "matter_week":    {"type": "noul", "noul": 0.48},
        "new_or_reaction":{"type": "choice", "choice": "new_information", "confidence": 0.14,
                           "probabilities": {"new_information": 0.57, "reaction": 0.43}},
        "part":           {"type": "choice", "choice": "story", "confidence": 0.83,
                           "probabilities": {"lead": 0.01, "story": 0.87, "overheard": 0.05, "none": 0.07}},
        "primary_source": {"type": "noul", "noul": 0.61},
        "same_story":     {"type": "noul", "noul": 0.98},
        "private_harm":   {"type": "noul", "noul": 0.08},
        "seconds":        {"type": "score", "score": 0.92, "confidence": 0.77,
                           "legend": {"0": "A one-line mention", "1": "...", "2": "...", "3": "..."},
                           "probabilities": {"0": 0.16, "1": 0.79, "2": 0.03, "3": 0.02}}},
      "usage": {"input_tokens": 760, "output_tokens": 163}}
     ```
   - Confirms the docs: Noul has no `confidence`; `model` comes back versioned (`jev-1.14.0`);
     score is a float over described levels (0.92 of 0–3 → 28 s when mapped to 20–45).
   - No rate-limit headers came back. Rate limits still unknown.
   - Mapping for `config/jev_questions.json`: probability and yes/no → `noul`; choices →
     `choice` with `criteria` as `{name: description}`; seconds → `score` with 4 described
     levels mapped in code. Same-story uses a backticked path (`` `earlier_posts[0]` ``).

2. **Gemini two-speaker voice works through a connector.**
   Confirm the Google Gemini connector forwards the text-to-speech models. If it does not,
   use the Custom API connector. Save one two-speaker clip. Note the audio format returned
   and whether word timestamps are available (assumed: no).
   Result: **PASS for `generateContent`; Interactions API blocked.** Spike `spikes/check2_gemini_tts.py`.
   - `POST <gateway>/v1beta/models/gemini-3.8-flash-tts:generateContent` with
     `multiSpeakerVoiceConfig` (Host = Charon, Reporter = Kore), three turns each carrying
     `"speech_metadata": {"speaker": ..., "style": "calm, dry, unhurried"}` → **200 in 6.0 s**.
   - Response: `candidates[0].content.parts[0].inlineData` with **`mimeType: "audio/wav"`**;
     decoded bytes start `RIFF`: **24,000 Hz, mono, 16-bit, 16.86 s**, 816,988 bytes
     (response JSON 1.09 MB). `usageMetadata`: 53 text tokens in, **422 audio tokens out**
     (≈ 25/s), `serviceTier: "standard"`. Other keys: `modelVersion`, `responseId`.
   - `POST <gateway>/v1beta/interactions` → **403 `{"error":"endpoint is not supported by the
     Google Gemini connector"}`**. Designed voices (`voice_...`) are documented only on that
     endpoint, so they need either a test of `voice_...` on `generateContent` or the Custom
     API connector.
   - Connector snippet lists `generateContent`, `/v1beta/decisions` and `/v1beta/models`.
   - Word timestamps: none in the response (as assumed).
   - Listening test pending (Tarik): `spikes/output/check2_two_speaker.wav`. Confirm two
     distinct voices and that `<short pause>` was not read aloud.
   - **Pace (check 2b, Tarik: "why are the voices so slow"):** the check 2 clip ran ~110 wpm
     because every turn carried `style: "calm, dry, unhurried"` (from
     `config/preferences.example.json`). Spike `spikes/check2b_voice_pace.py`, same 48-word
     newscast paragraph, single speaker (`speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName`):

     | Voice | Style | Length | Pace |
     | --- | --- | --- | --- |
     | Charon | (none) | 17.3 s | 167 wpm |
     | Charon | brisk, warm, conversational news read | 14.6 s | 197 wpm |
     | Rasalgethi | same | 17.1 s | 169 wpm |
     | Iapetus | same | 17.0 s | 169 wpm |
     | Kore | same | 17.5 s | 164 wpm |
     | Alnilam | same | 15.4 s | 186 wpm |

     Removing "unhurried" fixes pace. Which voice sounds like a newscast is Tarik's ear test:
     clips in `spikes/output/voices/`. Cost ≈ $0.03.
   - **Voices chosen by ear (Tarik, Nov 26): host Kore, reporter Charon, style "brisk, warm,
     conversational news read".** Written to `config/preferences.example.json`. Two-speaker
     re-test with a newscast-style lead: 200 in 7.8 s, 25.53 s WAV,
     `spikes/output/check2_two_speaker_kore_charon.wav`. **Listening test passed (Tarik:
     "sounds great").**
   - **File copy gotcha:** `sprite exec ... cat <file> > local` failed twice (0-byte file;
     `Error: cannot resume output at byte 0: earliest retained byte is 1167612`). Exec output
     is buffered for reconnection and large binary output can be lost. **Use
     `sprite file pull -s brave-indigo-lion <remote> <local>`** (worked, byte-exact). The build
     never copies to a laptop, but anything scripted from outside should use `file pull/push`.

3. **Apify covers the chosen sources.**
   Pick three source types for the weekend. For each, name the Actor, run it once, and
   record cost per run and time to finish. Thirteen runs a day must be affordable.
   Result: **PASS with a changed call pattern.** Spike `spikes/check3_apify.py`. Spend $0.064.
   - **`run-sync-get-dataset-items` is refused by the connector** (403 `endpoint is not
     supported by the Apify connector`, no charge). The run-log endpoint is refused too.
     Working flow (matches the connector's snippet):
     `POST <gateway>/v2/actors/<user>~<actor>/runs?timeout=240&maxTotalChargeUsd=0.25`
     (body = Actor input) → 201 `{"data":{"id", "status", "defaultDatasetId", "options":{...}}}`;
     `GET /v2/actor-runs/<id>?waitForFinish=60` → `data.status`; `GET /v2/datasets/<id>/items?clean=1`
     → JSON array. `options` echoed `maxTotalChargeUsd: 0.25, isMaxTotalChargeUsdSetByUser: true`,
     so the cap passes through. `usageTotalUsd` and `chargedEventCounts` on the run object.

     | Source | Actor | Time | Items (last 2 h) | Charged | ≈ 13 runs/day |
     | --- | --- | --- | --- | --- | --- |
     | Hacker News | `constructive_calm~hacker-news-scraper` (topstories, comments depth 1) | 5.8 s | 7 stories, 43 comments | $0.049 (start fee charged 4×, $0.04) | ~$0.64 |
     | Reddit | `automation-lab~reddit-scraper` (r/LocalLLaMA new, 2 comments/post) | 9.7 s | 4 posts, 5 comments | $0.011 | ~$0.15 per subreddit |
     | RSS | `santamaria-automations~rss-feed-reader` | 3.2 s | 2 (hnrss.org) | $0.003 | ~$0.04 per feed set |

   - **Reddit `.rss` feeds fail through Apify: HTTP 404 (first attempt 429).** The RSS route
     works for real RSS (hnrss.org worked) but cannot replace the Reddit Actor.
   - Fields: HN items have `by, title, url, hnUrl, score, descendants, createdAt, text,
     comments[]`. Reddit posts have `author, title, selfText, url, permalink, score,
     numComments, upvoteRatio, createdAt, subreddit`. RSS items have `item_title,
     item_link, item_author, item_published, item_text`, no engagement.
   - Recommended weekend set: **Hacker News Actor, Reddit Actor, RSS Actor** (local news and
     newsletter feeds). Estimated ~$1/day at these volumes, so the $5 free credit lasts about
     4–5 days, enough for Sunday if volumes stay similar. The HN start fee dominates: fewer
     HN runs or a different HN Actor would cut it.
   - **Budget (decided Nov 26, Tarik):** Apify Starter plan on Friday. Core set RSS + HN +
     Reddit ≈ $1.67/day at 13 runs. Inferred, untested: start fees are charged once per GB of
     run memory (HN 4096 MB → 4×, RSS 128 MB → 1×, Reddit 512 MB → 1×), so `memory=1024` on
     the HN run should cut it to ~$0.25/day. Usage and limits endpoints are refused by the
     connector (403); check balance in the Apify console.
   - **Round 2 (16:23 UTC, $0.134):** Tarik asked about more sources, including Google News.
     RSS candidates were first fetched directly (free): 24 of 28 return dated items; failed:
     insideradio.com/rss (429), wuwm.com/rss (404), jsonline.com/rss (402, paywall),
     radiomilwaukee.org/feed (404). Bluesky handles checked via `public.api.bsky.app`
     `app.bsky.actor.getProfile`.

     | Source | Actor | Time | Items | Charged | ≈ 13 runs/day |
     | --- | --- | --- | --- | --- | --- |
     | Bluesky, 7 accounts (simonwillison.net, github.com, theverge.com, niemanlab.org, current.org, urbanmilwaukee.com, wisconsinexaminer.com) | `blueskyscraper~bluesky-posts-scraper` | 3.2 s | 24 posts (today) | $0.026 | ~$0.10 with `monitoringStoreName` dedupe |
     | Google News, query "artificial intelligence", last 2 h | `lhotanova~google-news-scraper` | 30.1 s | 10 | $0.058 (start charged 4×) | ~$0.75 per query |
     | RSS, 21 verified feeds + 3 Google News RSS searches | `santamaria-automations~rss-feed-reader` | 6.6 s | 59 (last 2 h) | $0.049 (24 feeds × $0.002) | ~$0.64 |

     - Bluesky items carry `text, url, handle, displayName, createdAt, likeCount, replyCount,
       quoteCount, externalLink, links, authorFollowersCount, isReply, isRepost`. Most
       accounts are outlets that also have RSS, so Bluesky mostly adds engagement counts and
       individual voices.
     - Google News items: `title, link` (**resolved publisher URL**), `source, sourceUrl,
       publishedAt, image, rssLink, loadedUrl`. A broad query returns low-quality outlets
       (first item: an opinion piece from goachronicle.com). Google News RSS through the RSS
       Actor is far cheaper but its links are `news.google.com/rss/articles/CBM...` redirects.
     - RSS is the cheapest per item and carries the primary sources. Feed list is in
       `spikes/check3_apify.py` (`rss_full`).

4. **The Sprite can run the heavy tools.**
   ffmpeg joins two clips and writes MP3 chapters. A headless browser renders one frame.
   Both within the Free plan's limits.
   Result: **PASS.** Spike `spikes/check4_heavy_tools.sh`, run 16:14 UTC.
   - `apt-get install ffmpeg`: 60 s → **ffmpeg 8.0.1-3ubuntu2**.
   - Two 24 kHz mono WAVs → concat demuxer + hand-written FFMETADATA (TIMEBASE=1/1000) +
     one-pass `loudnorm=I=-16:TP=-1.5:LRA=11` + `-ar 44100 -ac 1 -c:a libmp3lame -b:a 64k
     -id3v2_version 3` → **0.2 s**. `ffprobe -show_chapters`: chapter 0 = 0–3.000 s, chapter
     1 = 3.000–7.500 s, titles intact. File starts `ID3`, contains `CTOC` and 2 `CHAP` frames.
   - `uv pip install playwright` + `playwright install --with-deps chromium`: 26 s →
     **Playwright 1.65.2**; one 1080x1920 frame rendered in **1.6 s**.
   - Disk after: 1.5 GB used of 99 GB (Chromium cache 700 MB).
   - **Remotion for the vertical video: PASS** (Tarik approved the tool, Nov 26). Spike
     `spikes/check4b_remotion.sh`: `npx create-video@latest --yes --blank --no-tailwind`,
     `npx remotion add @remotion/media`, `npx remotion browser ensure`, then
     `npx remotion render Reel out/reel.mp4`. Remotion **4.0.547**. Scaffold + install 22 s,
     browser 5 s, **render of 45 s at 1080x1920, 30 fps (1,350 frames): 33.3 s.** Output
     H.264 + AAC, 45.01 s, 2.2 MB; audio is the check 2 Gemini WAV via `<Audio>` from
     `@remotion/media`. Disk 651 MB for the project. Captions used placeholder timing; real
     word timing (Deepgram) is untested. Sample: `spikes/output/check4b_reel.mp4`.
   - Remotion license: free for an individual, including commercial use, and for
     organizations of up to 3 people (remotion.dev/docs/license/faq). Fine for a personal
     entry; an entry made under an organization larger than 3 would need a Company License
     ("Automators" for scheduled renders).
   Sprite facts (`sprite exec`, Nov 26 15:57 UTC): Ubuntu 26.04.1 LTS,
   x86_64, 8 CPUs, ~15 GiB RAM reported, 99 GB free disk, sudo works. Installed: Python 3.13.17,
   pip 26.3, uv 0.13.7, Node 24.22.1, sqlite 3.46.1, Claude Code 2.1.319, Codex CLI 0.167.0,
   Gemini CLI 0.67.0. **Not installed: ffmpeg, ffprobe, any Chromium/Chrome, crontab.**
   Spike written: `spikes/check4_heavy_tools.sh` (apt ffmpeg; join two 24 kHz WAVs; loudnorm;
   mono MP3 with FFMETADATA chapters; verify CHAP/CTOC; Playwright 1.64 Chromium renders a
   1080x1920 frame).

5. **Something can wake the Sprite on the hour.**
   Find out whether a scheduled job inside a sleeping Sprite fires, or whether an outside
   trigger must call it. Also confirm the preinstalled coding agent can run headless.
   Result: **Partly answered.**
   - Docs: no scheduler in Sprites (RESEARCH-NOTES §4.1, §7.3).
   - Spike `spikes/check5_ticker.sh`: detached `nohup setsid` loop appending a timestamp
     every 30 s, started 15:58:18 UTC, then no commands sent. Read back at 16:00:54: **six
     lines, exactly 30 s apart, no gaps; process alive.** A background process kept the
     Sprite awake, which the docs' activity list doesn't mention. `sprite info` said `cold` at
     15:59:01, between two ticks, so the status field was wrong or stale at that moment.
     Implication: an in-Sprite timer can fire, but only by keeping the Sprite awake (billing).
     Full run: **30 ticks 15:58:18 → 16:12:48, no gap over 30 s** (one outside command at
     16:01:29). Loop stopped itself at 16:13:29. Cost of an always-awake idle Sprite not
     measured (usage API not yet read).
   - Coding agent: `claude` 2.1.319 installed, `bypassPermissions` preset in
     `~/.claude/settings.json`, **no credentials and no `ANTHROPIC_*` env set.** Headless use
     needs a credential. Spike written: `spikes/check5_station_manager.sh` (Anthropic
     connector + `ANTHROPIC_BASE_URL` = gateway, placeholder `ANTHROPIC_AUTH_TOKEN`, per
     code.claude.com/docs/en/llm-gateway-connect).
   - **Coding agent headless: PASS.** With the Anthropic connector, a raw
     `POST <gateway>/v1/messages` (no auth header) → 200. `ANTHROPIC_BASE_URL=<gateway base>`
     plus a placeholder `ANTHROPIC_AUTH_TOKEN`, then `claude -p "..." --model claude-haiku-5-5
     --output-format json` → `"result": "station manager online"`, `is_error: false`, 3.2 s,
     $0.0026. The gateway replaces the placeholder with the stored key.
   - Gateway listing from inside the Sprite (`GET /v1/gateway/list`): 57 providers available,
     including typesafe, gemini, ollama, apify, pinecone, box, tigris, deepgram, anthropic;
     **0 connections.** Listing entries carry only `provider`, `display_name`, `description`,
     `default_scopes`; no request examples until a connector exists.

6. **Backfill for Corrections.**
   Scrape posts from a week ago for one beat, score them with Jev today, and store the
   predictions. This gives real results to grade by Sunday.
   Result: **Scraped and scored; grading not done yet.** Spike `spikes/check6_backfill.py`, 16:20 UTC.
   - Apify HN Actor, `mode: "search"`, `searchQuery: "AI"` (required in search mode),
     `searchTags: ["story"]`, Nov 19 00:00–24:00 Central (`dateFromUnix`/`dateToUnix`),
     `minScore: 20`, `maxItems: 60` → **19 stories in 3.1 s, $0.0436.**
   - Jev, 5 questions per story (same-story skipped), 19 calls in 5.1 s, 12,824 input tokens
     (≈ $0.0005), all `jev-1.14.0`. Stored on the Sprite in `~/spikes/check6/backfill.db`:
     `posts` (id, source, beat, author, title, url, text, points, comments, created_at,
     scraped_at) and `decisions` (post_id, question_id, answer_type, value, probability,
     confidence, raw, model, asked_at), one row per answer.
   - **Calibration finding: `matter_week` ranged 0.32–0.62, median 0.40. No story reached
     0.70.** (Check 1's real release announcement scored 0.48.) At the spec's starting
     threshold nothing airs, and Corrections ("how the 70%+ calls turned out") has no calls
     to grade.
   - **`private_harm` median 0.17; 7 of 19 at or above 0.20.** The top three are real
     (0.86 an executive's spouse named in a smuggling case; 0.67 a named Air Force officer in
     solitary; 0.57 a user contacted by the FBI). The 0.20–0.33 band is generic tech
     discussion ("Ask HN: Where do you see Software in 5 years?" 0.33, "AI Overworks People"
     0.24). The 0.20 cut drops 37% of this sample.
   - `part`: 15 story, 3 none, 1 overheard, 0 lead. `new_or_reaction`: 12 new, 7 reaction.
   - Still to do: the follow-up scrape and the `still_discussed` question, which can run any
     time now, since the posts are already a week old.

## Not verified by research

Status after the Nov 26 spikes:
- Jev pricing: documented ($0.042 per million input tokens, output free). Rate limits still
  unknown; no rate-limit headers came back through the gateway.
- Gateway URL pattern with no Authorization header: **confirmed** for TypeSafe, Gemini,
  Anthropic and Apify. Each connector's `gateway_base_url` comes from `GET /v1/gateway/list`.
- Gemini TTS price: Google's page says free tier free, paid $9 per million audio tokens
  through Dec 31, 2026. Measured 422 audio tokens for 16.9 s (25/s).

Original notes:

- Jev pricing and rate limits on the connector.
- Whether the gateway URL pattern is `https://api.sprites.dev/v1/gateway/<provider>/<connection_id>/<path>`
  with no Authorization header. This came from a docs search snippet. Confirm on the
  connector's detail page.
- Gemini TTS price. A third-party summary says $9 per million audio tokens through
  Dec 31, 2026, at 25 tokens per second. Another says free through year end.

## Friday checks (during the build)

7. **Ollama Cloud through the gateway** (plan Task 8, step 1), Nov 26 17:4x UTC.
   - Connector snippet lists `POST <gateway>/api/chat`, `POST <gateway>/v1/chat/completions`,
     `GET <gateway>/api/tags`; example model `gpt-oss:120b`, `"stream": false`.
   - `POST /api/chat` with `{"model":"gemma4:31b","messages":[...],"stream":false,"think":false}` →
     **402 `{"error":"Add usage credits or subscribe and save up to 66%: https://ollama.com/plans"}`**.
     The gateway forwards correctly; the Ollama account has no credits. No free cloud usage.
   - After Tarik added credits: same request → **200 in 0.6 s**, `{"model":"gemma4:31b","message":{"role":"assistant","content":"..."},"done":true,"done_reason":"stop","total_duration":250502667,"prompt_eval_count":24,"eval_count":30}`. **PASS.**
