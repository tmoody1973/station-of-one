# 013 — ONE Jazz: a 24/7 jazz station programmed by style

**Decision** — ONE Jazz stops being an hourly sampler and becomes a 24/7 jazz station run by the same program director as Rhythm Lab. Each hour follows one of five daypart clocks (a clock is the fixed order of slots in an hour) whose slots name a style of jazz. The song's rotation category (the group that sets how often a song can play) still decides how long it rests. The catalog is the core jazz from Rhythm Lab Radio's library, plus two new sources: new releases from the station's own artists, and well-known recordings that fill the thinnest styles. Jev names each new record's style, and a record Jev calls "not jazz" is never added.

**Why this came up** — Tarik, Nov 27, 6:04 pm: "create general jazz stream instead of sampler like rhythm lab using program director best practices", with his jazz programming folder (tiers, seven styles, five daypart clocks, separation rules). The sampler had about 30 matched songs, enough for one 50-minute set an hour. A 24-hour stream at 11 tracks an hour plays 264 tracks a day. With the folder's rule that no track repeats within 72 hours, it needs roughly 800 playable tracks, spread across the styles the clocks ask for. Getting this wrong means either a station that repeats itself within a day or one whose "jazz" slots play whatever is left.

**Options**
1. **Clock slots name styles; categories set rest.** A slot asks for, say, heritage jazz; the scheduler takes a rested heritage song from any category, and if none can play it tries that style's fallback list (a short list of the closest styles), then any jazz. Cost: a second dimension in the scheduler; while a style is thin, its slots sometimes play a neighbouring style.
2. **One category per style.** Seven categories, and clock slots name categories exactly as Rhythm Lab's do. No scheduler change. Cost: every record in a style would rest the same time, so Tarik's play counts (how often he played a record on Rhythm Lab Radio, which decide how often it airs) would stop mattering.
3. **Keep the sampler and add feeds.** No new code. Cost: it never reaches 24 hours; the feeds mostly surface classic American jazz that's already in the library.

**What we chose and why** — Option 1. Claude proposed it in the jazz plan (`docs/superpowers/plans/2026-11-27-jazz-station.md`) and Tarik approved it ("Approve, build it next"). It keeps both halves of his folder: the style order of each daypart clock, and the play-count tiers. The style fallback lists, the 10-minute "long song" rule and the targets for thin styles (heritage 150, vocal 120, Latin/Brazilian/Afro 120) are Claude's judgment, editable in `config/stations/jazz.json`.

**What we gave up**
- The thin styles start thin. A rehearsal on a copy of the database found 948 playable core tracks, but only 86 heritage, 52 vocal and 46 Latin. Until deepening catches up, those slots will often play their fallback style.
- Deepening uses Apple Music's "top songs" for each artist, which leans toward the obvious recordings over the deep cuts a jazz programmer would pick.
- The new-release scout only checks artists already on the station. New artists still arrive only through the four jazz feeds. Apple's genre-filtered new-release listing was skipped: it wasn't verified and wasn't needed beside the artist check.
- The old ONE Jazz sampler is retired, not deleted: its config stays because about 40 tests use it, and its old page now points to the new station.

**How we'll know if this was right** — After a week on air, from the queue table on the Sprite: (1) no track played twice within 72 hours and no artist within 4 hours; (2) at least 8 in 10 style slots outside heritage, vocal and Latin played the style they named; (3) heritage, vocal and Latin have moved toward their targets; (4) Tarik spot-checks 20 of Jev's style answers on new finds and agrees with at least 16.

**What actually happened** —
