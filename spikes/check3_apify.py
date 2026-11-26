"""Check 3: Apify covers the chosen sources. One run per candidate source type.

Each run: POST <gateway>/v2/actors/<id>/runs with a hard spend cap, poll, read the dataset
(maxTotalChargeUsd). Reports seconds, item count, a sample item's keys, and the run's charge.
Shapes from docs/RESEARCH-NOTES.md §6.8 (https://docs.apify.com/api/v2/actor-run-sync-get-dataset-items-post.md).
SPENDS APIFY CREDIT: capped at CAP_USD per run. Ask before running.

Run one:  sprite exec -s brave-indigo-lion -- bash -c 'cd ~/spikes && python3 check3_apify.py rss'
Run all:  ... python3 check3_apify.py all
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone

from gw import call, connection

CAP_USD = 0.25
two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)

CANDIDATES = {
    # Per-feed pricing; tests whether one Actor can cover HN, Reddit, local news and YouTube via RSS.
    "rss": ("santamaria-automations~rss-feed-reader", {
        "feedUrls": [
            "https://hnrss.org/frontpage",
            "https://www.reddit.com/r/LocalLLaMA/new/.rss",
            "https://www.reddit.com/r/milwaukee/new/.rss",
        ],
        "maxItemsPerFeed": 25,
        "includeContent": True,
        "filterByDate": two_hours_ago.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }),
    "hn": ("constructive_calm~hacker-news-scraper", {
        "mode": "topstories", "maxItems": 20, "includeComments": True, "maxCommentDepth": 1,
        "dateFromUnix": int(two_hours_ago.timestamp()),
    }),
    "reddit": ("automation-lab~reddit-scraper", {
        "urls": ["https://www.reddit.com/r/LocalLLaMA/"], "sort": "new", "postedAfter": "2 hours",
        "maxPostsPerSource": 15, "includeComments": True, "maxCommentsPerPost": 2, "commentDepth": 1,
        "includeNsfw": False,
    }),
    # Round 2 (Nov 26): handles verified via public.api.bsky.app getProfile.
    "bluesky": ("blueskyscraper~bluesky-posts-scraper", {
        "mode": "posts",
        "handles": ["simonwillison.net", "github.com", "theverge.com", "niemanlab.org",
                    "current.org", "urbanmilwaukee.com", "wisconsinexaminer.com"],
        "maxResultsPerInput": 10, "postedAfter": two_hours_ago.strftime("%Y-%m-%d"),
        "includeReposts": False, "includeProfile": False, "monitoringStoreName": "station-one-spike",
    }),
    "gnews": ("lhotanova~google-news-scraper", {
        "query": "artificial intelligence", "language": "US:en", "openEndedDateRange": "2h",
        "maxItems": 10, "fetchArticleDetails": True,
    }),
    # Feeds verified Nov 26 by direct fetch (200, dated items); plus Google News RSS searches.
    "rss_full": ("santamaria-automations~rss-feed-reader", {
        "feedUrls": [
            "https://simonwillison.net/atom/everything/", "https://openai.com/news/rss.xml",
            "https://blog.google/innovation-and-ai/technology/ai/rss/", "https://huggingface.co/blog/feed.xml",
            "https://github.blog/feed/", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
            "https://feeds.arstechnica.com/arstechnica/technology-lab", "https://hnrss.org/frontpage",
            "https://current.org/feed/", "https://www.niemanlab.org/feed/", "https://www.poynter.org/feed/",
            "https://podnews.net/rss", "https://radioink.com/feed/", "https://www.cjr.org/feed",
            "https://pressgazette.co.uk/feed/",
            "https://urbanmilwaukee.com/feed/", "https://milwaukeenns.org/feed/",
            "https://wisconsinexaminer.com/feed/", "https://wisconsinwatch.org/feed/",
            "https://milwaukeerecord.com/feed/", "https://onmilwaukee.com/rss",
            "https://news.google.com/rss/search?q=artificial+intelligence+when:1h&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=Milwaukee+when:1h&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=%22public+radio%22+when:1h&hl=en-US&gl=US&ceid=US:en",
        ],
        "maxItemsPerFeed": 10, "includeContent": True,
        "filterByDate": two_hours_ago.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }),
}

which = sys.argv[1] if len(sys.argv) > 1 else "rss"
names = list(CANDIDATES) if which == "all" else which.split(",")
conn = connection("apify")
base = conn["gateway_base_url"].rstrip("/")
print("usage_snippet:\n", conn.get("usage_snippet"))

for name in names:
    actor, actor_input = CANDIDATES[name]
    # The connector refuses run-sync-get-dataset-items (403). Use start -> poll -> dataset,
    # as in the connector's usage_snippet.
    print(f"\n== {name}: {actor}\ninput: {json.dumps(actor_input)}")
    t = time.time()
    status, _, raw = call("POST", f"{base}/v2/actors/{actor}/runs?timeout=240&maxTotalChargeUsd={CAP_USD}",
                          actor_input)
    print(f"start -> {status}")
    if status != 201:
        print(raw.decode(errors="replace")[:1500])
        continue
    run = json.loads(raw)["data"]
    run_id = run["id"]
    print("run id:", run_id, "| options:", run.get("options"))
    while run["status"] in ("READY", "RUNNING", "TIMING-OUT", "ABORTING"):
        status, _, raw = call("GET", f"{base}/v2/actor-runs/{run_id}?waitForFinish=60", timeout=90)
        if status != 200:
            print("poll ->", status, raw.decode(errors="replace")[:500])
            break
        run = json.loads(raw)["data"]
        print(f"  {time.time() - t:.0f}s status {run['status']}")
    secs = time.time() - t
    status, _, raw = call("GET", f"{base}/v2/datasets/{run['defaultDatasetId']}/items?clean=1&format=json")
    items = json.loads(raw) if status == 200 else []
    print(f"finished {run['status']} in {secs:.1f}s | dataset -> {status} | items: {len(items)}")
    if items:
        print("sample keys:", sorted(items[0].keys()))
        print("sample item:", json.dumps(items[0])[:800])
    time.sleep(10)  # Apify: first response after completion can show preliminary costs
    status, _, raw = call("GET", f"{base}/v2/actor-runs/{run_id}")
    if status == 200:
        run = json.loads(raw)["data"]
        print("usageTotalUsd:", run.get("usageTotalUsd"), "| chargedEventCounts:", run.get("chargedEventCounts"))
