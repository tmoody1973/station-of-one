"""Check 1: Jev answers from the Sprite through the TypeSafe AI connector.

Sends one post with our six per-post questions (mapped per docs/RESEARCH-NOTES.md §6.4)
plus GET /v1/models. Prints the real request and response so they can be recorded.
Shapes confirmed in https://docs.typesafe.ai/api/system-one.md (Context7 /typesafe-docs/typesafeai).
Cost: one call, roughly 1k input tokens at $0.042 per million.

Run:  sprite exec -s brave-indigo-lion -- python3 ~/spikes/check1_jev.py
"""
import json
import time

from gw import call, connection

conn = connection("typesafe")
base = conn["gateway_base_url"].rstrip("/")
print("connection entry:", json.dumps({k: v for k, v in conn.items() if k != "usage_snippet"}, indent=1))
print("usage_snippet:\n", conn.get("usage_snippet"))

status, _, raw = call("GET", f"{base}/v1/models")
print("\nGET /v1/models ->", status, raw.decode()[:800])

request = {
    "model": "jev-latest",
    "state": {
        "post": {
            "source": "Hacker News",
            "author": "example_user",
            "url": "https://news.ycombinator.com/item?id=0",
            "posted_at": "2026-11-26T14:05:00Z",
            "text": "Mozilla announces it will end support for the Firefox ESR 115 branch on "
                    "March 1, 2027, per its release calendar (link to mozilla.org in post).",
        },
        "earlier_posts": [
            {"source": "Reddit r/firefox", "text": "Firefox ESR 115 support ends in March 2027 according to Mozilla."}
        ],
    },
    "questions": {
        "matter_week": {"type": "noul",
                        "instructions": "Will the news in `post` still matter to listeners a week from now?"},
        "new_or_reaction": {"type": "choice",
                            "instructions": "Is `post` new information, or a reaction to something already known?",
                            "criteria": {"new_information": "Reports a new fact, release, decision or event",
                                         "reaction": "Comments on, jokes about or reacts to news already out"}},
        "part": {"type": "choice",
                 "instructions": "Which part of a five-minute newscast fits `post` best?",
                 "criteria": {"lead": "The most important story of the hour",
                              "story": "A regular short news story",
                              "overheard": "A notable single comment worth quoting",
                              "none": "Not suitable for the newscast"}},
        "primary_source": {"type": "noul",
                           "instructions": "Is the central claim in `post` supported by a linked primary source?"},
        "same_story": {"type": "noul",
                       "instructions": "Is `post` about the same story as `earlier_posts[0]`?"},
        "private_harm": {"type": "noul",
                         "instructions": "Could airing `post` harm a private individual?"},
        "seconds": {"type": "score",
                    "instructions": "How much airtime does `post` deserve in a newscast?",
                    "criteria": ["A one-line mention", "A short item with one fact",
                                 "A full story with context", "A story needing background and reaction"]},
    },
}
print("\nPOST /v1/systemone request:\n", json.dumps(request, indent=1))
t = time.time()
status, headers, raw = call("POST", f"{base}/v1/systemone", request)
print(f"\n-> {status} in {time.time() - t:.2f}s")
print("rate-limit/retry headers:", {k: v for k, v in headers.items()
                                    if "rate" in k.lower() or "retry" in k.lower()})
try:
    resp = json.loads(raw)
    print(json.dumps(resp, indent=1))
    if "answers" in resp and "seconds" in resp["answers"]:
        s = resp["answers"]["seconds"]["score"]  # float 0..n-1
        print("seconds mapped to 20-45:", round(20 + s / 3 * 25))
except json.JSONDecodeError:
    print(raw.decode()[:2000])
