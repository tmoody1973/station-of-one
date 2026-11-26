# Station of One: handoff package

A personal agent on a Fly.io Sprite that reads your feeds and produces a five-minute
newscast at the top of every hour, a live front page, and a daily vertical video.
Entry for Fly.io Hacksgiving. Submissions close before midnight PST, Sunday Nov 29, 2026.

## What is in here

| Path | What it is |
| --- | --- |
| `CLAUDE.md` | Project rules for Claude Code. Read automatically. |
| `docs/SPEC.md` | The build spec: formats, requirements, pipeline, scope, schedule. |
| `docs/THURSDAY-CHECKS.md` | Five things to prove before writing the plan. |
| `docs/KICKOFF-PROMPT.md` | Prompts to paste into Claude Code, in order. |
| `docs/STATION-ID.md` | Call sign, show names and station ID lines. |
| `docs/LINKS.md` | Links to the full PRD and the mockup canvas. |
| `config/preferences.example.json` | Beats, sources, music taste, hours, thresholds. |
| `config/jev_questions.json` | The typed questions Jev answers, in a neutral format. |
| `mockups/` | Markup for the four screens, as layout reference. |

## How to start

1. Unzip into a new folder and run `git init`.
2. Open Claude Code in the folder.
3. Paste prompt 1 from `docs/KICKOFF-PROMPT.md` (the Thursday checks).
4. When the checks pass, paste prompt 2 (write the plan).

## The full PRD

`docs/SPEC.md` carries everything needed to build. The longer PRD, with the roadmap and
business notes, lives in the doc linked from `docs/LINKS.md`. To keep a copy in the repo,
use the doc's Export menu, choose Markdown, and save it as `docs/PRD.md`.
