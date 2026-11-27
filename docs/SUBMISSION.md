# Submission checklist (spec §14)

Deadline: before midnight PST, Sunday Nov 29, 2026. Demo posted by 6 pm Central Sunday.

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Agent running on a Sprite | Done | Sprite `brave-indigo-lion`; hourly builds started by the Cloudflare cron (`trigger/`), visible in the control room: https://patient-mountain-3400.fly.storage.tigris.dev/control-room/index.html |
| 2 | Uses at least one Sprites connector | Done (nine) | README "Connectors" table; `docs/THURSDAY-CHECKS.md` checks 1–13 record each proven request |
| 3 | Public repo with a README listing each connector and its job | Done | https://github.com/tmoody1973/station-of-one (README) |
| 4 | A live page the judges can open | Done | https://patient-mountain-3400.fly.storage.tigris.dev/index.html |
| 5 | Demo posted on X, Bluesky, LinkedIn or Reddit, tagging @flydotio | **Tarik** | 60-second demo below |
| 6 | Form submitted with code link, demo link and description | **Tarik** | Description below |

## Description for the form (two sentences)

Station of One is a radio station with exactly one listener, run by an agent on a Fly.io Sprite: every hour it reads public posts, lets TypeSafe AI's Jev decide what airs, and publishes a five-minute synthetic-voice newscast with chapters, a live front page and a control room showing every decision. Each morning it grades last week's calls in a Corrections segment and stages The Table, a debate show Jev referees, and each evening it renders a captioned vertical video of the day's top story.

## Demo, 60 seconds (spec §14)

1. A real speaker on a desk and a clock near the hour. "I've been on the radio for 20 years. This week I built a station with exactly one listener."
2. The open plays: "It's nine o'clock. Here's the last hour on your internet."
3. Front page on a phone: tap a story, tap a source.
4. Control room: steps and tools, Jev's decisions scrolling.
5. Corrections line with the real backfill numbers ("called 5 stories… 0 were still being discussed").
6. End card: page address, "runs on a Fly.io Sprite." (The daily vertical video's end card already carries it.)

## Before posting

- Done Nov 27: renamed to ONE 1.0 FM (no call letters), so no FCC check is needed. Old note: check the call signs (WONE, WNCL) against the FCC's call sign search, or keep the "fictional station" lines as they are (they are on every page).
- Listen to the newest newscast once; check the control room shows a full green run.
