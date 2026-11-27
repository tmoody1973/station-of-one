"""Check 17: music station (Plan A). Apple Music catalog shapes through the custom_api connector, and which
UK jazz feeds Apify can read. Run on the Sprite: .venv/bin/python /home/sprite/spikes/check17_music_station.py"""
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from station.gateway import Gateway
from station.steps.scrape import ACTORS, actor_input, run_actor

import urllib.request  # noqa: E402

gw = Gateway()
# The Gateway helper finds connectors by provider; custom_api will hold two (Apple Music, Perplexity), so the
# spike calls the Apple Music connector's gateway URL directly.
GW = "https://api.sprites.dev/v1/gateway/custom_api/YlFQlsDQx9sk2cz9TI82Ng"


def get(path: str) -> dict:
    with urllib.request.urlopen(GW + path, timeout=30) as r:
        return json.loads(r.read())


t = time.time()
for term in ("Nubya Garcia Odyssey", "Yussef Dayes Black Classical Music", "Kokoroko Abusey Junction"):
    d = get(f"/v1/catalog/us/search?term={quote(term)}&types=songs,albums&limit=3")
    songs = d.get("results", {}).get("songs", {}).get("data", [])
    albums = d.get("results", {}).get("albums", {}).get("data", [])
    print(f"== {term}: {len(songs)} songs, {len(albums)} albums")
    for s in songs[:2]:
        a = s["attributes"]
        print("  song", s["id"], a["artistName"], "-", a["name"], "|", a.get("albumName"), a.get("releaseDate"),
              a.get("durationInMillis"), "isrc", a.get("isrc"), "| preview", (a.get("previews") or [{}])[0].get("url", "")[:40],
              "| url", a.get("url", "")[:50], "| art", a.get("artwork", {}).get("url", "")[:40])
    if albums:
        al = albums[0]
        tr = get(f"/v1/catalog/us/albums/{al['id']}/tracks")["data"]
        print("  album", al["id"], al["attributes"]["name"], "->", len(tr), "tracks:", [x["attributes"]["name"] for x in tr[:4]])
print(f"apple {time.time() - t:.1f}s")

FEEDS = ["https://ukvibe.org/feed/", "https://www.jazzviews.net/feed", "https://www.brownswoodrecordings.com/feed",
         "https://daily.bandcamp.com/feed", "https://www.theguardian.com/music/jazz/rss", "https://www.jazzwise.com/feed",
         "https://londonjazznews.com/feed"]
t = time.time()
run = run_actor(gw, ACTORS["rss"], actor_input("rss", FEEDS, datetime.now(UTC) - timedelta(days=7)), cap_usd=0.05, timeout_s=180)
by = {}
for it in run.items:
    by.setdefault(it.get("feed_url"), []).append(it)
print(f"rss {run.status} {time.time() - t:.1f}s ${run.usd:.4f} items={len(run.items)}")
for f in FEEDS:
    items = by.get(f, [])
    print(f"  {len(items):3d}  {f}", "|", (items[0].get("item_title") or "")[:70] if items else "")
t = time.time()
run = run_actor(gw, ACTORS["subreddit"], actor_input("subreddit", ["Jazz"], datetime.now(UTC) - timedelta(days=2)), cap_usd=0.05)
posts = [i for i in run.items if i.get("dataType", i.get("type")) != "comment"]
print(f"r/Jazz {run.status} {time.time() - t:.1f}s ${run.usd:.4f} items={len(run.items)}; sample:", [(p.get("title") or "")[:50] for p in posts[:3]])
