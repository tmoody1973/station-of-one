# Research notes

Written Thu Nov 26, 2026, before any planning or code. Sources are current docs read today.
Fly's Sprites docs were read as raw Markdown from the index at https://docs.fly.io/llms.txt
(81 pages). Library and API facts come from Context7 where it had an entry, otherwise from
the vendor's own docs; each section says which.

Legend: **Confirmed** = stated in a doc linked beside it. **Inferred** = my reading of
several docs, not stated outright. **Not confirmed** = no doc found; a spike must prove it.

## Read this first

**Platform facts that change the plan**
1. **Nothing wakes a Sprite on a schedule.** An outside caller (GitHub Actions, Cloudflare
   cron, a Fly Machine) must hit the exec API on the hour (§4.1, §7.3).
2. **No connectors exist yet** in the org. All eight are added by hand in the dashboard, and
   gateway calls only work from inside the Sprite (§1, §3).
3. **The station manager needs a model credential** the spec doesn't list: Anthropic or Codex
   connector, and no doc shows the Claude CLI using the gateway (§4.2).
4. **Tigris has no index pages.** Every link must end in a filename (`/index.html`), including
   the address on the video end card. Public buckets need a card on file (§6.11).
5. **Gemini TTS changed shape:** speaker labels move out of the text into `speech_metadata`,
   output is WAV, max two prebuilt voices per call (§6.1–6.3, §6.6).
6. **Pinecone changed its API;** the connector documents the legacy paths (§6.9).

**Money (nothing bought yet)**
- Apify free credit ($5/month) runs out in 2–3 days at our rate; Starter is $19 (§6.8).
- Fly Free plan: $5/month, credit card required; our builds should fit (§7.1).
- Gemini TTS ≈ $0.07 per newscast on the paid tier, free tier exists. Jev < $0.10/day.
  Ollama < $0.001 per script. Deepgram covered by free credit. Lyria sting < $0.50 once.

**Your decisions**
- PRD vs spec: 16 differences in §5, all settled Nov 26 (spec wins; settings page is a must have).
- Apify: **decided Nov 26 (Tarik): Starter plan ($19) on Friday.** Free credit covers Thursday spikes. Measured costs in `THURSDAY-CHECKS.md` check 3.
- Hourly trigger: GitHub Actions or Cloudflare (§7.3).
- Voices: prebuilt first, designed later? (§6.2)
- Decided today: sting only, made once with Lyria (decision 001). Printful merch parked (§9).

---

## 1. What is on this machine (read-only checks)

| Check | Result |
| --- | --- |
| `fly version` | `fly v0.5.2 darwin/arm64`, built 2026-11-02 |
| `sprite --version` | `sprite version 2026-11-03 (4eb1509)`, at `~/.local/bin/sprite` |
| Sprites API endpoint | `https://api.sprites.dev` (selected), 1 org |
| Active org | `tarik-moody` (via fly.io login) |
| Sprites | One: `brave-indigo-lion` |
| `sprite info -s brave-indigo-lion` | ID and URL recorded locally (not published), created 2026-11-26 15:32 UTC, URL auth `sprite` (org-only), no labels shown |
| Checkpoints | `v1` "initial checkpoint", 2026-11-26 15:30 |
| Connectors (`GET /v1/oauth/connections`) | **None.** `{"connections":[]}` |

Nothing was created, changed or deleted. One side effect: `sprite checkpoint list` woke the
Sprite (status went from `cold` to `running`). It pauses again on its own after about 30
seconds idle. Any CLI call that touches the Sprite may wake it; that costs a few seconds of
compute, nothing more.

