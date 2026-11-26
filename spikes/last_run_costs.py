"""Free read: status, memory and charge of the latest runs."""
import json

from gw import call, connection

b = connection("apify")["gateway_base_url"].rstrip("/")
s, _, r = call("GET", f"{b}/v2/actors/constructive_calm~hacker-news-scraper/runs?desc=1&limit=1")
print("per-actor run list ->", s, r[:120])
s, _, r = call("GET", f"{b}/v2/actor-runs?desc=1&limit=3")
print("account run list ->", s)
if s == 200:
    for item in json.loads(r)["data"]["items"]:
        _, _, r2 = call("GET", f"{b}/v2/actor-runs/{item['id']}")
        d = json.loads(r2)["data"]
        print(d.get("actId"), d["status"], "usd", d.get("usageTotalUsd"), "mem", d["options"].get("memoryMbytes"),
              d.get("chargedEventCounts"))
