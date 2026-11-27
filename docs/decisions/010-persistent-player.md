# 010 — One player for the whole site: swap only the page content

**Decision** — After the first page load, link clicks fetch the next page in the background and replace only its `<main>` content; the masthead, station strip and player bar are never reloaded, so audio and embedded players keep playing across pages, Back and Forward.

**Why this came up** — Tarik asked (Nov 27) for a persistent player on every page that keeps playing while switching pages with no stoppage, and for a station strip like KCRW's. A static site reloads everything on each click, which stops audio. The music stations will play through that player (voice breaks, newscasts, and full songs once Apple Music is connected).

**Options**
1. **Swap only `<main>` with a small script of our own.** About 30 lines; the player is never touched. Cost: we maintain it, and page scripts must work after a swap.
2. **Turbo Drive with the player marked permanent.** A widely used library (Turbo 8). Cost: in our spike it reloaded the YouTube embed on every page change (9 reloads in 9 moves), because Turbo moves the player into each new page; 190 KB of code.
3. **Keep full page loads, open a pop-up player window.** No architecture change. Cost: a second window, blocked by many browsers, not the experience Tarik described.

**What we chose and why** — Option 1. Claude chose it on the spike's evidence (check 19): audio and the embed both survived 5 page changes plus Back and Forward, against 9 embed reloads for Turbo.

**What we gave up** — A maintained library's edge-case handling (forms, scroll restoration, prefetch); our own script has to handle Back/Forward, external links, downloads and failures, each with a test.

**How we'll know if this was right** — On the live site, a newscast started on the front page plays without a gap through a story page, the jazz sampler, a music pick and the control room, and Back twice; a docked Bandcamp player keeps playing too.

**What actually happened** —
