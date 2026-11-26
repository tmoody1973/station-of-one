"""Save Nov 26 spike payloads as test fixtures (free dataset reads). Run on the Sprite."""
import json
import os

from gw import call, connection

RUNS = {"apify_rss": "YhriFC0z5QovknSSM", "apify_hn": "T6bjjyxdYK7X3mdXl", "apify_reddit": "hAp038QPHLPTAjOzh"}
base = connection("apify")["gateway_base_url"].rstrip("/")
os.makedirs(os.path.expanduser("~/spikes/fixtures"), exist_ok=True)
for name, run_id in RUNS.items():
    _, _, raw = call("GET", f"{base}/v2/actor-runs/{run_id}")
    ds = json.loads(raw)["data"]["defaultDatasetId"]
    _, _, raw = call("GET", f"{base}/v2/datasets/{ds}/items?clean=0&format=json")
    items = json.loads(raw)
    path = os.path.expanduser(f"~/spikes/fixtures/{name}.json")
    json.dump(items, open(path, "w"), indent=1)
    print(name, len(items), os.path.getsize(path))
