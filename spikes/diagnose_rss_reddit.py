"""Why so few RSS/Reddit posts? Run each Actor once over the last 2 h and show per-feed status."""
import json
from collections import Counter
from datetime import UTC, datetime, timedelta

from station.config import load_prefs
from station.gateway import Gateway
from station.steps.scrape import ACTORS, _beat_lookup, actor_input, run_actor

gw, prefs = Gateway(), load_prefs()
since = datetime.now(UTC) - timedelta(hours=2)
refs = _beat_lookup(prefs)
rss = run_actor(gw, ACTORS["rss"], actor_input("rss", list(refs["rss"]), since))
print("RSS input filterByDate:", actor_input("rss", ["x"], since)["filterByDate"], "| items:", len(rss.items), "| usd", rss.usd)
for i in rss.items:
    if i.get("type") == "feed_summary":
        print(f"  {i.get('status'):10} items={i.get('items_count'):>3} latest={i.get('latest_item_date')}  {i.get('feed_url')}  {i.get('error') or ''}")
red_in = actor_input("subreddit", list(refs["subreddit"]), since)
print("\nReddit input:", json.dumps(red_in))
red = run_actor(gw, ACTORS["subreddit"], red_in)
print("Reddit items:", len(red.items), Counter((i.get("subreddit") or "?", i["type"]) for i in red.items))
print("warnings:", {w for i in red.items for w in (i.get("warnings") or [])})
