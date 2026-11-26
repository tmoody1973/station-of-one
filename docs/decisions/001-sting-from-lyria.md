# 001: The station sting is made once with Google's music generator

**Decision.** The open and close sting comes from one Lyria clip, generated once, trimmed and
committed as a file. No music segues between stories.

**Why this came up.** The spec requires "a short original sting at open and close" and bans
licensed music. Tarik asked whether Google's music generator (Lyria) should make station IDs
and segues. Getting it wrong costs either a licensing problem or minutes of runtime and an
extra hourly failure point.

**Options.**
1. Generate the sting once with Lyria, commit the file. Cost: under $0.50 of 30-second clips
   ($0.04 each, no free tier); every clip carries an inaudible SynthID watermark.
2. Same, plus short stabs between stories cut from the same clip. Cost: a scope change, and
   about 6–8 seconds less story time per newscast.
3. Generate music fresh each hour. Cost: a new paid API call and failure point every build,
   through an endpoint (`/v1beta/interactions`) not yet proven to pass the Sprites gateway.

**What we chose and why.** Option 1, Tarik's call (Claude recommended it). The sting is
already in scope; segues are not, and the five minutes belong to the stories. A committed file
can't fail at 9 am.

**What we gave up.** Segues that might make the show feel more like radio. The sting won't
change from hour to hour.

**How we'll know if this was right.** On Friday's first full MP3: the open and close sound
like a station, and no one listening asks where the music between stories went.

**What actually happened.**
