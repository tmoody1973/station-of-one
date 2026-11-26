# Station of One

Hackathon build. Deadline: Sunday Nov 29, 2026, before midnight PST. One developer.
Read `docs/SPEC.md` before planning or coding. It is the source of truth for scope.

## Ground rules

- Scope is fixed by `docs/SPEC.md`. Do not add features. If something looks missing, ask.
- Follow the cut order in the spec when time is short. Audio and front page come first.
- The design is settled. Do not re-open product decisions; raise only blockers.
- Nothing in `docs/THURSDAY-CHECKS.md` is verified yet. Treat every item there as unknown
  until a spike proves it, and record the result in that file.

## Architecture decisions already made

- Runs on one Fly.io Sprite. Public files (audio, pages, video, feed) go to an object
  bucket so they load while the Sprite sleeps.
- No agent framework. The hourly build is a plain pipeline of scripts, one module per step.
- The coding agent preinstalled on the Sprite is used headless for two jobs only:
  station manager (repair a failed step) and source scout (propose sources daily).
- Python. SQLite on the Sprite for posts, decisions and predictions. Static HTML from
  templates. ffmpeg for audio. No CMS, no web framework, no always-on server.
- One JSON data file per newscast. Shape the data like these future collections:
  newscasts, stories, sources, beats, music_picks, corrections, debates.

## Connectors

All external calls go through the Sprites connector gateway. Never put an API key in the
Sprite, in code, in config, or in the repo. Each connector's dashboard page has an
"API Usage" example; use that as the reference for request shape, not memory.

| Connector | Job |
| --- | --- |
| Apify | Scrapes every source |
| TypeSafe AI (Jev) | Every editorial decision: typed answers with probabilities |
| Ollama Cloud | Writes scripts |
| Google Gemini | Voices (two-speaker TTS) |
| Pinecone | Duplicate detection, memory of what aired |
| Box | Archive of each newscast bundle and decision log |
| Tigris or S3 bucket | Public hosting |
| Deepgram or AssemblyAI | Word timestamps for video captions |
| Anthropic | Station manager and source scout (headless Claude CLI through the gateway) |

## Editorial rules that are enforced in code

- Jev decides; code applies thresholds. A language model never chooses what airs.
- Scripts are written only from posts that passed selection.
- Every claim is attributed to where it was posted. Scraped claims are never stated as fact.
- Summaries are in the show's own words. At most one short quoted line per story, author named.
- Posts likely to harm a private individual are dropped and never shown.
- Public sources only in this build. No inbox, calendar or logged-in feeds.
- No licensed music in audio, feed or video. Music appears only as official embeds on the page.
- The page and feed state that voices are synthetic and the show is machine-edited.
- No real station's name, call letters, theme or look. Do not copy any real outlet's design.
- The Table: low-stakes topics only. Elections, contested policy, religion and health are
  excluded. Never voice or impersonate a real person.

## Working style

- Small steps, each runnable by hand: every pipeline step has a CLI entry point that
  reads and writes files, so it can be tested alone.
- Log every Jev answer with its probability. The log feeds the page, video and Corrections.
- Keep a run log per build (step, tool, counts, seconds, status). The control room page reads it.
- Prefer a working plain version over a polished partial one.
