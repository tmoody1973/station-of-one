"""Step 1, scrape: Apify Actors through the gateway; new posts into SQLite.

Proven in check 3: the connector refuses run-sync-get-dataset-items (403), so every Actor
runs as start -> poll -> read dataset, with a hard spend cap per run.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from station.config import Prefs
from station.gateway import GatewayError
from station.store import Post, get_cursor, set_cursor, upsert_posts

ACTORS = {
    "hackernews": "constructive_calm~hacker-news-scraper",
    "subreddit": "automation-lab~reddit-scraper",
    "rss": "santamaria-automations~rss-feed-reader",
    "bluesky": "blueskyscraper~bluesky-posts-scraper",
    "googlenews": "lhotanova~google-news-scraper",
}
LOW_MEMORY = {"hackernews", "googlenews"}  # these default to 4 GB; start fee is charged per GB
# HN's front page is mostly older than an hour; read the last day and let the DB drop known posts.
HN_WINDOW = timedelta(hours=24)
FIRST_RUN_WINDOW = timedelta(hours=2)
HN_MEMORY_MB = 1024  # start fee is charged per GB of run memory (check 3, inferred)
ACTIVE = {"READY", "RUNNING", "TIMING-OUT", "ABORTING"}
TEXT_LIMIT = 4000


class ScrapeError(Exception):
    pass


@dataclass(frozen=True)
class ActorRun:
    items: list[dict]
    run_id: str
    status: str
    usd: float


@dataclass
class ScrapeResult:
    posts: list[Post]
    counts: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def plain(text: str | None) -> str:
    """HTML fragment -> plain text."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:TEXT_LIMIT]


