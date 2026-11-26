# Kickoff prompts for Claude Code

Paste these in order. The product design is already decided, so skip open-ended
brainstorming and go from reading, to checks, to a written plan.

Assumed layout (adjust the file names in the prompts if yours differ):

- `docs/PRD.md`: the full PRD, exported from the doc as Markdown
- `docs/SPEC.md`: the condensed build spec
- `mockups/`: the four screens as HTML and as PNG images
- Fly.io CLI already installed and logged in on this machine

## Prompt 0: read everything and research the platform

```
Before any planning or code, get oriented. Do these in order and do not skip any.

1. Read CLAUDE.md, then every file in docs/. The PRD is the Markdown file in docs/
   (docs/PRD.md, or whichever PRD file is there). docs/SPEC.md is the condensed build
   spec. If the PRD and the spec disagree, list the differences and ask me which wins.

2. Look at every mockup in mockups/. Open the PNG images to see the intended layout,
   and read the HTML files for structure, copy and exact colors. The .dc.html files use
   a design-canvas runtime and will not render on their own; treat them as reference
   markup. The four screens are the front page, the control room, onboarding and settings.

3. Research the platform from current documentation, not from memory:
   - Read Fly.io's Sprites documentation: what a Sprite is, creating and exec'ing into
     one, sleeping and waking, checkpoints and restore, services and public URLs,
     scheduled work, network policy, limits on the Free plan, and the Sprites CLI and API.
   - Read the Sprites connectors documentation and the ecosystem page: how the gateway
     works, how access policies are set, and the exact request shape for each connector
     we use (Apify, TypeSafe AI, Ollama Cloud, Google Gemini, Pinecone, Box, Tigris or
     S3-compatible storage, Deepgram or AssemblyAI).
   - Start from https://fly.io/sprites/ecosystem/ and the Sprites docs on docs.fly.io.

4. Use the Context7 MCP server to pull current documentation for every library and API
   you plan to call, and confirm request and response shapes before writing code against
   them. At minimum: the Apify API and client, Pinecone, the Box API, the Gemini API
   (text-to-speech, including two-speaker output), the Ollama API, ffmpeg chapter
   metadata, and whichever speech-recognition API we use. If Context7 has no entry for
   something (TypeSafe AI's Jev may be too new), say so and fetch the vendor's own docs.
   Never guess an endpoint, parameter or model name.

5. The Fly.io CLI is already set up and authenticated on this machine. Check what is
   there (fly version, the Sprites CLI, which org is active, any existing Sprites and
   connectors) with read-only commands. Do not create, change or delete anything yet.

Then write docs/RESEARCH-NOTES.md with:
- what you confirmed, with a link to the doc page for each fact
- anything in the PRD or spec that the documentation contradicts
- anything you could not confirm from documentation

Stop there and show me the notes.
```

## Prompt 1: run the checks

```
Read docs/THURSDAY-CHECKS.md and docs/RESEARCH-NOTES.md.

Do not plan the full build yet. Work through docs/THURSDAY-CHECKS.md one item at a time.
For each item, write the smallest script in spikes/ that proves or disproves it. Use the
Fly.io CLI, which is already set up, to create the Sprite and run the spike on it. Tell me
what I need to do by hand in the Fly dashboard (adding a connector, pasting a key), since
keys never go in the repo or on the Sprite. Ask before any command that creates, deletes
or spends money, and before any Apify run.

Use Context7 or the vendor's docs to confirm an API call before you write it. Record each
result in docs/THURSDAY-CHECKS.md, including the real request and response shapes.

Stop after the checks and summarize what changed versus the PRD and spec.
```

## Prompt 2: write the plan

```
Use the Superpowers writing-plans skill. Do not use the brainstorming skill: the design is
settled in the PRD, docs/SPEC.md and the mockups, and the checks are done.

Write the implementation plan for the "Must have by Sunday" scope in docs/SPEC.md only.
Base every API call in the plan on docs/RESEARCH-NOTES.md and the recorded check results.
Order the tasks so that by the end of Friday there is one complete five-minute newscast
MP3 with chapters, built by hand trigger. Each pipeline step is its own task with a CLI
entry point and a test using saved sample data, so steps can be built and checked alone.

The pages follow the mockups in mockups/: match the PNGs for layout and the HTML for
copy and colors, rebuilt as plain HTML templates.

Put "Should have", "Nice to have" and The Table in a separate later section of the plan.
If the research notes or check results contradict the PRD or spec, list the conflicts
first and ask me before planning around them.
```

## Prompt 3: build

```
Use the Superpowers executing-plans skill on the plan. Stop for review after each task
group. Before using any API or library call you have not already confirmed, check it with
Context7 or the vendor's docs. Follow the cut order in docs/SPEC.md if we fall behind the
schedule. Deploy to the Sprite with the Fly.io CLI, and ask before anything that deletes
data or spends money.
```

## If you do want a brainstorm

Use it only for a decision the spec leaves open: the three weekend sources, whether the
station is WONE or WYOU, or the video rendering tool. Give it the question, not the whole
product.
