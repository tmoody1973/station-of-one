# Station of One · ONE 1.0 FM

**A radio station with exactly one listener, run by an agent on a Fly.io Sprite.** Every hour from 7 am to 7 pm Central it reads public posts (about 1,300 a day), lets TypeSafe AI's Jev decide what airs, and publishes a five-minute newscast with synthetic voices, chapters, a live front page and a control room that shows every decision; each morning it also grades last week's calls (Corrections) and stages a debate show, The Table, that Jev referees. Around the clock it also programs music stations the way a radio program director would; the flagship, **Rhythm Lab**, is built from 13 years of Tarik's Rhythm Lab Radio playlists.

Built for Fly.io Hacksgiving, Nov 23–29, 2026. The voices are synthetic and the show is machine-edited. ONE 1.0 FM is a fictional station.

## Open it

| What | Link |
| --- | --- |
| Front page (latest newscast, player, stories, Corrections, almost-made-air) | https://patient-mountain-3400.fly.storage.tigris.dev/index.html |
| Control room (every step, tool, timing and Jev decision for the hour) | https://patient-mountain-3400.fly.storage.tigris.dev/control-room/index.html |
| Settings (beats, sources, thresholds, connectors; read-only) | https://patient-mountain-3400.fly.storage.tigris.dev/settings/index.html |
| The Table, episode 1 ("Is Intel One Mono worth switching to?") | https://patient-mountain-3400.fly.storage.tigris.dev/table/2026-11-26/index.html |
| Daily vertical video | https://patient-mountain-3400.fly.storage.tigris.dev/video/2026-11-26.mp4 |
| Podcast feed (latest newscast plus every Table episode) | https://patient-mountain-3400.fly.storage.tigris.dev/feed.xml |
| Rhythm Lab, the flagship music station (on now, what's coming up, with start times) | https://patient-mountain-3400.fly.storage.tigris.dev/radio/rhythm-lab/index.html |
| This week's music meeting (every add, move and drop, with Jev's probability and reason; the rotation board) | https://patient-mountain-3400.fly.storage.tigris.dev/radio/rhythm-lab/meeting/index.html |
| How the station is programmed (rotation, hour clocks, separation, the meeting) | https://patient-mountain-3400.fly.storage.tigris.dev/radio/how-it-works/index.html |
| ONE Jazz, the UK jazz sampler (a fresh 50-minute set each hour) | https://patient-mountain-3400.fly.storage.tigris.dev/radio/uk-jazz/index.html |

## What happens each hour

1. **At :48, every hour** a Cloudflare Worker cron calls the Sprites exec API. The Sprite wakes and starts the build; a lock stops two builds overlapping, and a Tasks API hold keeps the Sprite awake until it finishes. Between 7 pm and 7 am there is no newscast: the build runs only the 24/7 music station (below).
2. **Scrape.** Apify Actors read Hacker News, Reddit, RSS feeds, Bluesky and Google News for six news beats.
3. **Find duplicates.** Link matching, title overlap, and Pinecone similarity against earlier hours; Jev's "same story?" question makes the merge.
4. **Judge.** Jev answers five typed questions per post (likely to matter in a week? new or a reaction? which part of the show? primary source? could it harm a private person?), each with a probability. Every answer is logged.
5. **Rundown.** Code applies the thresholds: drop anything 20%+ likely to harm a private person, air the best story per beat and then the top scores at 40%+, up to five. A language model never chooses what airs.
6. **Write.** Ollama Cloud writes scripts only from the posts that passed, attributed to where they were posted, in the show's own words.
7. **Voice.** Gemini TTS: a host and a reporter (two-speaker on the lead).
8. **Assemble.** ffmpeg joins the chapters with a sting, normalizes loudness and writes chapter markers into one MP3.
9. **Story pages.** Each aired story gets its own page: a short article written only from its own posts (attributed in every paragraph, sized to the source material), its sources, Jev's score and a Listen button. The image is the publisher's own preview photo, shown from their address and credited; if there is none, Gemini draws an abstract Bauhaus illustration, labeled as a machine illustration.
10. **Page, publish, archive.** Static pages and audio go to the Tigris bucket; a zip of the hour (scripts, rundown, audio, every Jev answer) goes to Box.
11. **Finish.** The control room is refreshed and the Sprite takes a checkpoint. If any step fails, the station manager (headless Claude through the Anthropic connector) picks retry or skip from a fixed menu and writes one sentence for the control room.

**Once a day:** after the 7 am newscast, The Table (yesterday's pettiest low-stakes dispute, two agents, Jev scores every claim, code declares the winner) and Corrections (last week's aired calls, checked for follow-up); after the 7 pm newscast, a 30–45 s captioned vertical video of the day's top story (Deepgram word timings, Remotion). Also after the 7 am newscast: **music picks**, three new releases from chosen Bandcamp labels and YouTube channels, ranked by Jev and shown as the artists' official players, which load only when you tap Play (`docs/decisions/007-music-picks.md`).

