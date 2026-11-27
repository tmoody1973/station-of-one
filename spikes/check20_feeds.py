"""Check 20 (Rhythm Lab plan, Task 1): do the flagship's candidate feeds return items through the same Apify RSS
actor the stations use? One run, last 7 days, capped at $0.10. Writes nothing to the database."""
from collections import Counter
from datetime import UTC, datetime, timedelta

from station.gateway import Gateway
from station.steps.scrape import ACTORS, actor_input, normalize, run_actor

FEEDS = ["https://daily.bandcamp.com/feed", "https://www.stonesthrow.com/feed/", "https://www.brownswoodrecordings.com/feed",
         "https://djmag.com/feed", "https://thequietus.com/feed/"]  # XLR8R and Fact dropped: no posts since May / Sept 2026
since = datetime.now(UTC) - timedelta(days=14)
run = run_actor(Gateway(), ACTORS["rss"], actor_input("rss", FEEDS, since), cap_usd=0.10, timeout_s=180)
posts = [p for item in run.items for p in normalize("rss", item, "rhythm-lab")]
print("status", run.status, "| usd", run.usd if hasattr(run, "usd") else run[3], "| items", len(run.items))
for source, n in Counter(p.source for p in posts).most_common():
    print(f"  {n:3d}  {source}")
for p in posts[:6]:
    print("   e.g.", p.source, "|", p.title[:80])
