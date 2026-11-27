# 007 — Music picks are a daily, Jev-ranked section with players that load only on tap

**Decision** — Once a day, after the 7 am newscast, the station gathers new releases from chosen Bandcamp labels and YouTube channels, Jev scores each one, code keeps the top three (one per source, no repeats within a week), and the front page shows them as the artists' official players that load only when a reader taps Play.

**Why this came up** — The spec listed "music picks" as a nice-to-have, and the Music beat in settings showed two placeholder sources and zero posts. On Nov 27 Tarik asked for both: Music became a news beat (Pitchfork-style feeds) and music picks were built. The station may not play licensed music on air, in the feed or in the video, so music can only appear as official embeds on the page.

**Options**
1. **Daily picks, Jev ranks, players on tap.** Fits the editorial rule (Jev decides, code applies), costs a fraction of a cent a day, and nothing from Bandcamp or YouTube loads until the reader asks. Cost: one more daily step and one more scraper permission in use.
2. **Hourly picks.** Fresher, but the sources only change a few times a week, and it would repeat picks or burn Jev calls for nothing.
3. **Hand-picked list in settings.** No code, no cost. Cost: not machine-edited, which is the whole premise of the station, and it goes stale.

**What we chose and why** — Option 1. Tarik approved the plan; Claude chose the starter sources (NPR Music, KEXP and COLORS on YouTube; Stones Throw, Sub Pop and Ninja Tune on Bandcamp) because Tarik approved without naming any. They live in `config/preferences.json` under `music_picks`.

**What we gave up** — Bandcamp label pages carry no release dates, so "new" means "first on the label's page"; the starter sources are Claude's taste, not Tarik's; today's picks appear at 8 am, not 7, because the step runs after the 7 am newscast is published.

**How we'll know if this was right** — Every morning has three playable picks from three different sources; no pick repeats within a week; the front page never loads a third-party player before a tap.

**What actually happened** —