## Music stations

The same agent programs music stations heard through each listener's own Apple Music subscription (`config/stations/`, `station/radio/`). No audio is stored or streamed by the station: what it publishes is a schedule, and each listener's browser plays it.

### Rhythm Lab: the flagship, programmed around the clock

Tarik's Rhythm Lab Radio library (563 shows, 10,701 tracks, 2005 and 2013–2026) is the station's catalog: 2,513 tracks matched on Apple Music, each carrying how Tarik played it.

- **Rotation categories.** Core tracks (6+ shows) are Power Gold, rested 20 hours between plays; rotation tracks (3–5 shows) rest 3 days; recent repeats 5 days; the rest of the library 10 days; new finds 6 hours.
- **The show's own habits.** Energy comes from where Tarik placed a track (hour 2 of the show ran uptempo); tracks that opened an hour or closed a show are preferred in those slots; tracks he played back to back get a small pairing bonus (13,282 pairs); one slot an hour leans on holiday records from Nov 26 to Dec 31.
- **Hour clocks.** A day clock (with the newscast at :00) and an overnight clock. :00 and :30 always start on time: a song that would run past one is swapped for a shorter one, and leftover time goes to a break.
- **Separation that never bends.** No artist twice in 3 hours, no two 7-minute songs back to back, energy never jumping two levels. Softer preferences give way first.
- **The weekly music meeting** (daily in the first week). Jev is asked whether each new find should join, whether songs have earned more airplay, whether listeners are tired of them; code acts at 0.6 or more, moves at most a quarter of a category per meeting, and never drops a library track. Every answer is logged and shown on the meeting page.
- **The queue.** Each hour the station schedules the next two hours and publishes `data/radio/rhythm-lab/queue.json` (start times, Apple song ids, public notes). The station page lists them with start times; the browser marks what's on now.
- **Privacy.** The library and Tarik's show notes live only in the Sprite's database. Pages show the track, its Apple Music link and "First aired on Rhythm Lab Radio, Nov 2014"; never a show note or a Drive link.

New music still comes in: five feeds (Bandcamp Daily, Stones Throw, Brownswood, DJ Mag, The Quietus) are read each daytime hour, and Jev rates each find against the brief before the meeting considers it. Why this design, and what it gave up: `docs/decisions/009-24-7-music.md`.

### ONE Jazz: the UK jazz sampler

ONE Jazz keeps the simpler hourly programmer: it reads its feeds (UK Vibe, Brownswood, Bandcamp Daily, r/Jazz), has Ollama list the music each item names, Jev rate every find against the brief, matches them on Apple Music (under 80% confidence is held; originals beat remasters and live takes), and programs a 50-minute set (no artist twice in 3 hours, a mix of new, recent and older records). Its ~30 matched songs are too few for a 24-hour clock, so it moves to the program director when its catalog grows (one line in its config).

Both pages show Apple's 30-second previews (they play only when tapped and never advance on their own) and a "Listen on Apple Music" link. The Apple Music developer token is signed on Tarik's Mac and held in a Custom API connector (`docs/decisions/008-music-stations.md`). Next: full songs through MusicKit ("Connect Apple Music" in settings), then voice breaks with cited facts and news on the music stations.

## How the site plays

Every page shares one player bar, pinned to the bottom, and one strip of stations under the masthead (`templates/_player.html`, `templates/_masthead.html`, `templates/shell.js`).

1. Every ▶ on the site says what it plays in a `data-play` attribute: the file, the title, where to start, and its chapters. The newscast, a story's Listen button, The Table's chapters, music picks and 30-second previews all play through the same bar.
2. When you follow a link to another page of the site, `shell.js` fetches that page and swaps in only its main content. The bar, the masthead and the strip never reload, so the audio keeps playing, including through Back and Forward. Anything unusual (another site, the RSS feed, a download, a failed fetch) is an ordinary page load.
3. The strip reads `/data/stations.json` every minute: News with the latest newscast, then each music station that has published a set (the flagship first) with what is on now. The page step writes it each hour; the radio step rewrites it after each run.
4. A music pick's page keeps its big player on the page; "Keep it playing as you browse" docks it in the bar instead.

Nothing plays until you tap. Why the main-content swap and not a library such as Turbo: `docs/decisions/010-persistent-player.md` (check 19).

## Connectors (Sprites connector gateway)

No API key is in the Sprite, the code, the config or this repo. Every call goes through the gateway.

