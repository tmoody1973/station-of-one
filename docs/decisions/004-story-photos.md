# 004 — Story photos: the publisher's preview image, linked, with a beat card fallback

**Decision** — The lead story shows the publisher's own preview image, loaded from the publisher's address and credited with a link to the story; when there is none, or it fails to load, the beat-colored card shows instead.

**Why this came up** — Tarik wanted headline photos on the front page. A page with photos reads like a news site; a page of colored blocks reads like a prototype. But almost every news photo is licensed (AP, Getty, Reuters) for that outlet only, and a machine-edited show that republishes them is exactly what the spec's image rule was written to prevent. If we got it wrong, the first thing a judge or a publisher sees is someone else's photo on our page.

**Options**
1. **Beat-colored cards only.** No rights questions at all. Cost: the page looks plainer.
2. **Generated art per story.** An image model draws an illustration each hour. Cost: per-image spend 13 times a day, and a risk of an odd or misleading picture beside real news.
3. **The publisher's preview image, linked.** Sites publish a preview image so links look good when shared; we display it from their address, the way social apps build link previews, credit it, and link to the story. Cost: still a display of their photo; any publisher can object or block it.

**What we chose and why** — Option 3 with option 1 as the fallback. Tarik made the call. Claude's part: we never download or re-host the image (the spec's line is "never copy"), only scraped image fields are used (no extra fetching outside the connector gateway), and unsafe or broken image addresses fall back to the beat card.

**What we gave up** — The cleanest rights position (option 1). Coverage is also partial: Bluesky link cards, Google News and Reddit carry images; RSS feeds and Hacker News, where many aired stories come from, do not, so many hours will still show the beat card.

**How we'll know if this was right** — No publisher complaints or blocked images during the hackathon, and at least some hours show a photo. Check the public front page after a day of builds and count hours with a photo versus a card.

**What actually happened** —
