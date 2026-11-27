"""Music picks candidates (plan 2026-11-27-music-picks, Task 2; check 16).

YouTube: each channel's public RSS feed through the existing RSS reader actor (Shorts left out).
Bandcamp: each label's /music grid through the Cheerio Scraper; the grid carries the album id, so no
album pages are visited. Ids are validated here; the page builds players from the id alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import parse_qs, urlparse

from station.gateway import GatewayError
from station.steps.scrape import ACTORS, ScrapeError, actor_input, run_actor

YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALBUM_ID = re.compile(r"^\d{1,12}$")
RECENT = timedelta(days=14)
PER_LABEL = 3
PAGE_FUNCTION = """async function pageFunction(context) {
  const { $, request } = context;
  const items = [];
  $('li[data-item-id^="album-"]').slice(0, 6).each((i, el) => {
    const li = $(el);
    const title = li.find('p.title').clone().children().remove().end().text().trim();
    items.push({ id: li.attr('data-item-id').replace('album-', ''), title,
                 artist: li.find('.artist-override').text().trim(), href: li.find('a').attr('href') });
  });
  return { url: request.url, label: $('meta[property="og:title"]').attr('content') || null, items };
}"""


@dataclass(frozen=True)
class Pick:
    source: str
    kind: Literal["bandcamp", "youtube"]
    embed_id: str
    title: str
    artist: str
    url: str
    published_at: str


def youtube_id(url: str) -> str | None:
    u = urlparse(url or "")
    if u.hostname and u.hostname.endswith("youtu.be"):
        candidate = u.path.strip("/")
    elif u.path == "/watch":
        candidate = (parse_qs(u.query).get("v") or [""])[0]
    elif u.path.startswith(("/shorts/", "/embed/", "/live/")):
        candidate = u.path.split("/")[2]
    else:
        return None
    return candidate if YOUTUBE_ID.match(candidate) else None


def album_id(item: dict) -> str | None:
    value = str(item.get("id") or "")
    return value if ALBUM_ID.match(value) else None


def _http(url: str | None, fallback: str) -> str:
    return url if (url or "").startswith(("https://", "http://")) else fallback


def youtube_candidates(gw, channels: list[str], now: datetime | None = None) -> tuple[list[Pick], list[str]]:
    now = now or datetime.now(UTC)
    feeds = [f"https://www.youtube.com/feeds/videos.xml?channel_id={c}" for c in channels]
    try:
        run = run_actor(gw, ACTORS["rss"], actor_input("rss", feeds, now - RECENT), cap_usd=0.05, timeout_s=120)
    except (ScrapeError, GatewayError) as e:
        return [], [f"youtube candidates failed: {str(e)[:120]}"]
    picks = []
    for it in run.items:
        link = it.get("item_link") or ""
        vid = youtube_id(link)
        published = it.get("item_published") or ""
        if not vid or "/shorts/" in link:  # Shorts are vertical clips, mostly not music (check 16)
            continue
        try:
            if datetime.fromisoformat(published.replace("Z", "+00:00")) < now - RECENT:
                continue
        except ValueError:
            continue
        source = it.get("feed_title") or "YouTube"
        picks.append(Pick(source, "youtube", vid, it.get("item_title") or "", it.get("item_author") or source,
                          _http(link, ""), published))
    return picks, []


def bandcamp_candidates(gw, labels: list[str]) -> tuple[list[Pick], list[str]]:
    try:
        run = run_actor(gw, "apify~cheerio-scraper", {
            "startUrls": [{"url": f"https://{l}.bandcamp.com/music"} for l in labels], "pageFunction": PAGE_FUNCTION,
            "maxCrawlingDepth": 0, "linkSelector": "", "proxyConfiguration": {"useApifyProxy": True}},
            cap_usd=0.05, timeout_s=120)
    except (ScrapeError, GatewayError) as e:
        return [], [f"bandcamp candidates failed: {str(e)[:120]}"]
    picks, notes = [], []
    for page in run.items:
        page_url = page.get("url") or ""
        found = [it for it in page.get("items") or [] if album_id(it)][:PER_LABEL]
        if not found:
            notes.append(f"bandcamp: no albums on {page_url}")
            continue
        label = page.get("label") or (urlparse(page_url).hostname or "Bandcamp").split(".")[0]
        for it in found:
            picks.append(Pick(label, "bandcamp", album_id(it), (it.get("title") or "").strip(),
                              (it.get("artist") or "").strip() or label, _http(it.get("href"), page_url), ""))
    return picks, notes
