"""Check 20, part 2: the raw actor items per feed (which feeds return nothing, and what the dropped items are)."""
import json
from datetime import UTC, datetime, timedelta

from station.gateway import Gateway
from station.steps.scrape import ACTORS, actor_input, run_actor

FEEDS = ["https://www.stonesthrow.com/feed/", "https://xlr8r.com/feed/", "https://www.factmag.com/feed/"]
since = datetime.now(UTC) - timedelta(days=7)
run = run_actor(Gateway(), ACTORS["rss"], actor_input("rss", FEEDS, since), cap_usd=0.05, timeout_s=180)
print("status", run.status, "items", len(run.items))
for it in run.items[:12]:
    print(json.dumps({k: (str(v)[:70]) for k, v in it.items() if k in ("feedUrl", "feedTitle", "title", "link", "pubDate", "publishedAt", "isoDate", "error", "errorMessage")}))
