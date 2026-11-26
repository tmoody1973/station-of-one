# Station of One: build spec

Condensed from the PRD for building. Where this and the PRD differ, ask.

## 1. What it is

A personal agent on a Fly.io Sprite. It reads public feeds, and each broadcast hour it
publishes:

1. A five-minute audio newscast with chapters.
2. A live front page with the player, story cards, source links and the decision log.
   Each hour also keeps its own permanent page.

Once a day it also renders a vertical video (30 to 45 seconds) from the day's top story.
A second daily show, The Table, is built only after the newscast runs unattended.

Hackathon rules: runs on a Sprite, uses at least one Sprites connector, built Nov 23 to 29,
one entry, demo posted on X, Bluesky, LinkedIn or Reddit tagging @flydotio, form submitted
with code link, demo link and a two-sentence description.

Judges come from TypeSafe AI, Box, Fly.io, Pinecone, Ollama and Apify. Each of those
products must do visible, necessary work.

Station identity: WONE at 1.0 FM. The Table is identified as WNCL. Station ID lines and
the open decision about them are in `docs/STATION-ID.md`.

## 2. Newscast format (5:00)

| # | Chapter | Length | Content |
| --- | --- | --- | --- |
| 1 | Open | 0:10 | Sting, station ID ("WONE, 1.0 FM. One station, one listener."), the time, "here's the last hour on your internet" |
| 2 | Lead story | 1:00 | Highest score; host plus reporter, two voices |
| 3 | Stories 2 to 5 | 2:40 | About 40 seconds each, host only |
| 4 | Overheard | 0:30 | Best single comment of the hour, attributed |
| 5 | Corrections | 0:30 | First newscast of the day only |
| 6 | Sign-off | 0:10 | "I've read N posts today so you didn't. M didn't make air." |

- Without Corrections, the lead story runs 30 seconds longer.
- Fewer than three stories above threshold: shorter newscast, and the host says so.
- Tone: calm, dry, public-radio pacing. No jokes written into the script.
- Broadcast hours come from preferences (default 7 am to 7 pm, 13 newscasts).
- The whole build finishes in under ten minutes.

## 3. Beats and sources

Content is organized into beats; each beat has about five public sources.

| Beat | Source types | Used in |
| --- | --- | --- |
| AI and developer tools | Subreddits, Hacker News, public accounts, RSS | Newscast |
| Media and public radio | Trade newsletters, RSS, public accounts | Newscast |
| Milwaukee | Local news RSS, city subreddit | Newscast |
| Music business and industry | Trade press RSS (added Nov 26, Tarik) | Newscast |
| Arts and culture | Arts and culture RSS (added Nov 26, Tarik) | Newscast |
| Music | Bandcamp tags and labels, YouTube channels | Music picks only |

Specific sources and Apify Actors are chosen during the Thursday checks. Each hourly run
pulls only what is new since the last run. Store link, author, time, text, engagement.

Preferences live in one file on the Sprite (`config/preferences.example.json` shows the
shape). For this build it is edited by hand and the settings page is read-only.

## 4. Editorial engine

Apify gathers. Jev decides. Code applies thresholds. A language model writes only what
survived. See `config/jev_questions.json`.

Per post:

| # | Question | Type | Use |
| --- | --- | --- | --- |
| 1 | Will this still matter in a week? | probability | Main ranking score |
| 2 | New information, or reaction to known news? | choice of 2 | Keeps commentary out |
| 3 | Which part fits: lead, story, overheard, none? | choice of 4 | Builds the rundown |
| 4 | Is the central claim backed by a linked primary source? | yes/no + probability | How much the script hedges |
| 5 | Same story as this earlier post? | yes/no + probability | Merge after Pinecone lookup |
| 6 | Could airing this harm a private individual? | yes/no + probability | Hard exclusion |

Per newscast: for each chosen story, how many seconds it deserves (20 to 45).

Rules in code:
- Airs: the five highest Q1 scores among posts with Q1 at or above the air floor (start
  0.40, tune Friday). Measured Nov 26: Jev's Q1 ran 0.32–0.62, so a 0.70 bar aired nothing
  (see `docs/THURSDAY-CHECKS.md` check 6, `docs/decisions/002-air-rule.md`).
