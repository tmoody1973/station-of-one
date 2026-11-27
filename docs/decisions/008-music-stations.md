# 008 — Music stations: Apple Music catalog through a Custom API connector, sampler page first

**Decision** — The music stations match tracks to the Apple Music catalog with the Apple Music API, reached through a Sprites "Custom API" connector that holds a developer token Tarik signs on his own Mac; the first public surface is a sampler page (tracklist, notes, sources, tap-to-play previews, Apple Music links), with full MusicKit playback after it. The work is split into three plans: discovery to sampler, voice and news, playback and more stations.

**Why this came up** — Tarik's PRD (Nov 27) turns Station of One into music stations heard through each listener's own Apple Music subscription. Neither Apple Music nor Perplexity is a built-in connector on the Sprites gateway, and the project rule is that no key ever sits on the Sprite, in code or in the repo. Apple's terms also limit previews: they may not be played back to back as a station.

**Options**
1. **Apple Music API through a Custom API connector.** Real catalog data (song IDs, ISRC, previews, Apple Music links) and the same IDs MusicKit plays later. Cost: Tarik signs a token on his Mac every six months and pastes it into the dashboard.
2. **Apple's free iTunes Search API.** No key, no token. Cost: a second matching system to replace when full playback arrives, and no storefront availability check.
3. **Skip matching until MusicKit.** Cost: nothing playable for judges until the last milestone.

**What we chose and why** — Option 1. Tarik chose it (he had the MusicKit key ready); Claude recommended option 2 for speed. Flagship station: UK jazz (Tarik's choice, the PRD's first milestone).

**What we gave up** — A token that expires (27 May 2027 for the first one) and has to be re-signed; a sampler that cannot play continuously without a subscription; more of the weekend spent on music than on polishing the newscast.

**How we'll know if this was right** — The sampler page lists at least ten matched UK jazz tracks, each with a preview that plays on tap and a source link that opens; no Apple audio is stored on our side; the token setup never put a secret into the repo or a chat.

**What actually happened** —
