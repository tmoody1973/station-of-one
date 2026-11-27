# Submission checklist (spec §14)

Deadline: before midnight PST, Sunday Nov 29, 2026. Demo posted by 6 pm Central Sunday.

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Agent running on a Sprite | Done | Sprite `brave-indigo-lion`; builds every hour at :48, started by the Cloudflare cron (`trigger/`), visible in the control room: https://patient-mountain-3400.fly.storage.tigris.dev/control-room/index.html |
| 2 | Uses at least one Sprites connector | Done (ten) | README "Connectors" table; `docs/THURSDAY-CHECKS.md` records each proven request |
| 3 | Public repo with a README listing each connector and its job | Done | https://github.com/tmoody1973/station-of-one (README) |
| 4 | A live page the judges can open | Done | https://patient-mountain-3400.fly.storage.tigris.dev/index.html |
| 5 | Demo posted on X, Bluesky, LinkedIn or Reddit, tagging @flydotio | **Tarik** | 60-second demo below |
| 6 | Form submitted with code link, demo link and description | **Tarik** | Description below |

## Description for the form (two sentences)

Station of One is a radio station with exactly one listener, run by an agent on a Fly.io Sprite: every hour it reads public posts, lets TypeSafe AI's Jev decide what airs, publishes a synthetic-voice newscast with a control room showing every decision, and each morning grades its own past calls in public. Around the clock it also programs Rhythm Lab, a music station built from my 13 years of radio playlists, the way a real program director would: rotation, hour clocks and a weekly music meeting where Jev decides and code applies the rules, so a language model never picks the next song.

## Demo, 60 seconds (spec §14)

Three beats and a sting. Each beat shows the agent deciding, not just the output.

| Time | Picture | Words (Tarik, on camera or voice-over) |
| --- | --- | --- |
| 0:00–0:06 | A real speaker on a desk, a clock near the hour | "I've been on the radio for 20 years. This week I built a station with exactly one listener." |
| 0:06–0:18 | **The news.** The open plays ("It's nine o'clock. Here's the last hour on your internet."); front page on a phone: tap a story, tap a source | "Every hour an agent reads the posts I'd scroll past and makes me a newscast." |
| 0:18–0:30 | **The control room:** Jev's decisions scrolling, each with a probability; then the Corrections box with its real numbers | "Jev decides what airs; code applies the rules; every call is logged, and every morning it grades last week's calls in public." |
| 0:30–0:48 | **Rhythm Lab.** The station page with "On now" and the next hour's times; then the music meeting page: adds with Jev's probability and reason; then the hour-clock drawing | "And around the clock it programs my own show, 13 years of Rhythm Lab playlists, like a program director. At its first music meeting Jev added 89 records, each with a reason. A language model never picks the next song." |
| 0:48–0:55 | **The Table** (the sting): the Uncle's voice mid-argument, Jev's verdict on screen | "Every morning two synthetic voices argue yesterday's pettiest internet fight. Jev referees." |
| 0:55–1:00 | End card: page address, "Runs on a Fly.io Sprite", @flydotio | (station ID) "ONE, 1.0 FM. One station, one listener." |

Keep the clips real: record from the live pages, not mockups. The 89 is from the first meeting (Nov 27, 3:48 pm build); if a later meeting is shown, say its own number.

## Post text

Fits X (280 with the link shortened) and Bluesky (300); LinkedIn and Reddit can take the longer story from the description.

> 20 years on the radio. For #Hacksgiving I built a station with one listener: an agent on a @flydotio Sprite makes my hourly newscast, grades its own calls, and programs my 13 years of playlists like a program director. https://patient-mountain-3400.fly.storage.tigris.dev/index.html

## Before posting

- Done Nov 27: renamed to ONE 1.0 FM (no call letters), so no FCC check is needed.
- Listen to the newest newscast once; check the control room shows a full green run.
- Open Rhythm Lab and check "On now" names a real song and the next hour has times: https://patient-mountain-3400.fly.storage.tigris.dev/radio/rhythm-lab/index.html
- Open the music meeting and skim the adds; if one is wrong for the station, say so before filming that page: https://patient-mountain-3400.fly.storage.tigris.dev/radio/rhythm-lab/meeting/index.html
- Fill in "What actually happened" in decisions 006–011 and 009, in your own words.
