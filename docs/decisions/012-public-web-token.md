# 012 — Full songs in the browser: a public, origin-locked Apple Music web token

**Decision** — Full songs play in the listener's browser through MusicKit on the Web, configured with a separate Apple Music developer token that is public by design: locked to the station's web address (`--origin https://patient-mountain-3400.fly.storage.tigris.dev`), valid 60 days, signed on Tarik's Mac, placed on the Sprite by his own command, and published as `/data/musickit.json`. It is the one key-like value outside the Sprites connector gateway.

**Why this came up** — Plan C lets a listener with an Apple Music subscription hear Rhythm Lab's full songs, live, in the site's player. MusicKit on the Web runs in the browser and calls Apple directly, so it needs a developer token in the page; the gateway can't stand in for a browser. The project rule is that no API key goes in the Sprite, code, config or repo. Getting this wrong means either no full songs at all, or exposing the server token that the station's own catalog lookups depend on.

**Options**
1. **A separate web token, origin-locked, published.** Apple's documented way to run MusicKit in a web page. Cost: anyone can copy it from the page; Apple honours it only from our address in a browser, but a script can fake that address, so the worst case is someone spending Tarik's Apple developer quota until the token expires or is replaced.
2. **Reuse the server token from the gateway connector in the page.** No new token. Cost: it has no origin lock, and exposing it puts the station's own Apple Music lookups at risk.
3. **No full songs; previews and a demo video only.** No token outside the gateway. Cost: no listener can actually hear the station, which is the point of a 24/7 station.

**What we chose and why** — Option 1. Claude proposed it in Plan C and Tarik approved it (Nov 27), with a 60-day lifetime. The token never enters the repo (`data/` is git-ignored), the transfer script prints only its length, and Claude never handles it.

**What we gave up** — A rule kept without exception until now: one credential lives outside the gateway, in public. Tarik re-signs it every 60 days (late January next). MusicKit loads from Apple's servers when a listener taps, which is a third party in the listener's browser.

**How we'll know if this was right** — In two weeks: Apple's developer dashboard shows MusicKit usage only in line with real listening; no request with our token comes from anywhere but our pages; nobody had to revoke the key.

**What actually happened** —