| Connector | Its job here | Where to see it |
| --- | --- | --- |
| **Apify** | Scrapes every news source each hour (5 Actors), reads each story's preview photo (Cheerio Scraper) and the music stations' feeds. On a paid plan since Nov 27: the free plan's $5 a month ran out that afternoon and every scrape was refused until the upgrade | Control room, "Scrape sources"; story pages |
| **TypeSafe AI (Jev)** | Every editorial decision, as typed answers with probabilities: what airs, duplicates, airtime, hot topics, The Table's topic and every claim's ruling, Corrections; for music, whether a find fits a station, the music meeting's adds and moves, and each new song's energy and vocals | Control room decision log; Table rulings; music meeting page |
| **Ollama Cloud** | Writes the newscast scripts and The Table's claims, and lists the music each feed item names (`deepseek-v4.1-flash`) | Any newscast; Table page |
| **Google Gemini** | Voices: host/reporter for the news, Anchor/Uncle for The Table (`gemini-3.8-flash-tts`); Bauhaus illustrations for stories with no photo (`gemini-3.1-flash-image`) | The audio; story pages |
| **Pinecone** | Same-story detection across hours, and the memory Corrections searches for follow-ups | Control room, "Find duplicates"; Corrections box |
| **Box** | Archive of every newscast and Table episode with its full decision log | "Station of One archive" folder |
| **Tigris** | Public hosting of pages, audio, feed and video | Every link above |
| **Deepgram** | Word timestamps for the video captions | The vertical video |
| **Apple Music** (Custom API connector) | Finds each record in Apple's catalog: song ids, previews, artwork and links for the music stations | Every music page |
| **Anthropic** | Station manager: picks a repair when a step fails (headless Claude CLI). The planned daily "source scout" was not built. | Control room, "Station manager" |

The hourly trigger itself runs on a Cloudflare Worker (`trigger/`), after GitHub Actions' schedule skipped its first two slots (`docs/decisions/005-cloudflare-trigger.md`). Since Nov 27 it fires every hour, so the music station runs overnight.

## Editorial rules enforced in code

- Jev decides; code applies the thresholds. Scripts are written only from posts that passed selection.
- Every claim is attributed to where it was posted; nothing scraped is stated as fact. At most one short quote per story.
- Posts likely to harm a private individual are dropped and never shown, anywhere.
- Public sources only. No licensed music in the station's audio, feed or video: music plays only through each listener's own Apple Music, or as an artist's official player. Voices are synthetic, and every page and the feed say so.
- A language model never picks the next song either: Jev answers the music meeting's questions, and code applies the rotation, rest times, clocks and separation.
- The daily video and The Table skip elections, contested policy, religion and health (a Jev screen). The Table never names or quotes a commenter.
- Story photos are shown from the publisher's own address, credited to the publisher and linked, never copied (`docs/decisions/004-story-photos.md`). Stories without one get an abstract illustration with no people, text or logos, labeled "Illustration generated by machine for this story. Not a photograph." (`docs/decisions/006-story-pages-and-images.md`).

## Run it yourself

The Sprite holds the state (SQLite, run folders); the code is plain Python, one module and one command per step. Each step reads and writes files in a run folder, so any step can run by hand:

```bash
uv sync
uv run pytest -q                                              # 469 tests
uv run python -m station scrape   --run data/runs/2026-11-27T09   # one step
uv run python -m station judge    --run data/runs/2026-11-27T09
uv run python -m station build    --hour 2026-11-27T09            # a whole newscast
uv run python -m station table    --day 2026-11-26                # an episode of The Table
uv run python -m station video    --day 2026-11-26                # the daily video
uv run python -m station radio    --station rhythm-lab            # one music station's hour
uv run python -m station radio    --station rhythm-lab --meeting  # hold its music meeting now
uv run python scripts/rhythm_lab_golive.py --db /tmp/copy.db     # load the library (rehearse on a copy)
uv run python scripts/library_report.py                         # private list of unmatched library tracks
```

Browser tests for the shared player (system Chrome, against a test copy in the bucket): `STATION_E2E=1 uv run --with playwright pytest -q tests/e2e`.

The network steps need the Sprites connector gateway, so they run on a Sprite with the connectors above attached. `config/preferences.json` holds the beats, sources, thresholds and voices; the settings page is rendered from it.

## How it was built

- `docs/SPEC.md`: what the station must do. `docs/THURSDAY-CHECKS.md`: every risky assumption, proven or corrected with real runs (request shapes, timings, costs, failures).
- `docs/decisions/`: the decisions where a reasonable person could have chosen differently, with what was given up.
- `docs/superpowers/plans/`: the eight implementation plans (the newscast, The Table, story pages, music picks, the UK jazz sampler, the site shell, the program director, Rhythm Lab), executed task by task with tests written first, each closed by an independent code review.
- `docs/LATER.md`: work agreed for after the hackathon (moving the site to Next.js).

Station identity: ONE at 1.0 FM, an invented frequency. It was WONE until Nov 27; real US call signs start with K or W, so the station now uses no call letters at all (`docs/decisions/011-rename-to-one.md`).