Not checked: the Ubuntu version and installed tools on the Sprite (needs `sprite exec`,
which I held for Thursday check 4). Docs disagree: [Working with Sprites](https://docs.fly.io/sprites/working-with-sprites.md)
says Ubuntu 25.10; [Sprite Maintenance](https://docs.fly.io/sprites/sprite-maintenance.md)
says new Sprites run 26.04.

---

## 2. Sprites platform: confirmed

### What a Sprite is and its limits
- Persistent, hardware-isolated Linux VM, billed by the second, free when idle.
  [Overview](https://docs.fly.io/sprites/index.md)
- Fixed 8 vCPUs, 100 GB storage (no autoscale), memory managed and autoscaled by the
  platform; no fixed RAM figure to design against.
  [Lifecycle](https://docs.fly.io/sprites/concepts/lifecycle.md)
- Preinstalled: Python, Node, Go, Ruby, Rust, Elixir, Java, Bun, Deno; Claude CLI, Gemini
  CLI, Codex, Cursor; git, curl, wget, vim. ffmpeg and a headless browser are **not** listed.
  [Working with Sprites](https://docs.fly.io/sprites/working-with-sprites.md)

### Sleeping and waking
- About 30 seconds after activity stops, the Sprite pauses. First **warm** (VM suspended,
  memory frozen, wake in 100–500 ms, processes resume), later **cold** (VM stopped, memory
  dropped, wake in 1–2 s, processes start fresh). You can't choose or see the transition.
  [Lifecycle](https://docs.fly.io/sprites/concepts/lifecycle.md)
- Activity = running exec/console commands, open TCP connections, TTY sessions, services
  with open connections. [Working with Sprites](https://docs.fly.io/sprites/working-with-sprites.md#idle-detection)
- Open TCP connections drop on any pause, warm or cold.
  [Keeping a Sprite Running](https://docs.fly.io/sprites/keeping-sprites-running.md)
- Disk persists (files, packages, SQLite). Memory and processes do not.
  [Lifecycle](https://docs.fly.io/sprites/concepts/lifecycle.md)
- The Sprite wakes on: a request to its URL, or a command sent to it (CLI or API).
  [Quickstart](https://docs.fly.io/sprites/quickstart.md)

### Keeping it awake during a build: the Tasks API
- A task is a hold. While at least one task is live the Sprite stays active. Max one hour
  per task; refresh with `PUT`. Socket: `/.sprite/api.sock`, virtual host `sprite`.
  `POST /v1/tasks {"name":"build","expire":"15m"}`, `PUT /v1/tasks/build`,
  `DELETE /v1/tasks/build`. Recommended heartbeat: 5-minute expiry refreshed every minute.
  [Keeping a Sprite Running](https://docs.fly.io/sprites/keeping-sprites-running.md)
- Inferred: a build started by `sprite exec` already counts as activity while it runs, so
  a task is a safety net (for example while waiting on a slow API call with no output),
  not a requirement. Cheap to add; the spike should test a full build without it first.

### Services
- `sprite-env services create <name> --cmd <bin> --args "a,b" [--http-port N] [--needs svc]`.
  Services start at boot, restart on crash and after a cold wake. They do **not** keep the
  Sprite awake. Only one service may own the HTTP port. Logs: `/.sprite/logs/services/<name>.log`.
  No systemd, no journalctl. [Services](https://docs.fly.io/sprites/concepts/services.md)

### Checkpoints
- `sprite checkpoint create --comment "..."` from outside, or `sprite-env checkpoints create`
  from inside. Copy-on-write, sequential IDs (`v1`, `v2`), last five mounted read-only at
  `/.sprite/checkpoints/`. Platform also takes hidden `auto-` checkpoints.
  Restore is asynchronous and destructive. [Checkpoints](https://docs.fly.io/sprites/concepts/checkpoints.md)
- **Docs disagree:** the Checkpoints page says creation "doesn't interrupt the Sprite";
  [Working with Sprites](https://docs.fly.io/sprites/working-with-sprites.md#checkpoints)
  says running processes stop during creation. Checkpoint only as the last step of a run
  until a spike shows which is true.

### URLs and networking
- URL: `https://<name>-<org-id>.sprites.app`, private (org members only) by default;
  `sprite config update --url-auth public` opens it. Routes to port 8080 or the service's
  `--http-port`. [Networking](https://docs.fly.io/sprites/concepts/networking.md)
- Egress unrestricted by default. An optional DNS allowlist ("network policy") can be set
  from outside only. [Networking](https://docs.fly.io/sprites/concepts/networking.md)

### Running a command from outside
- REST: `POST https://api.sprites.dev/v1/sprites/{name}/exec?cmd=<bin>&cmd=<arg>...`,
  bearer token, optional `env=K=V`, `dir=`, `stdin=true`. Non-TTY. Wakes the Sprite.
  [Execute Command](https://docs.fly.io/sprites/api/exec/execute-command.md)
- CLI: `sprite exec -s brave-indigo-lion -- <cmd>`. [CLI commands](https://docs.fly.io/sprites/cli/commands.md)
- `sprite auth setup --token` exists for CI use. [CLI Authentication](https://docs.fly.io/sprites/cli/authentication.md)

---

## 3. Connectors and the gateway: confirmed

From [Connectors](https://docs.fly.io/sprites/concepts/connectors.md) unless noted.

- Gateway URL: `https://api.sprites.dev/v1/gateway/<provider>/<connection_id>/<path>`.
  **No Authorization header.** The gateway identifies the calling Sprite from Fly's request
  signature, checks the access policy, and forwards `<path>` to the provider with the stored
  credential. This settles the open item in `THURSDAY-CHECKS.md`.
- Calls must come from inside a running Sprite. From a laptop or CI the gateway returns
  `401`. So every spike that calls a connector has to run on the Sprite.
- Access policy is deny-by-default (`403 connection denies all sprites by default`). Grant
  by name prefix, Sprite labels (all must match), or allow-all. Endpoint allow and block
  lists exist but are API-only; block wins.
- Each connector's detail page shows its exact gateway URL and an "API Usage" example. The
  [ecosystem page](https://fly.io/sprites/ecosystem/) tells you to run that example as the
  first test. This matches `CLAUDE.md`.
- `GET https://api.sprites.dev/v1/gateway/list` from inside a Sprite returns connected
  providers with `gateway_base_url` and `usage_snippet`. A coding agent in the Sprite gets a
  preinstalled `sprite-api-gateway` skill for this.
- Setup is manual in the dashboard: Fly.io dashboard → org → Sprites → Connectors → Add
  connector. Providers "can vary by organization during rollout."

### Per-connector facts from the ecosystem page panels

All from the detail panels on https://fly.io/sprites/ecosystem/ (read Nov 26).

| Connector | Credential | What the gateway forwards, and limits |
| --- | --- | --- |
| Apify | API key (BYOK) | Run Actors, read outputs. Starting runs spends Apify credits; use a scoped token. |
| TypeSafeAI (Jev) | API key from console.typesafe.ai | **Only `POST /v1/systemone` and `GET /v1/models`.** Jev answers yes/no, choice and score questions with probabilities and confidence. |
| Ollama Cloud | API key from ollama.com/settings/keys | Cloud models only. "Availability varies by organization during rollout." |
| Google Gemini | API key from AI Studio | Only generation, streaming, token counting, model listing, decision creation. **Request bodies ≤ 8 MB. Files API not forwarded.** Developer API only, no Vertex. |
| Pinecone | API key | Paths like `/indexes/<index>/query`, `/indexes/<index>/vectors/upsert`; gateway resolves the index host. Indexes can be created through the connector but only deleted in the Pinecone console. |
| Box | **OAuth** (Continue with Box) | Needs `root_readwrite` (whole account, not one folder). **Uploads ≤ 50 MiB, no chunked uploads. Downloads ≤ 64 MiB per response.** No delete or sharing changes. Refresh token expires after 60 days idle. |
| Tigris | Access key ID + secret | Listings, copies and bulk deletes need a connection with no endpoint restrictions. Requests may incur Tigris charges. |
| S3-compatible | Access key + secret | Listed; no detail panel found. |
| Deepgram | Project key | `POST /v1/listen` (prerecorded) and `POST /v1/speak`. **Body ≤ 8 MB, 120 s upstream timeout. Saving or testing the key runs a ~18 s paid transcription.** "Availability varies during rollout." |
| AssemblyAI | API key (community connector) | `POST /v2/upload`, `GET/POST /v2/transcript`, `GET /v2/transcript/:id` and subroutes. Direct uploads > 8 MB return 413; pass `audio_url` instead. Polling ≤ 60/min per transcript. |
| Anthropic | API key | Messages API (plus token counting, batches) and `/v1/models` only. |
| Codex | ChatGPT plan sign-in | For running Codex in a Sprite without a key on it. Rollout-limited. |
| Custom API | Token + base URL | Fallback for anything without a connector. Upstream must be public. |
| Pushover, Blotato | API key | Listed (optional and later in the PRD). |

The Meta connector is listed as "Muse Spark" only, which matches the PRD's decision not to
use it.

---

## 4. What the docs contradict or leave out in the PRD and spec

### 4.1 Nothing wakes a Sprite on a schedule (affects check 5)
Searched all 81 Sprites pages: no cron, timer or scheduled-wake feature. A cron daemon inside
the Sprite can't fire while the Sprite is paused (cold drops all processes; warm freezes the
whole VM). So the PRD's "a few minutes before the hour, the Sprite wakes" needs an **outside
caller** that runs `sprite exec` or hits the exec API (or the Sprite URL with a service
behind it) on the hour. Candidate callers are in section 7.3. Inferred,
but follows directly from the lifecycle docs.

### 4.2 The station manager needs a model credential the spec doesn't mention
`CLAUDE.md` says the preinstalled coding agent runs headless as station manager and source
scout. That CLI needs a model key, and keys may not live on the Sprite. Options the docs
show: the **Anthropic** connector (Messages API only) or the **Codex** connector (ChatGPT
plan). Whether the Claude CLI can be pointed at the gateway URL with no key on the Sprite is
**not documented anywhere I found.** This is a ninth connector, or a design question, and it
should be part of check 5.

### 4.3 ffmpeg and a headless browser are not listed as preinstalled
Both are needed (audio assembly, video). Expect to `apt install ffmpeg` and install a
browser (for example Playwright's Chromium). Disk persists, so it's a one-time install.
Check 4 confirms.

### 4.4 Sleep is automatic; there is no "let the Sprite sleep" command
Spec step 10 (`finish`: "checkpoint, let the Sprite sleep") just means exit cleanly and
release any task hold. The Sprite pauses about 30 seconds later.

### 4.5 Box grants whole-account access
The Box connector requires `root_readwrite`. Any Sprite allowed on that connector can write
anywhere in the Box account. Use a dedicated Box account or accept that.

### 4.6 Size limits shape the pipeline
- Gemini requests ≤ 8 MB: fine for text-to-speech prompts.
- Deepgram and AssemblyAI direct uploads ≤ 8 MB: a 45-second mono MP3 is well under that,
  but the full five-minute newscast at high bitrate might not be. Send the bucket URL instead.
- Box uploads ≤ 50 MiB: one newscast bundle (≈3 MB MP3 + JSON + HTML) fits; the daily video
  may need its own upload.

---

## 5. Where the PRD and the spec disagree

Listed for a decision. "Spec" = `docs/SPEC.md`, "PRD" = `docs/Station of One PRD.md`.
Where the mockups side with one, I say so.

| # | Topic | PRD says | Spec says | My read |
| --- | --- | --- | --- | --- |
| 1 | Jev question 3 options | Newscast, Feature, Overheard, none | lead, story, overheard, none (also `config/jev_questions.json`) | Spec. The newscast has no Feature. |
| 2 | Per-episode Jev question | "Of the top 20, which carries a four-minute Feature?" plus seconds per story | Seconds per story only | Spec. Feature belongs to the later daily show. |
| 3 | Which segment gets two voices | Pipeline step 6: "The Feature uses two speakers"; A4: the lead story | Lead story | Spec (and PRD A4). Step 6 is a leftover. |
| 4 | Short-newscast trigger | Rules: fewer than **four** stories clear; Show format: fewer than **three** | Fewer than three (config `min_stories: 3`) | Needs your call. |
| 5 | Threshold boundary | Airs if Q1 is **above** 70%; dropped if Q6 **above** 20% | **At or above** 0.70; dropped **at or above** 0.20 | Needs your call; matters only at exactly 0.70 / 0.20. |
| 6 | Speech recognition | Hourly pipeline step 8 ("Time the words") | Daily only, for the video | Spec. Saves 12 paid runs a day. |
| 7 | Video render | Hourly-ish pipeline step 10, headless browser | Daily `video` step, "from a code template" | Spec on timing; tool still open. |
| 8 | Source types for the weekend | "Three source types at most: subreddits, Hacker News, public accounts on one platform" | Beats table lists RSS, trade newsletters, local news RSS, Bandcamp, YouTube too | Needs your call; Thursday check 3 picks three. |
| 9 | Scrape window | "Each run pulls the last 24 hours" and "only what is new since the last one" | Only what is new since the last run | Spec (PRD contradicts itself). |
| 10 | Player and page extras | Playback speed, chapter list with highlight, transcript, share row (P2, P3, P7, P8) | Not in must-have; sticky player has play, ±15 s, time | Spec; mockup matches the spec. |
| 11 | Header | Show name, date **and** headline count (P1) | Show name and date; counts in their own module | Spec; mockup matches. |
| 12 | Control room page | Not in PRD scope list (only "decision log" on the page and in the demo) | Must have | Spec. |
| 13 | Settings page | Read-only page "still appears in the demo" | "Not in this build: … editable settings"; read-only page mentioned in §3 but not in the must-have list | Needs your call: build the read-only page or not. |
| 14 | Video caption file | V7: generate a caption file for posting | Not mentioned | Small; spec silent. |
| 15 | Notify step | Pipeline step 12 sends a link (Pushover optional) | No notify step | Spec. |
| 16 | Thumbs up/down feedback | S4: stored and fed to Jev | Not in build (`feedback: []` in config) | Spec. |

**Decided Nov 26 (Tarik):** spec wins on every row. #4: fewer than **three** stories → short
newscast. #5: **at or above** 0.70 airs, at or above 0.20 is dropped. #8: the three weekend
source types are picked in Thursday check 3 by cost and parse quality. #13: the read-only
settings page is a **must have** (added to `SPEC.md` §12).

The front-page mockup also shows The Table card and "On the turntable". Both are later
scope in both documents; they appear in the mockup only as layout reference.

---

## 6. API by API

### 6.1 Google Gemini text-to-speech (vendor docs, read Nov 26)

Source: [model page](https://aistudio.google.com/docs/models/gemini-3.8-flash-tts) (link from
Tarik) and the [speech-generation guide](https://aistudio.google.com/docs/speech-generation.md).
Google's own pages, not Context7. Model released September 2026.

**Confirmed**
- Model ID `gemini-3.8-flash-tts`. Sibling `gemini-3.8-flash-lite-tts` is cheaper and
  faster but has no free tier.
- `v1beta` API is required.
- Google's examples use the **Interactions API**: `POST https://generativelanguage.googleapis.com/v1beta/interactions`.
  `generateContent` is still referenced (format enum `AUDIO_L16`), but every full example
  in the guide uses `/interactions`.
- Text is a **verbatim transcript**. Speaker labels and delivery go in a `speech_metadata`
  annotation on each text item. Writing "Host: ..." in the text may be spoken aloud. Only
  momentary vocal tags go inline: `<breath>`, `<cough>`, `<laugh>`, `<sigh>`.
- Two-speaker request (copied from the guide, names changed only in this comment):

  ```json
  {
    "model": "gemini-3.8-flash-tts",
    "input": [{
      "type": "user_input",
      "content": [
        {"type": "text", "text": "How's it going today Jane?",
         "annotations": [{"type": "speech_metadata", "speaker": "Joe", "style": "cheerful and friendly"}]},
        {"type": "text", "text": "Not too bad, how about you?",
         "annotations": [{"type": "speech_metadata", "speaker": "Jane", "style": "calm and relaxed"}]}
      ]
    }],
    "response_format": {"type": "audio"},
    "generation_config": {"speech_config": {"speakers": [
      {"speaker": "Joe", "voice": "Puck"}, {"speaker": "Jane", "voice": "Kore"}]}}
  }
  ```
  Single speaker uses `"speech_config": [{"voice": "..."}]` (an array, not an object).
  Response audio is base64 at `output_audio.data`.
- Max **2 speakers** per call, prebuilt voices only. Every turn must name its speaker.
- Output: unary requests return a **complete WAV** (RIFF header, 24 kHz, mono, 16-bit).
  Write the bytes straight to `.wav`; do not add a header. `"mime_type": "audio/l16"` gives
  raw PCM. `sample_rate` can be set (24000 default).
- Limits: 8,192 input tokens, 16,384 output tokens per request.
- 30 prebuilt voices. Ones that fit "calm, dry, unhurried": Charon (informative),
  Schedar (even), Iapetus (clear), Kore (firm), Orus (firm), Rasalgethi (informative),
  Gacrux (mature). Also an extended library (`GET /v1beta/voices`) and voice design.
- Pricing, standard tier: **free tier free of charge**; paid tier $0.50 per 1M input text
  tokens and **$9.00 per 1M audio output tokens through Dec 31, 2026** ($0.00225 per 10 s
  of audio), doubling Jan 1, 2027. Two cheaper tiers at $4.50 (no free tier) and one at
  $16.20 are also listed; the page's tier labels did not survive my text extraction, so I
  read them as batch/flex and priority. **This settles the PRD's conflicting sources: both
  were right, for different tiers.** Five minutes ≈ $0.07 paid, as the PRD says.
- No word timestamps mentioned anywhere in the guide. The PRD's assumption (use speech
  recognition for captions) stands.

**Contradicts the PRD:** none on price. The PRD's model name "Gemini 3.8 Flash TTS" is
right; the request shape will differ from any older example (speaker labels move out of the
text; output is WAV, not raw PCM).

**Not confirmed**
- Whether the Sprites Gemini connector forwards `/v1beta/interactions`. Its panel lists
  "generation, streaming, token counting, model listing and decision creation." If it
  doesn't, fall back to `generateContent` (need its exact multi-speaker JSON for 3.8) or
  the Custom API connector. **Thursday check 2.**
- Free-tier rate limits for this model (not on the model page).

### 6.2 Gemini voice design (vendor docs, read Nov 26)

Source: [Voice design guide](https://aistudio.google.com/docs/voice-design.md) (link from Tarik).

**Confirmed**
- Describe a voice in 1–2 sentences; get a persistent `voice_...` ID. Works with both
  `gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`.
- Two ways to create one: the Voice Design studio in AI Studio
  (https://aistudio.google.com/generate-speech), which lets you audition and copy the ID, or
  `POST /v1beta/voices` with
  `{"store": true, "voice": {"model": "gemini-3.8-flash-tts", "type": "prompted", "display_name": "...", "gender": "...", "language_code": "en-US", "prompted": {"input": "<description>"}}}`.
  Response includes `sample_audio` (base64 WAV preview).
- Use it by passing the ID where a voice name goes:
  `"speech_config": [{"voice": "voice_..."}]`. The guide shows this on `/v1beta/interactions`
  only, and reads the audio from `.steps[] | select(.type=="model_output") | .content[] | select(.type=="audio") | .data`
  (the Python SDK exposes the same as `output_audio.data`).
- Guidance: fixed traits (age, timbre, accent) go in the design prompt; per-turn mood goes in
  `speech_metadata.style`, kept short.
- Limits: 200 stored voices per project, deleted after 1 year without use. List, get and
  delete via `GET/DELETE /v1beta/voices[/<id>]`.
- **A two-speaker call takes prebuilt voices only** ([speech guide, Limitations](https://aistudio.google.com/docs/speech-generation.md)).
  With designed voices, each speaker's turn is a separate call and the clips are joined.

**What this means for the build**
- Designed voices fit "original name, theme and sound" better than stock voices, and setup is
  a one-time step Tarik can do in the AI Studio UI, so the Sprite never needs `/v1beta/voices`.
- The cost: the lead story becomes several single-speaker calls joined by ffmpeg instead of
  one two-speaker call. The pipeline already joins per chapter, so this is a few more joins,
  not a new step.
- Voice replication (cloning a real recording) is out: `CLAUDE.md` forbids voicing a real
  person. Voice design from a description doesn't touch that rule.

**Not confirmed**
- Whether a `voice_...` ID works on `generateContent`, or only on `/interactions`.
- Whether the Sprites Gemini connector forwards `/v1beta/interactions` at all (same open
  item as 6.1). If it doesn't, designed voices need the Custom API connector.
- Whether a designed voice belongs to the Google Cloud project behind the API key. Inferred
  yes ("saved to your project"), so create it with the same key the connector holds.

### 6.3 Gemini: the gateway-safe request shape (generateContent)

Google now calls `generateContent` "legacy" but still supported
([llms.txt](https://aistudio.google.com/llms.txt)). It is plainly "generation", so it is the
endpoint most likely to pass the gateway. Context7 `/websites/ai_google_dev_gemini-api` matched
the vendor page. Source for the JSON:
[speech guide, generateContent view](https://aistudio.google.com/docs/speech-generation.md?generate-content=true).

`POST <gateway>/v1beta/models/gemini-3.8-flash-tts:generateContent`
```json
{
  "contents": [{"role": "user", "parts": [
    {"text": "How's it going today Jane?",
     "speech_metadata": {"speaker": "Joe", "style": "cheerful and friendly"}},
    {"text": "Not too bad, how about you?",
     "speech_metadata": {"speaker": "Jane", "style": "calm and relaxed"}}
  ]}],
  "generationConfig": {
    "responseModalities": ["AUDIO"],
    "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
      {"speaker": "Joe",  "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}},
      {"speaker": "Jane", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}
    ]}}
  }
}
```
- Mixed casing (`speech_metadata` snake case inside camelCase config) is as documented.
- Single speaker: `"speechConfig": {"voiceConfig": {"voice": "Kore"}}`.
- Audio: base64 at `candidates[0].content.parts[0].inlineData.data`, a full WAV by default.
  Raw PCM: `"generationConfig": {"responseFormat": {"audio": {"mimeType": "AUDIO_L16", "sampleRate": 24000}}}` (REST only).
- Response size: one minute of audio ≈ 3.8 MB of base64 JSON. The gateway's response limit is
  not documented. **Synthesize one chapter per call** (already the spec's plan), never the
  whole newscast in one call.

**Not confirmed:** the literal `inlineData.mimeType` string; rate limits per tier for this
model; whether a designed `voice_...` ID works here.

### 6.4 TypeSafe AI: Jev

Context7 `/typesafe-docs/typesafeai` matched the vendor docs. Vendor:
[System One API](https://docs.typesafe.ai/api/system-one.md) (OpenAPI also at
https://api.typesafe.ai/openapi.json), [Models](https://docs.typesafe.ai/models.md),
[Primitives](https://docs.typesafe.ai/primitives.md), [Noul](https://docs.typesafe.ai/primitives/noul.md),
[Score](https://docs.typesafe.ai/primitives/score.md), [State](https://docs.typesafe.ai/concepts/state.md),
[Errors](https://docs.typesafe.ai/api/errors.md).

**Confirmed**
- `POST https://api.typesafe.ai/v1/systemone`; through the gateway `<gateway>/v1/systemone`.
- Body: `{"model": "jev-latest", "state": <string|object|array>, "questions": {<id>: <question>}}`.
  Question types:
  - `noul`: yes/no. `{"type":"noul","instructions":"...","criteria":{"true":"...","false":"..."}}`.
    Answer: `{"type":"noul","noul":0.83}`, the probability of yes. **No `confidence` field.**
  - `choice`: 1–255 named options, `criteria` = `{name: description}`. Answer has `choice`,
    `confidence`, `probabilities` per option.
  - `score`: 1–10 ordered levels described in words. Answer `score` is a float 0…n-1 plus
    `confidence`, `legend`, `probabilities`.
- Response: `{"model": "jev-1.14.0", "answers": {...}, "usage": {"input_tokens", "output_tokens"}}`.
  `model` comes back versioned even when you send an alias. **Log it with every answer.**
- Any number of questions in one request; they all see the same `state` and don't see each
  other's answers. Question ids are not sent to the model, so all meaning goes in
  `instructions` and `criteria`. No separate batch endpoint; one call per post with all six
  questions is the intended pattern.
- `state` as an object is recommended; instructions can point at a field with a backticked
  path, e.g. `` `earlier_posts[2].text` ``.
- Models: `jev-1.14.0` (Oct 14, 2026), `jev-1.13.0`; aliases `jev-latest`, `jev-preview`.
  `GET /v1/models` lists only aliases.
- Limits: 64k tokens per request, 32k per question, 32 MiB body. Errors 400/401/413/415/422,
  429 (rate limit), 529 (overloaded); retry those two with backoff and `retry-after`.
- Price: **$0.042 per million input tokens; output free.** Six questions on a ~300-token post
  ≈ $0.00004 (estimate). 2,000 posts a day ≈ under $0.10.
- Docs' own starting thresholds for a Noul: ≥ 0.7 yes, ≤ 0.3 no, between = review.

**Mapping our questions** (`config/jev_questions.json`)

| Our id | Spec type | Real type |
| --- | --- | --- |
| `matter_week` | probability | `noul` → read `noul` |
| `new_or_reaction` | choice of 2 | `choice` with 2 options |
| `part` | choice of 4 | `choice` with 4 options (docs suggest a companion Noul if "none" is unreliable) |
| `primary_source` | yes/no + probability | `noul` |
| `same_story` | yes/no + probability | `noul`, one per candidate in the same request, each pointing at `` `earlier_posts[i]` `` |
| `private_harm` | yes/no + probability | `noul` |
| `seconds` (20–45) | score | `score` with up to 10 **described** levels; code maps 0…n-1 to 20–45 |

**Contradicts the spec or config**
- "Yes/no plus probability" is not two values; a Noul is one number. Code decides yes/no
  from the threshold, which is what the spec wants anyway.
- A 20–45 numeric answer isn't native. Levels must be described in words ("a brief mention",
  "a full story with context"…); the model never sees level numbers.
- There is no per-answer confidence on yes/no questions, so the control room can show the
  probability only.

**Not confirmed:** rate-limit numbers (console only); whether the gateway passes custom
headers such as `TypeSafe-Danger-Zone-Long-Context` (not needed under 64k); whether
`retry-after` survives the gateway.

### 6.5 Ollama Cloud

Context7 `/websites/ollama` matched the vendor docs. Vendor: [API intro](https://docs.ollama.com/api/introduction),
[Cloud](https://docs.ollama.com/cloud.md), [Cloud API](https://docs.ollama.com/cloud/api.md),
[Chat](https://docs.ollama.com/api/chat.md), [Cloud models](https://docs.ollama.com/cloud/models.md),
[Pricing](https://ollama.com/pricing). Live model list from `GET https://ollama.com/api/tags` (public).

**Confirmed**
- `POST <gateway>/api/chat` with `{"model": "...", "messages": [...], "stream": false, "think": false, "options": {"temperature": ..., "num_predict": ...}}`.
  **`stream` defaults to true; send false.** Text at `message.content`; tokens at
  `prompt_eval_count` / `eval_count`.
- Use the bare model name from `/api/tags` (`gemma4:31b`), not `:cloud`.
- **Cloud models don't support structured outputs** ([Cloud](https://docs.ollama.com/cloud.md)).
  Ask for plain text and check it in code.
- 25 models live today. Candidates for 150-word scripts: `gemma4:31b` ($0.14/$0.40 per 1M
  in/out), `mistral-large-4` ($0.70/$2.10), `glm-5.3-flash` ($0.15/$0.50),
  `deepseek-v4.1-flash` ($0.30/$1.20). Pick by ear on Friday; under $0.001 per script.
- Three model-retirement rounds happened in 2026; pin the name in config.
- Plans: pay-as-you-go (no subscription, 3 concurrent requests), Pro $20/mo (3), Max $100/mo
  (10). Over the limit, requests queue, then get rejected. No free allowance shown.
- OpenAI-compatible `/v1/chat/completions` exists.

**Contradicts the spec:** none. One design note: with 3 concurrent requests, write the six
chapters 3 at a time, not all at once.

**Not confirmed:** whether the gateway forwards `/v1/*`, `/api/usage`, `/api/balance`; the
status code when the queue is full; rate limits beyond concurrency.

### 6.6 Gemini TTS prompting rules that shape the `write` and `voice` steps

Source: Google's prompting guide, saved verbatim at `docs/reference/gemini-tts-prompting.md`
(pasted by Tarik; same text as the "Prompting guide" section of the
[speech guide](https://aistudio.google.com/docs/speech-generation.md)).

What the script writer (Ollama) must output:
- **Plain spoken words only.** No stage directions, speaker names or "(calmly)" in the text;
  they'd be read aloud.
- Pauses: punctuation, `--`, `...`, and `<short pause>` / `<long pause>` inline.
- Emphasis: CAPITALIZE the stressed word. Use sparingly; the show is calm and dry.
- Allowed inline tags are human sounds only (`<breath>`, `<sigh>`, `<throat-clearing>`…).
  For this show, at most `<breath>` and pause tags; no laughs (the tone rules say no jokes).
- The lead story's host/reporter exchange is written as separate turns, each tagged with its
  speaker. Backchannels like `|mm|` inside a turn are possible; skip them for a newscast.

What the voice step must send:
- **Voice carries identity; style stays short or empty.** Google says to test with an empty
  `style` first and, if needed, reuse **one short constant string** for every turn.
  **Correction (check 2b):** `"calm, dry, unhurried"` slowed delivery to ~110 wpm; "unhurried"
  is read as a pace instruction. With no style, Charon read at 167 wpm. Pick the style by ear. Don't add longer
  persona text: Google names long style blocks as the main cause of voice drift.
- Never put age, gender, name or accent in `style`; that belongs to the voice choice.
- Joining separately voiced turns: unary calls return WAV with a 44-byte header. Either
  request raw PCM (`AUDIO_L16` / `audio/l16`) or strip headers before joining; or let ffmpeg
  decode each WAV, which handles it.

Tension with the guide: it recommends writing in disfluencies ("uh", "hm") for naturalness.
A newscast is read copy, so the writer prompt should allow at most light hesitation in the
reporter's turns, none in the host's. That's a tone call for Friday listening, not a research
question.

### 6.7 Google Lyria (music generation), asked about for the sting

Source: [Music generation guide](https://aistudio.google.com/docs/music-generation.md) and
[Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing), read Nov 26. Vendor docs.

**Confirmed**
- `lyria-3-clip-preview`: always a **30-second** clip, MP3. `lyria-3.5`: full songs of "a
  couple of minutes" (length steered by prompt), MP3 or WAV. 44.1 kHz stereo.
- Endpoint: `POST /v1beta/interactions` with `{"model": "lyria-3-clip-preview", "input": "<prompt>"}`.
  Interactions API only in the examples.
- Prompts can say "Instrumental only, no vocals" and give timestamped structure
  (`[0:00 - 0:10] Intro: ...`).
- **No free tier.** Paid: $0.04 per 30 s clip, $0.08 per full song.
- Every output carries an inaudible **SynthID** watermark. Prompts naming specific artists
  or copyrighted lyrics are blocked. Results vary call to call; no editing of a result.

**Fit with the spec**
- Spec §6 already requires "a short original sting at open and close. No licensed music."
  Generated audio is not licensed music, so a Lyria-made sting fits that rule.
- A sting is a **one-time asset**, not an hourly step: generate a handful of 30 s clips,
  pick one, trim a 3–5 s open and close with ffmpeg, commit the file. The hourly build never
  calls Lyria, so the open question about the gateway forwarding `/interactions` doesn't
  matter here.
- "Music segues" between stories are **not in the spec**. Adding them is a scope change, and
  each one eats into the 5:00 runtime.

**Not confirmed**
- Google's terms on who owns Lyria output and whether it may be used in a public podcast
  feed. I did not open the Gemini API terms. Read them before the feed goes public.
- Whether Spotify or other directories treat SynthID-marked music differently.

**Decided Nov 26 (Tarik):** sting only, made once with Lyria and committed. No segues. Spec
unchanged. See `docs/decisions/001-sting-from-lyria.md`.

### 6.8 Apify

Context7 `/websites/apify_api_v2` and `/apify/apify-client-python`, plus vendor docs:
[run-sync-get-dataset-items](https://docs.apify.com/api/v2/actor-run-sync-get-dataset-items-post.md),
[runs](https://docs.apify.com/api/v2/actors-runs-post.md), [run get](https://docs.apify.com/api/v2/actor-run-get.md),
[dataset items](https://docs.apify.com/api/v2/dataset-items-get.md), [API overview](https://docs.apify.com/api/v2.md),
[pricing](https://apify.com/pricing.md), [subscriptions](https://docs.apify.com/account/subscriptions.md).
Actor facts come from the public Store metadata API (`GET https://api.apify.com/v2/actors/<id>`,
no key), read Nov 26. Nothing was run.

**Confirmed**
- Path is `/v2/actors/<user>~<name>/...` (clients and docs both use `actors`, not `acts`).
- One-call scrape: `POST <gateway>/v2/actors/<id>/run-sync-get-dataset-items?timeout=240&maxTotalChargeUsd=0.50&clean=1`
  with the Actor input as the JSON body. `201` returns the items array. **Over 300 s → `408`**;
  `402` = out of credit. Set the HTTP client timeout above 300 s.
- Async fallback: `POST /v2/actors/<id>/runs` → `GET /v2/actor-runs/<runId>?waitForFinish=60`
  (60 s max per poll) → `GET /v2/datasets/<defaultDatasetId>/items?clean=1`.
- `maxTotalChargeUsd` caps spend per run. **Send it on every run.**
- Python client accepts `api_url` and no token, but plain HTTP is simpler through the gateway.
- **Free plan: $5 of usage per month; when it runs out the account stops until next cycle.**
  Starter: $19/month with $19 of usage.

**Actor picks** (all pay-per-event, no login or cookies, prices are free-tier, 13 runs a day)

| Source | Actor | Price | "Only new" input | Reliability, 30 days | Est. per day |
| --- | --- | --- | --- | --- | --- |
| Hacker News | `constructive_calm~hacker-news-scraper` | $0.01/run + $0.0004/story + $0.00015/comment | `dateFromUnix` | 213/215 runs OK | ~$0.41 |
| Reddit | `automation-lab~reddit-scraper` | $0.003/run + $0.00115/post + $0.00075/comment | `postedAfter: "2 hours"` (set `includeNsfw: false`; default is true) | 167,587/169,518 | ~$0.50–1.14 |
| RSS/Atom | `santamaria-automations~rss-feed-reader` | $0.001/run + **$0.002 per feed** (not per item) | `filterByDate` | 53,349/54,558 | ~$0.27 for 10 feeds |
| Bluesky | `blueskyscraper~bluesky-posts-scraper` | $0.0011/post | `monitoringStoreName` returns only posts not delivered before | 169/169 (23 users) | ~$0.29 |
| Bandcamp tags | `jungle_synthesizer~bandcamp-discover-new-release-scraper` | $0.0005/record | **none**; dedupe by URL | 14/14 (2 users) | ~$0.16–0.65 |
| YouTube | `streamers~youtube-channel-scraper` | $0.0013/video | `oldestPostDate: "1 day"` | 1.7M runs, 99%+ | ~$0.17 |

- Avoid `trudax~reddit-scraper-lite`: 958,834 of 1,106,349 runs failed in 30 days.
- **Budget:** all six with "only new" filters ≈ $1.8/day (estimate), so the free $5 lasts about
  2–3 days. **The demo through Sunday likely needs the $19 Starter plan.** Your call; nothing is
  bought.
- **Cheaper path worth testing Thursday:** the RSS Actor bills per feed, and Hacker News
  (hnrss.org), Reddit (`/r/<sub>/.rss`) and YouTube channels all publish RSS. One Actor could
  cover three source types for cents a day, with less terms-of-use risk than scraping Reddit
  directly. Not confirmed that those feeds parse well; check 3 can settle it. RSS loses
  engagement counts (scores, comment counts), which the spec says to store.
- Terms of use: Reddit and Bandcamp are the risky ones (background knowledge, not read today).

**Contradicts the spec or PRD:** none directly. PRD target of 1,500–3,000 posts a day pushes
Reddit/Bluesky item costs up; the estimates above assume ~100 items per source per run.

**Not confirmed:** whether a run keeps billing after a `408`; the old `/v2/acts/` alias; Reddit
comment sort order; how the RSS Actor handles hnrss, Reddit `.rss` and YouTube feeds.

### 6.9 Pinecone

Context7 `/websites/pinecone_io` and `/pinecone-io/python-sdk`, plus vendor docs:
[versioning](https://docs.pinecone.io/reference/api/versioning.md),
[Documents API](https://docs.pinecone.io/guides/get-started/documents-api.md),
[move to Documents API](https://docs.pinecone.io/guides/indexes/move-to-the-documents-api.md),
[integrated embedding](https://docs.pinecone.io/guides/search/integrated-embedding.md),
[upsert documents](https://docs.pinecone.io/reference/api/2026-07/data-plane/upsert_documents.md),
[search documents](https://docs.pinecone.io/reference/api/2026-07/data-plane/search_documents.md),
[embed](https://docs.pinecone.io/reference/api/2026-07/inference/generate-vectors.md),
[legacy upsert vectors](https://docs.pinecone.io/guides/legacy/vectors-api/upsert-vectors.md),
[legacy query](https://docs.pinecone.io/guides/legacy/vectors-api/query-vectors.md),
[limits](https://docs.pinecone.io/reference/api/database-limits/object-limits.md).

**Confirmed**
- **Pinecone's API changed.** Current version header `X-Pinecone-Api-Version: 2026-07`
  introduces a **Documents API** (schema-defined index, text in, built-in embedding, full-text
  search too). The older Records and Vectors APIs are now "legacy" but still work. Without the
  header, requests default to the *oldest* supported version, so **always send it.**
- The connector's documented example paths (`/indexes/<name>/query`,
  `/indexes/<name>/vectors/upsert`) are the **legacy Vectors API**.
- Two workable routes:
  - **A. Documents API (current).** `POST /namespaces/<ns>/documents/upsert` with
    `{"documents": [{"_id": "...", "text": "..."}]}` (max 96 per request; JSON, not NDJSON), then
    `POST /namespaces/<ns>/documents/search` with
    `{"top_k": 5, "score_by": [{"type": "embed", "fields": ["text"], "query": "..."}]}` →
    `matches[]._score`. Indexing is asynchronous (docs wait ~10 s before searching).
  - **C. Legacy vectors + `/embed`.** `POST /embed` (`{"model": "multilingual-e5-large", "parameters": {"input_type": "passage"}, "inputs": [{"text": "..."}]}`),
    then `/vectors/upsert` and `/query` (`{"vector": [...], "topK": 5, "includeMetadata": true}` →
    `matches[].score`). Two calls per write; creating the index over REST needs header
    `2026-04`, because 2026-07 rejects a dimension/metric body.
- **Starter (free) plan:** 5 indexes (AWS us-east-1 only), 2 GB storage, 1M read units and 2M
  write units a month, **5M embedding tokens a month per model**, 1 GB egress (then reads are
  blocked until next month), $0.
- Budget: ~78k items a month at ~64 tokens each ≈ 5M tokens, right at the free cap. **Embed
  only items that pass a cheap exact-URL check in SQLite first, and embed title plus summary,
  not full text.** At hackathon length (4 days) this is far under the cap.
- Indexes can be created through the connector but only deleted in the Pinecone console.

**Recommendation for check 3/dedupe spike:** try route A through the gateway (one upsert, one
search). If the gateway rejects `/documents/*` paths, use route C, which matches the paths
the connector page documents.

**Contradicts the spec:** none. The spec's fallback (link matching) stays the cut-order
fallback.

**Not confirmed:** gateway forwarding of `/namespaces/<ns>/documents/*`; whether the gateway
passes or overrides `X-Pinecone-Api-Version`; the exact 2026-04 create-index body; the inner
field name in `/embed` responses (`values` assumed); `GET /indexes/<name>` through the gateway
to read `status.ready`.

### 6.10 Box

Context7 `/websites/developer_box_reference`, vendor pages
[upload file](https://developer.box.com/reference/post-files-content),
[upload version](https://developer.box.com/reference/post-files-id-content),
[create folder](https://developer.box.com/reference/post-folders).

**Confirmed**
- New file: `POST https://upload.box.com/api/2.0/files/content`, multipart, **`attributes`
  part first** (`{"name": "...", "parent": {"id": "<folder>"}}`), then `file`. Otherwise
  `400 metadata_after_file_contents`. `201`; new ID at `entries[0].id`.
- New version: `POST https://upload.box.com/api/2.0/files/<id>/content`, `200`.
- Folder: `POST https://api.box.com/2.0/folders` with `{"name": "...", "parent": {"id": "0"}}`.
  `201`; ID at top-level `id` (not `entries`). `409` if the name exists (case-insensitive); on
  409, list the parent's items and match by name. Root folder is `"0"`.
- Through the gateway: no deletes, no sharing changes, uploads ≤ 50 MiB, no chunked uploads.

**Not confirmed: how the gateway reaches `upload.box.com`.** Uploads live on a different host
than the rest of the API, and no public doc says how the gateway routes them. Two other
hackathon repos on GitHub hit the same question and point to the connector's API Usage panel.
Check 1-style spike: read Box's `usage_snippet` from `GET /v1/gateway/list`, upload a 1 KB file.

### 6.11 Tigris (public hosting)

Vendor docs: [llms.txt](https://www.tigrisdata.com/docs/llms.txt),
[public buckets](https://www.tigrisdata.com/docs/buckets/public-bucket.md),
[S3 API support](https://www.tigrisdata.com/docs/api/s3.md),
[caching](https://www.tigrisdata.com/docs/objects/caching.md),
[custom domains](https://www.tigrisdata.com/docs/buckets/custom-domain.md),
[pricing](https://www.tigrisdata.com/pricing/), [Fly setup](https://www.tigrisdata.com/docs/sdks/fly.md).

**Confirmed**
- S3-compatible; API endpoint `https://t3.storage.dev` (`region=auto`, virtual-host style).
- **Public URL: `https://<bucket>.t3.tigrisfiles.io/<key>`** (also `.t3.tigrisbucket.io`,
  `.t3.tigrisblob.io`). `t3.storage.dev` does not serve public objects. The older
  `<bucket>.fly.storage.tigris.dev` form isn't in current docs; don't use it.
- Make a bucket public: `fly storage create --public` or `fly storage update <bucket> --public`,
  or `--acl public-read`. Only canned ACLs (`public-read`, `private`).
- **No static-website mode.** No index document; `/` returns a listing or 403, `/2026-11-28/`
  returns 404. **Every link must name the file**: `/index.html`, `/2026-11-28/0900/index.html`.
  This is a real constraint on page templates and on the address we put on the video end card.
- Set `Content-Type` on every upload (`text/html`, `audio/mpeg`, `application/rss+xml`,
  `application/json`, `video/mp4`). **HTML, JSON and RSS get no default cache header**; set
  `Cache-Control: max-age=60` on hourly files. Audio and images default to one hour.
- No dots in bucket names (TLS fails). Custom domain = CNAME to `<bucket>.t3.tigrisbucket.io`,
  DNS-only (no Cloudflare proxy).
- Free tier: 5 GB, 10k writes, 100k reads a month. Our ~7k writes a month fit.
- **Public buckets need a verified payment method** for orgs created after May 18, 2026, even
  though the pricing page says "no card to start".

**Not confirmed:** how the gateway signs S3 requests (does our code send an unsigned
`PUT <gateway>/<bucket>/<key>`?), and whether `Content-Type`, `Cache-Control` and `x-amz-acl`
pass through. Spike: read Tigris's `usage_snippet`, PUT one file, then `curl -I` the public URL.

### 6.12 ffmpeg: join, loudness, chapters

Context7 `/websites/ffmpeg_ffmpeg-all`, the [ffmpeg docs](https://ffmpeg.org/ffmpeg-all.html),
FFmpeg source on GitHub, [Apple's audio requirements](https://podcasters.apple.com/support/893-audio-requirements).

**Confirmed**
- Chapters file (`;FFMETADATA1`), one block per chapter:
  ```ini
  [CHAPTER]
  TIMEBASE=1/1000
  START=0
  END=10000
  title=Open
  ```
  **Without `TIMEBASE`, times are read as nanoseconds.** Escape `= ; # \` with a backslash.
- The MP3 muxer writes ID3v2 `CTOC` and `CHAP` frames whenever the output has chapters
  (confirmed in FFmpeg source, `libavformat/id3v2/writer.c`, `mp3enc.c`). Use
  `-id3v2_version 3` (widest player support; common practice, not an ffmpeg claim).
- Join: concat demuxer (`ffconcat version 1.0` list, `-f concat -safe 0 -i list.txt`). All
  inputs must share sample rate and channels; Gemini output is uniform 24 kHz mono.
- **Don't use `chapter_per_file`:** added to FFmpeg 2026-09-20, not in the ffmpeg 8.0.1 that
  Ubuntu 26.04 ships. Compute chapter times from `ffprobe` durations and write the file.
- Loudness: Apple asks for −16 LKFS ±1 and true peak ≤ −1 dBFS. Use
  `loudnorm=I=-16:TP=-1.5:LRA=11`. Two-pass (measure, then apply `measured_*` values with
  `linear=true`) or one-pass for speech. **Always pass `-ar 44100`**, or loudnorm upsamples to
  192 kHz.
- Final encode: `-ar 44100 -ac 1 -c:a libmp3lame -b:a 64k -id3v2_version 3`, about 0.5 MB a
  minute, so a five-minute newscast ≈ 2.4 MB. Fits Box (50 MiB) and the speech-to-text 8 MB cap.
- Raw PCM input needs `-f s16le -ar 24000 -ac 1` (default would be 44.1 kHz → voice 1.84× fast).
  Since Gemini now returns WAV, check the first four bytes for `RIFF` before treating anything
  as raw.
- Verify with `ffprobe -show_chapters newscast.mp3`.

**Not confirmed:** ffmpeg is installed on the Sprite (check 4).

### 6.13 Speech-to-text for video captions: Deepgram

Deepgram docs: [pre-recorded](https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded),
[errors](https://developers.deepgram.com/docs/errors), [pricing](https://deepgram.com/pricing).
AssemblyAI docs: [transcribe a file](https://www.assemblyai.com/docs/pre-recorded-audio/getting-started/transcribe-an-audio-file),
[pricing](https://www.assemblyai.com/pricing).

**Recommendation: Deepgram.** One synchronous call, no polling; Fly maintains the connector
(AssemblyAI's is community-built); a 45-second clip is ~0.4 MB as MP3, far under the 8 MB cap.

- `POST <gateway>/v1/listen?model=nova-3&smart_format=true` with the audio as the body
  (`Content-Type: audio/mpeg`), or JSON `{"url": "<public bucket URL>"}` with
  `Content-Type: application/json` (missing it → `400`).
- Words at `results.channels[0].alternatives[0].words[]` = `{word, start, end, confidence, punctuated_word}`,
  **times in seconds**. (AssemblyAI returns milliseconds; normalize in one place if it's ever a fallback.)
- $200 free credit, no card. Each connector key save or test runs a ~18 s paid transcription.
- AssemblyAI model IDs disagree across Fly, its docs and its pricing page; another reason to
  prefer Deepgram.

**Not confirmed:** Deepgram's exact pre-recorded price (below the $0.0048/min streaming rate).

## 7. Platform money, rules and the hourly trigger

### 7.1 Fly plan and Sprite cost
Source: [Fly pricing](https://fly.io/pricing/) (`sprites.dev/pricing` redirects there).
- **Free plan: $5 of usage a month, up to 3 Machines and 3 Sprites, credit card required.**
  Past $5 it moves to pay-as-you-go automatically.
- Sprites, billed only while awake: $0.0385 per CPU-hour, $0.021875 per GB-hour of memory,
  hot storage $0.50/GB-month while awake, cold storage $0.02/GB-month.
- Rough estimate (Researcher C's arithmetic): 13–24 builds a day at ~3 minutes ≈ $2–3 a month
  of compute. Fits the $5 only if builds stay short. Watch the
  [usage API](https://docs.fly.io/sprites/api/usage/read-organization-usage.md).
- The hackathon page says "Your hackathon compute is on us with Fly's new Free plan."
- Connector limits on the Free plan: not published.

### 7.2 Hacksgiving rules
Source: https://fly.io/hacksgiving/ (and `/hacksgiving.md`), read Nov 26.
- "Your project must be an agent that runs on Fly.io Sprites using at least one connector."
  Built during the week (Nov 23–29). One entry per developer. Any AI tools allowed.
- Submit by **midnight PST, Sun Nov 29** through the Google Form linked on the page: code link,
  demo, "a sentence or two" of description.
- Post a short demo on X, Bluesky, LinkedIn or Reddit tagging @flydotio. "Video demos always earn
  'bonus points,' but won't actually affect your score."
- Prizes: $2,500, $1,500, and the $1,000 Weird Uncle Award ("the strangest agent anyone builds").
- **No judging criteria are published.** Winners announced by email Tue Dec 1.
- Matches the spec's submission checklist. One small difference: the spec says "two-sentence
  description"; the page says "a sentence or two". No conflict.

### 7.3 The hourly trigger (answers check 5 on paper)
Sources: [exec API](https://docs.fly.io/sprites/api/exec/execute-command.md),
[GitHub schedule events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[Fly task scheduling](https://docs.fly.io/blueprints/task-scheduling),
[Cloudflare Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/).

No Sprites scheduler exists (section 4.1). Something outside calls
`POST https://api.sprites.dev/v1/sprites/brave-indigo-lion/exec?cmd=...` with a Sprites token
(made at sprites.dev/account). The token lives in that scheduler's secret store, never in the
Sprite or the repo.

| Option | Fires when | Catch |
| --- | --- | --- |
| GitHub Actions cron | e.g. `50 * * * *` | GitHub says runs "can be delayed… High load times include the start of every hour… some queued jobs may be dropped." A :50 start for a :00 air is near the busy window. |
| Fly Machine `--schedule hourly` | Whatever minute the Machine was created | "Not for precise timing." Uses one of the Free plan's 3 Machines. |
| Cloudflare Workers Cron Trigger | Exact minute you set, UTC | Another account; config changes take up to 15 min. |
| cron-job.org / Upstash QStash | Minute you set | Third party holds the Sprites token. |

My read: GitHub Actions is the least new setup (the repo will be on GitHub anyway) and the
spec already allows a hand trigger for the demo recording. Starting the build at :48–:50
gives the 10-minute budget. If GitHub's delays show up Saturday, switch to Cloudflare. Your call.

**Not confirmed:** whether `POST /exec` keeps the command running if the scheduler's HTTP
connection drops. Protect the build with a Tasks API hold (section 2) regardless.

## 8. Open items, mapped to the Thursday check that settles them

| Open item | Check |
| --- | --- |
| Gateway forwards Jev `POST /v1/systemone`; real rate limits | 1 |
| Gateway forwards Gemini `/v1beta/interactions`, or only `generateContent`; response-size limit; designed `voice_...` IDs on `generateContent` | 2 |
| Apify Actors for three chosen source types; cost per run; RSS Actor parsing hnrss / Reddit `.rss` / YouTube feeds | 3 |
| Pinecone Documents API through the gateway vs legacy vectors; version header pass-through | 3 (dedupe) or a short extra spike |
| ffmpeg and a headless browser installed and within limits; Ubuntu version; checkpoint interrupts processes or not | 4 |
| Outside trigger choice; exec survives disconnect; Claude CLI as station manager without a key on the Sprite (Anthropic or Codex connector) | 5 |
| Box upload routing to `upload.box.com` | new: add to check 1 or 4 |
| Tigris signing through the gateway; headers pass through; public URL works | new: add to check 4 |
| Deepgram through the gateway | Sunday, with the video |
| Lyria output terms for a public feed | before the RSS feed goes public |

Items in `THURSDAY-CHECKS.md` "Not verified by research" now settled by docs: the gateway URL
pattern with no Authorization header (section 3) and Gemini TTS price (section 6.1). Jev
pricing is now documented ($0.042 per million input tokens); Jev rate limits still aren't.
I did not edit `THURSDAY-CHECKS.md`; that file is for spike results.

## 9. Parked ideas (raised Nov 26, not in scope)

- **Printful merch (tote bags).** Tarik's idea: let people order station merch. Parked because
  the spec excludes payments, there is no Printful Sprites connector (would need Custom API),
  and the call signs haven't been checked with the FCC. Revisit after the hackathon.
  - What the API offers ([Printful API](https://www.printful.com/api),
    [docs](https://developers.printful.com/docs/), skimmed Nov 26): REST/JSON; private tokens
    with scopes and expiry, or OAuth for public apps; Catalog, Products, Orders (create draft,
    confirm for fulfillment, estimate costs), File Library, Shipping Rate, Tax Rate APIs; mockup
    generation. Postman collection available.
  - Inferred, not confirmed: API orders are billed to the station's Printful account, so
    selling to the public needs our own checkout (payments) or Printful's storefront
    integrations (Shopify, Etsy and similar) with a plain link from the page. The link-only
    route needs no code in this repo.

