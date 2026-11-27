"""Publisher preview photos for story pages (plan 2026-11-27-story-pages, Task 3; decisions 004 and 006).

One Apify cheerio-scraper run per hour reads the og:image (or twitter:image) of each story's linked article.
The photo is only ever shown from the publisher's own address, credited and linked; it is never copied.
Social links (Reddit, Bluesky, Hacker News, X) are skipped: those stories get an illustration instead.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

from station.gateway import GatewayError
from station.steps.scrape import ScrapeError, run_actor

ACTOR = "apify~cheerio-scraper"
SOCIAL_HOSTS = ("reddit.com", "bsky.app", "news.ycombinator.com", "x.com", "twitter.com")
LOGO_HINTS = ("logo", "favicon")
PAGE_FUNCTION = """async function pageFunction(context) {
  const { $, request } = context;
  const pick = (sel) => $(sel).attr('content') || null;
  return { url: request.url, image: pick('meta[property="og:image"]') || pick('meta[name="twitter:image"]') };
}"""


def _social(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS)


def lookup_urls(stories: list[dict]) -> list[str]:
    urls: list[str] = []
    for s in stories:
        url = (s.get("sources") or [{}])[0].get("url") or ""
        if url.startswith(("http://", "https://")) and not _social(url) and url not in urls:
            urls.append(url)
    return urls


def clean_image(page_url: str, image: str | None) -> str | None:
    if not image or not image.strip():
        return None
    url = urljoin(page_url, image.strip())
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    path = parsed.path.lower()
    # ponytail: a name heuristic for site-wide logos; a size check would need downloading the image
    if any(h in path for h in LOGO_HINTS) or path.endswith((".svg", ".ico")):
        return None
    return url


def preview_images(gw, urls: list[str]) -> tuple[dict[str, str], float]:
    if not urls:
        return {}, 0.0
    try:
        run = run_actor(gw, ACTOR, {"startUrls": [{"url": u} for u in urls], "pageFunction": PAGE_FUNCTION,
                                    "maxCrawlingDepth": 0, "linkSelector": "",
                                    "proxyConfiguration": {"useApifyProxy": True}}, cap_usd=0.10, timeout_s=120)
    except (ScrapeError, GatewayError):
        return {}, 0.0  # no photos this hour; every story falls back to an illustration
    found = {}
    for item in run.items:
        page, image = item.get("url") or "", clean_image(item.get("url") or "", item.get("image"))
        if page in urls and image:
            found[page] = image
    return found, run.usd
