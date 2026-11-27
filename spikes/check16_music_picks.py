"""Check 16: music picks. Proves the candidate shapes before production code uses them.

1. YouTube channel RSS through the existing RSS reader actor (ACTORS["rss"]).
2. Bandcamp label /music pages through the approved Cheerio Scraper: album id, title, artist per grid item.
Run on the Sprite: .venv/bin/python spikes/check16_music_picks.py
"""
import json
import time
from datetime import UTC, datetime, timedelta

from station.gateway import Gateway
from station.steps.scrape import ACTORS, actor_input, run_actor

CHANNELS = ["UC4eYXhJI4-7wSWc8UNRwD4A", "UC3I2GFN_F8WudD_2jUZbojA", "UC2Qw1dzXDBAZPwS7zm37g8g"]
LABELS = ["stonesthrow", "subpop", "ninjatune"]  # warp/music redirects to one album: no grid
PAGE_FUNCTION = """async function pageFunction(context) {
  const { $, request } = context;
  const items = [];
  $('li[data-item-id^="album-"]').slice(0, 6).each((i, el) => {
    const li = $(el);
    const title = li.find('p.title').clone().children().remove().end().text().trim();
    items.push({ id: li.attr('data-item-id').replace('album-', ''), title,
                 artist: li.find('.artist-override').text().trim(), href: li.find('a').attr('href') });
  });
  return { url: request.url, label: $('meta[property="og:title"]').attr('content') || null, items };
}"""

gw = Gateway()
t = time.time()
run = run_actor(gw, ACTORS["rss"], actor_input("rss", [f"https://www.youtube.com/feeds/videos.xml?channel_id={c}" for c in CHANNELS],
                                                datetime.now(UTC) - timedelta(days=14)), cap_usd=0.05)
print(f"youtube rss {run.status} {time.time() - t:.1f}s ${run.usd:.4f} items={len(run.items)}")
for it in run.items[:4]:
    print("  ", json.dumps({k: it.get(k) for k in ("feed_title", "item_title", "item_link", "item_published", "item_author")})[:300])

t = time.time()
run = run_actor(gw, "apify~cheerio-scraper", {"startUrls": [{"url": f"https://{l}.bandcamp.com/music"} for l in LABELS],
                                              "pageFunction": PAGE_FUNCTION, "maxCrawlingDepth": 0, "linkSelector": "",
                                              "proxyConfiguration": {"useApifyProxy": True}}, cap_usd=0.05)
print(f"bandcamp {run.status} {time.time() - t:.1f}s ${run.usd:.4f} pages={len(run.items)}")
for page in run.items:
    print("  ", page.get("url"), page.get("label"))
    for it in page.get("items", [])[:3]:
        print("     ", json.dumps(it)[:200])