- Dropped and never shown if Q6 is at or above 0.20.
- Every answer and probability is logged with post id, question id and timestamp.

Corrections: store each Q1 call with its date. Seven days later, scrape for follow-up and
ask Jev whether the story was still being discussed. Report how the aired calls turned out
(decided Nov 26: grade every story that aired a week earlier).
Backfill on last week's posts so Sunday has real numbers.

## 5. Pipeline (one module and one CLI command per step)

1. `scrape`: Apify Actors, raw posts into SQLite.
2. `dedupe`: embed into Pinecone, find near matches, confirm with Q5.
3. `judge`: send each post to Jev with the questions; save every answer.
4. `rundown`: apply thresholds; write the rundown JSON (stories, order, seconds).
5. `write`: Ollama Cloud writes each chapter's script from the chosen posts only.
6. `voice`: Gemini TTS, one call per chapter; the lead story is one two-speaker call.
7. `assemble`: ffmpeg joins chapters with the sting, normalizes loudness, embeds chapter
   markers, writes chapters JSON.
8. `page`: render the front page and the hour page from templates and the newscast JSON.
9. `publish`: upload audio, pages and feed to the bucket; archive bundle and log to Box.
10. `finish`: write the run log, checkpoint, let the Sprite sleep.

Daily, not hourly: `captions` (speech recognition for word timestamps), `video` (render
the vertical cut), `music` (score new releases), `corrections`, `table`.

Station manager: if a step fails, the headless coding agent reads the error, tries one
repair or fallback, records what it did in the run log, and the build continues.

## 6. Audio requirements

- One MP3 per newscast, mono, loudness-normalized.
- Each chapter generated separately, then joined, so one failure does not sink the build
  and chapter start times are exact.
