"""Free follow-up to check 3: which RSS feeds returned items, and why the others didn't."""
import json
import sys
from collections import Counter

from gw import call, connection

run_id = sys.argv[1]
b = connection("apify")["gateway_base_url"].rstrip("/")
_, _, r = call("GET", f"{b}/v2/actor-runs/{run_id}")
run = json.loads(r)["data"]
_, _, r = call("GET", f"{b}/v2/datasets/{run['defaultDatasetId']}/items?clean=0&format=json")
items = json.loads(r)
print(Counter((i.get("feed_url"), i.get("type")) for i in items))
for i in items:
    if i.get("type") != "feed_item":
        print(json.dumps(i)[:400])
s, _, r = call("GET", f"{b}/v2/actor-runs/{run_id}/log")
print("log ->", s)
print(r.decode(errors="replace")[-2000:])
