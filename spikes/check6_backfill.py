"""Check 6: backfill for Corrections.

Scrape AI/dev Hacker News stories from one week ago (Nov 19, Central time) through Apify,
score each with Jev, and store every answer in SQLite so Sunday has real calls to grade.
Apify flow per check 3 (runs -> poll -> dataset; run-sync is refused by the connector).
Jev request shape per check 1. Spend: one Apify run capped at $0.25; ~60 Jev calls.

Run:  sprite exec -s brave-indigo-lion -- bash -c 'cd ~/spikes && python3 check6_backfill.py'
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from gw import call, connection

CENTRAL = ZoneInfo("America/Chicago")
# Day to backfill (Central), e.g. 2026-11-20; default is the original Nov 19 run.
DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-11-19"
DAY_START = datetime.fromisoformat(DAY).replace(tzinfo=CENTRAL)
DAY_END = datetime.fromtimestamp(DAY_START.timestamp() + 86400, CENTRAL)
ACTOR = "constructive_calm~hacker-news-scraper"
ACTOR_INPUT = {
    "mode": "search", "searchQuery": "AI", "searchTags": ["story"], "sortSearchBy": "relevance",
    "dateFromUnix": int(DAY_START.timestamp()), "dateToUnix": int(DAY_END.timestamp()),
    "minScore": 20, "maxItems": 60, "includeComments": False,
}
QUESTIONS = {
    "matter_week": {"type": "noul",
                    "instructions": "Will the news in `post` still matter to listeners a week from now?"},
    "new_or_reaction": {"type": "choice",
                        "instructions": "Is `post` new information, or a reaction to something already known?",
                        "criteria": {"new_information": "Reports a new fact, release, decision or event",
                                     "reaction": "Comments on, jokes about or reacts to news already out"}},
    "part": {"type": "choice", "instructions": "Which part of a five-minute newscast fits `post` best?",
             "criteria": {"lead": "The most important story of the hour",
                          "story": "A regular short news story",
                          "overheard": "A notable single comment worth quoting",
                          "none": "Not suitable for the newscast"}},
    "primary_source": {"type": "noul",
                       "instructions": "Is the central claim in `post` supported by a linked primary source?"},
    "private_harm": {"type": "noul", "instructions": "Could airing `post` harm a private individual?"},
}
DB = os.path.expanduser("~/spikes/check6/backfill.db" if DAY == "2026-11-19" else f"~/spikes/check6/backfill-{DAY}.db")
os.makedirs(os.path.dirname(DB), exist_ok=True)

db = sqlite3.connect(DB)
db.executescript("""
CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY, source TEXT, beat TEXT, author TEXT, title TEXT, url TEXT,
  text TEXT, points INTEGER, comments INTEGER, created_at TEXT, scraped_at TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  post_id TEXT, question_id TEXT, answer_type TEXT, value TEXT, probability REAL,
  confidence REAL, raw TEXT, model TEXT, asked_at TEXT,
  PRIMARY KEY (post_id, question_id));
""")

# 1. Scrape
apify = connection("apify")["gateway_base_url"].rstrip("/")
print("Apify input:", json.dumps(ACTOR_INPUT))
t = time.time()
status, _, raw = call("POST", f"{apify}/v2/actors/{ACTOR}/runs?timeout=240&maxTotalChargeUsd=0.25", ACTOR_INPUT)
if status != 201:
    raise SystemExit(f"start -> {status}: {raw.decode()[:800]}")
run = json.loads(raw)["data"]
while run["status"] in ("READY", "RUNNING", "TIMING-OUT", "ABORTING"):
    status, _, raw = call("GET", f"{apify}/v2/actor-runs/{run['id']}?waitForFinish=60", timeout=90)
    run = json.loads(raw)["data"]
_, _, raw = call("GET", f"{apify}/v2/datasets/{run['defaultDatasetId']}/items?clean=1&format=json")
items = json.loads(raw)
print(f"scrape {run['status']} in {time.time() - t:.1f}s, {len(items)} items")
scraped_at = datetime.now(timezone.utc).isoformat()
for it in items:
    db.execute("INSERT OR REPLACE INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
        f"hn:{it['id']}", "Hacker News", "ai-dev", it.get("by"), it.get("title"),
        it.get("url") or it.get("hnUrl"), it.get("text"), it.get("score"), it.get("descendants"),
        it.get("createdAt"), scraped_at))
db.commit()

# 2. Judge
jev = connection("typesafe")["gateway_base_url"].rstrip("/")
tokens = 0
t = time.time()
for it in items:
    post_id = f"hn:{it['id']}"
    state = {"post": {"source": "Hacker News", "title": it.get("title"), "url": it.get("url"),
                      "text": (it.get("text") or "")[:4000], "author": it.get("by"),
                      "points": it.get("score"), "comments": it.get("descendants")}}
    status, _, raw = call("POST", f"{jev}/v1/systemone",
                          {"model": "jev-latest", "state": state, "questions": QUESTIONS})
    if status != 200:
        print(post_id, "->", status, raw.decode()[:300])
        continue
    resp = json.loads(raw)
    tokens += resp.get("usage", {}).get("input_tokens", 0)
    asked_at = datetime.now(timezone.utc).isoformat()
    for qid, a in resp["answers"].items():
        if a["type"] == "noul":
            value, prob, conf = ("yes" if a["noul"] >= 0.5 else "no"), a["noul"], None
        else:
            value, prob, conf = a["choice"], a["probabilities"][a["choice"]], a.get("confidence")
        db.execute("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?,?,?)",
                   (post_id, qid, a["type"], value, prob, conf, json.dumps(a), resp["model"], asked_at))
db.commit()
print(f"judged {len(items)} posts in {time.time() - t:.1f}s, {tokens} input tokens "
      f"(≈ ${tokens * 0.042 / 1e6:.4f})")

# 3. Summary
time.sleep(10)
_, _, raw = call("GET", f"{apify}/v2/actor-runs/{run['id']}")
print("Apify charged:", json.loads(raw)["data"].get("usageTotalUsd"))
rows = db.execute("""SELECT p.title, d.probability FROM decisions d JOIN posts p ON p.id = d.post_id
                     WHERE d.question_id = 'matter_week' ORDER BY d.probability DESC""").fetchall()
calls_70 = [r for r in rows if r[1] >= 0.70]
print(f"matter_week calls at or above 0.70: {len(calls_70)} of {len(rows)}")
for title, p in rows[:8]:
    print(f"  {p:.2f}  {title[:90]}")
dropped = db.execute("SELECT COUNT(*) FROM decisions WHERE question_id='private_harm' AND probability >= 0.20").fetchone()[0]
print("private_harm at or above 0.20 (would be dropped):", dropped)
print("db:", DB)