- Chapter markers embedded in the MP3 and written to a chapters JSON used by the page.
- Short original sting at open and close. No licensed music.
- Voice model: `gemini-3.8-flash-tts`
  ([model page](https://aistudio.google.com/docs/models/gemini-3.8-flash-tts)). Uses the
  `v1beta` API. Speaker and delivery go in `speech_metadata` on each turn, not in the text.
  Two speakers per call at most, prebuilt voices only. Returns 24 kHz mono 16-bit WAV.
  $9 per million audio tokens on the paid tier through Dec 31, 2026 (free tier exists).

## 7. Front page requirements

Structure follows audio-first public media sites: player first, every story playable.
Original name, colors and type. See `mockups/Main.dc.html`.

Must have:
- Header with show name and date.
- Sticky player bar holding the latest newscast: play, back and forward 15 seconds, time.
- Lead story: image area, beat tag, headline, two-sentence summary, Jev's score, source
  links, a play button that starts at that story's chapter.
- Story cards for the other stories: beat tag, headline, play button, score, source links.
- Today's newscasts: newest first, each with play, hour, duration and a link to its page.
- Counts: posts read this hour and today, stories aired.
- Footer line: voices are synthetic; the show is machine-edited.
- Works at phone width. Static files, no login, served from the bucket.

Should have: almost-made-air list (top five cut stories with scores), Corrections box,
preview image for link unfurls, RSS link.

Nice to have: generated graphics per story (plain beat-colored cards are fine), music
picks section with Bandcamp and YouTube embeds that load on tap.

Images: never copy a source's photo. The lead shows the publisher's own preview image straight from its
address (linked, not re-hosted), credited and linked to the story, when the scrape supplies one; otherwise
the beat-colored card. (Decided Nov 26, docs/decisions/004.)

## 8. Control room page

A page that shows the agent working, for the judges. See `mockups/ControlRoom.dc.html`.
It reads the run log and the decision log:
- Each step with the tool that did it, counts, seconds and status.
- Jev's decisions as a scrolling list: air, cut, drop, merge, with the probability.
- Station manager notes when a repair happened.
- Totals: posts read, Jev decisions, stories cleared, build time.

Rebuilt at the end of every run. A live-updating version during the run is a stretch.

## 9. Podcast feed (should have)

- One RSS feed with a single "latest newscast" item, replaced each hour.
- Cover art and the show-level fields directories require.
- Feed and audio in the bucket, not on the Sprite.
- Item description lists chapter timestamps as plain text.
- Spotify submission is manual and may not be approved by Sunday. Requirement: the feed
  validates and plays in a podcast app by URL.

## 10. Vertical video (must have, simple version)

- 1080x1920, 30 fps, 30 to 45 seconds, MP4, using the story's real audio.
- Simple version: count-up of posts read, the headline with word-timed captions, end card
  with the page address.
- Captions always on, inside the safe area. Word timing from speech recognition.
- Rendered on the Sprite from a code template. Output is a download; the owner posts it.
- Later: dot-field and score-dial animations, a Corrections cut, posting via Blotato.

## 11. The Table (second show, after the newscast is stable)

A separate daily show, about six minutes. Two agents argue the pettiest dispute in the
day's feeds. Jev referees. It replaces nothing in the newscast.

| # | Part | Length |
| --- | --- | --- |
| 1 | The question and where it came from | 0:30 |
| 2 | Opening claims | 1:30 |
| 3 | Three rounds, one claim each, Jev's ruling read after every claim | 3:00 |
| 4 | Verdict from Jev's totals | 0:30 |
| 5 | Season record | 0:30 |

- Cast: the Anchor (careful, cites sources) and the Uncle (confident, full of theories,
  often wrong; a character defined by his theories, not by any background or group).
- Topic: Jev scores yesterday's threads on "real two-sided dispute?" and "low-stakes?".
  The top thread passing both is the question.
- Excluded in code: elections, contested policy, religion, health.
- Agents argue positions from the feeds ("some posters say"). Never voice a real person.
- Each claim goes to Jev with both sides' sources. Scores are fixed before the verdict is
  scripted, so the writing model cannot pick the winner.
- Own page, own card on the front page, own item in a daily feed. Running record stored.
- If not working by Sunday noon, ship without it.

## 12. Scope

Must have by Sunday:
- Scrape, Jev scoring and story selection end to end on the Sprite, on an hourly schedule.
- The five-minute newscast as one MP3 with chapters.
- Front page (must-have list above) and per-hour pages.
- Control room page from the run log.
- Read-only settings page rendered from the preferences file (see `mockups/Settings.dc.html`).
- Box archive of the decision log.
- One simple vertical video.

Should have: Corrections on backfilled data, almost-made-air list, RSS feed, preview image.

Nice to have: generated graphics, music picks.

Then: The Table.

Cut first, in this order: Overheard; video animations; RSS feed; Pinecone dedupe (fall
back to link matching); the second voice on the lead story.

Not in this build: continuous stream, live interruptions, private sources, accounts,
payments, onboarding screens, editable settings, a CMS, Spotify listing.

## 13. Schedule

| Day | Goal | Done when |
| --- | --- | --- |
| Thu Nov 26 | Prove the risky parts | All Thursday checks recorded; backfill started |
| Fri Nov 27 | One complete newscast | Full MP3 with chapters, built by hand trigger |
| Sat Nov 28 | On the hour, on the page | Unattended hourly runs; front page and control room live; Box archive |
| Sun Nov 29 | Video, extras, submit | Video rendered; Corrections and feed if time; demo posted by 6 pm Central; form in |

## 14. Demo (60 seconds)

1. A real speaker on a desk and a clock near the hour. "I've been on the radio for 20
   years. This week I built a station with exactly one listener."
2. The open plays: "It's nine o'clock. Here's the last hour on your internet."
3. Front page on a phone: tap a story, tap a source.
4. Control room: steps and tools, Jev's decisions scrolling.
5. Corrections line with the real backfill numbers.
6. End card: page address, "runs on a Fly.io Sprite."

Submission checklist: agent running on a Sprite; public repo with a README listing each
connector and its job; demo post tagging @flydotio; form submitted; a live page the judges
can open.