def _iso_z(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def actor_input(source_type: str, refs: list[str], since: datetime) -> dict:
    if source_type == "hackernews":
        # Comments on (Tarik, Nov 26): ~700 top-level comments per run feed "posts read" and Overheard.
        return {"mode": refs[0], "maxItems": 20, "includeComments": True, "maxCommentDepth": 1,
                "dateFromUnix": int(since.timestamp())}
    if source_type == "subreddit":
        return {"urls": [f"https://www.reddit.com/r/{r}/" for r in refs], "sort": "new",
                "postedAfter": _iso_z(since), "maxPostsPerSource": 25, "includeComments": True,
                "maxCommentsPerPost": 3, "commentDepth": 1, "includeNsfw": False}
    if source_type == "rss":
        return {"feedUrls": refs, "maxItemsPerFeed": 25, "includeContent": True, "filterByDate": _iso_z(since)}
    if source_type == "bluesky":  # postedAfter is date-only; monitoringStoreName returns only unseen posts
        return {"mode": "posts", "handles": refs, "maxResultsPerInput": 20,
                "postedAfter": since.astimezone(UTC).strftime("%Y-%m-%d"), "includeReposts": False,
                "includeReplies": False, "includeProfile": False, "monitoringStoreName": "station-one"}
    if source_type == "googlenews":  # one query per run
        return {"query": refs[0], "language": "US:en", "openEndedDateRange": "2h", "maxItems": 15,
                "fetchArticleDetails": True}
    raise ValueError(f"unknown source type: {source_type}")


def runs_for(source_type: str, refs: list[str], since: datetime) -> list[dict]:
    if source_type == "googlenews":
        return [actor_input(source_type, [r], since) for r in refs]
    return [actor_input(source_type, refs, since)]


def run_actor(gw, actor_id: str, actor_input: dict, cap_usd: float = 0.25, memory_mb: int | None = None,
              timeout_s: int = 240) -> ActorRun:
    params = {"timeout": timeout_s, "maxTotalChargeUsd": cap_usd}
    if memory_mb:
        params["memory"] = memory_mb
    run = gw.json("POST", "apify", f"/v2/actors/{actor_id}/runs?{urlencode(params)}", actor_input)["data"]
    while run["status"] in ACTIVE:
        run = gw.json("GET", "apify", f"/v2/actor-runs/{run['id']}?waitForFinish=60", timeout=90)["data"]
    items = gw.json("GET", "apify", f"/v2/datasets/{run['defaultDatasetId']}/items?clean=1&format=json")
    if run["status"] != "SUCCEEDED" and not items:
        raise ScrapeError(f"{actor_id} ended {run['status']} with no items")
    # The connector refuses run-list endpoints, so cost is only readable from this run object.
    return ActorRun(items, run["id"], run["status"], float(run.get("usageTotalUsd") or 0))


def _hn(item: dict, beat: str) -> list[Post]:
    story = Post(id=f"hn:{item['id']}", source="Hacker News", beat=beat, kind="story", author=item.get("by"),
                 title=item.get("title") or "", url=item.get("url") or item.get("hnUrl") or "",
                 text=plain(item.get("text")), posted_at=item.get("createdAt") or "",
                 engagement={"points": item.get("score"), "comments": item.get("descendants")}, visibility="public")
    comments = [Post(id=f"hn:{c['id']}", source="Hacker News", beat=beat, kind="comment", author=c.get("by"),
                     title=f"Comment on: {story.title}", url=c.get("hnUrl") or "", text=plain(c.get("text")),
                     posted_at=c.get("createdAt") or "", engagement={}, visibility="public")
                for c in item.get("comments") or [] if c.get("text")]
    return [story, *comments]


def _subreddit_from(permalink: str) -> str:
    m = re.search(r"/r/([^/]+)/", permalink or "")
    return m.group(1) if m else "unknown"


def _reddit(item: dict, beat: str) -> list[Post]:
    if item.get("type") == "comment":
        sub = _subreddit_from(item.get("permalink", ""))
        return [Post(id=f"reddit:{item['id']}", source=f"Reddit r/{sub}", beat=beat, kind="comment",
                     author=item.get("author"), title=f"Comment on: {item.get('postTitle', '')}",
                     url=item.get("permalink") or "", text=plain(item.get("body")), posted_at=item.get("createdAt") or "",
                     engagement={"points": item.get("score")}, visibility="public")]
    sub = item.get("subreddit") or _subreddit_from(item.get("permalink", ""))
    return [Post(id=f"reddit:{item['id']}", source=f"Reddit r/{sub}", beat=beat, kind="story",
                 author=item.get("author"), title=item.get("title") or "", url=item.get("url") or item.get("permalink") or "",
                 text=plain(item.get("selfText")), posted_at=item.get("createdAt") or "",
                 engagement={"points": item.get("score"), "comments": item.get("numComments")}, visibility="public")]


def _rss(item: dict, beat: str) -> list[Post]:
    if item.get("type") != "feed_item":
        return []
    return [Post(id=f"rss:{item.get('item_guid') or item.get('item_link')}", source=item.get("feed_title") or "RSS",
                 beat=beat, kind="story", author=item.get("item_author"), title=item.get("item_title") or "",
                 url=item.get("item_link") or "", text=plain(item.get("item_text") or item.get("item_description")),
                 posted_at=item.get("item_published") or "", engagement={}, visibility="public")]


def _bluesky(item: dict, beat: str) -> list[Post]:
    if item.get("isRepost") or item.get("type", "post") != "post":
        return []
    text = item.get("text") or ""
    return [Post(id=f"bsky:{item['id']}", source=f"Bluesky @{item.get('handle')}", beat=beat,
                 kind="comment" if item.get("isReply") else "story", author=item.get("handle"),
                 title=text[:100], url=item.get("url") or "", text=text[:TEXT_LIMIT], posted_at=item.get("createdAt") or "",
                 engagement={"points": item.get("likeCount"), "comments": item.get("replyCount"),
                             "reposts": item.get("repostCount")}, visibility="public")]


def _gnews(item: dict, beat: str) -> list[Post]:
    return [Post(id=f"gnews:{item.get('guid') or item.get('link')}", source=item.get("source") or "Google News",
                 beat=beat, kind="story", author=None, title=item.get("title") or "", url=item.get("link") or "",
                 text="", posted_at=item.get("publishedAt") or "", engagement={}, visibility="public")]


def normalize(source_type: str, item: dict, beat_id: str) -> list[Post]:
    return {"hackernews": _hn, "subreddit": _reddit, "rss": _rss, "bluesky": _bluesky,
            "googlenews": _gnews}[source_type](item, beat_id)


def _beat_lookup(prefs: Prefs) -> dict[str, dict[str, str]]:
    """source type -> {ref: beat id}, newscast beats only."""
    out: dict[str, dict[str, str]] = {}
    for beat in prefs.beats:
        if beat.used_in != "newscast":
            continue
        for s in beat.sources:
            out.setdefault(s.type, {})[s.ref] = beat.id
    return out


def _beat_for(source_type: str, item: dict, refs: dict[str, str]) -> str:
    if source_type == "rss":
        return refs.get(item.get("feed_url", ""), next(iter(refs.values())))
    if source_type == "subreddit":
        sub = item.get("subreddit") or _subreddit_from(item.get("permalink", ""))
        return next((b for r, b in refs.items() if r.lower() == sub.lower()), next(iter(refs.values())))
    if source_type == "bluesky":
        return refs.get(item.get("handle", ""), next(iter(refs.values())))
    if source_type == "googlenews":
        return refs.get(item.get("query", ""), next(iter(refs.values())))
    return next(iter(refs.values()))


def scrape(gw, prefs: Prefs, db, now: datetime) -> ScrapeResult:
    result = ScrapeResult(posts=[])
    found = 0
    usd = 0.0
    run_ids: list[str] = []
    for source_type, refs in _beat_lookup(prefs).items():
        since = get_cursor(db, source_type) or now - FIRST_RUN_WINDOW
        if source_type == "hackernews":
            since = now - HN_WINDOW
        items: list[dict] = []
        succeeded = False
        for inp in runs_for(source_type, list(refs), since):
            try:
                run = run_actor(gw, ACTORS[source_type], inp,
                                memory_mb=HN_MEMORY_MB if source_type in LOW_MEMORY else None)
            except (GatewayError, ScrapeError) as e:
                result.notes.append(f"{source_type} failed: {e}")
                continue
            succeeded = True
            usd += run.usd
            run_ids.append(run.run_id)
            items += [{**i, "query": inp["query"]} if "query" in inp else i for i in run.items]
        if not succeeded:
            continue
        posts = [p for item in items for p in normalize(source_type, item, _beat_for(source_type, item, refs))]
        found += len(posts)
        new = upsert_posts(db, posts)
        result.posts.extend(new)
        result.counts[f"{source_type}_new"] = len(new)
        set_cursor(db, source_type, now)
    result.counts.update(new_posts=len(result.posts), seen=found, apify_usd=round(usd, 4), apify_runs=run_ids)
    return result
