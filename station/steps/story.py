"""The story step (plan 2026-11-27-story-pages, Task 5): article + image for every aired story.

Runs after assemble. Image order: the scrape's own photo, else the publisher's preview photo (Apify), else a
Bauhaus illustration (Gemini). Every failure costs only that story's article or image and becomes a note.
Writes stories.json; illustrations go to site/art/ so publish uploads them with the pages.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from station.config import Prefs
from station.runs import write_json
from station.steps.article import write_article
from station.steps.corrections import COLUMNS
from station.steps.illustrate import illustrate
from station.steps.photos import clean_image, lookup_urls, preview_images
from station.store import Post, post_from_row

CONCURRENCY = 3


def _source_posts(db: sqlite3.Connection, story: dict) -> list[Post]:
    ids = [s["post_id"] for s in story.get("sources", [])] or [story["id"]]
    rows = db.execute(f"SELECT {COLUMNS} FROM posts p WHERE p.id IN ({','.join('?' * len(ids))})", ids).fetchall()
    return [post_from_row(r) for r in rows]


def _photo(story: dict, src: str) -> dict:
    """Credit the publisher whose page the photo comes from, not the site that linked it (review I1)."""
    link = (story.get("sources") or [{}])[0].get("url") or ""
    host = (urlparse(link).hostname or "").removeprefix("www.")
    return {"kind": "photo", "src": src, "credit": host or "source", "link": link}


def make_stories(gw, run: Path, prefs: Prefs, db: sqlite3.Connection) -> tuple[dict, dict]:
    newscast = json.loads((run / "newscast.json").read_text())
    stories = newscast["stories"]
    posts = {s["id"]: _source_posts(db, s) for s in stories}  # read before the threads: sqlite stays on this one
    beats = {b.id: b.name for b in prefs.beats}
    notes: list[str] = []

    def article(s: dict) -> tuple[list[str] | None, str | None]:
        try:
            return write_article(gw, prefs.writer.model, s, posts[s["id"]])
        except Exception as e:  # noqa: BLE001 - review I2: any failure costs only this story's article
            return None, f"article dropped for {s['id']}: {type(e).__name__}: {str(e)[:120]}"

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        articles = list(pool.map(article, stories))
    notes += [note for _, note in articles if note]

    try:
        found, apify_usd = preview_images(gw, lookup_urls(stories))
    except Exception as e:  # noqa: BLE001 - no photos this hour; stories fall back to illustrations
        found, apify_usd = {}, 0.0
        notes.append(f"photo lookup failed: {type(e).__name__}: {str(e)[:120]}")
    images: dict[str, dict | None] = {}
    for s in stories:
        first_url = (s.get("sources") or [{}])[0].get("url") or ""
        # the publisher's full-size photo beats the scrape's own (often a ~140 px thumbnail); review M1
        src = found.get(first_url) or clean_image(first_url, s.get("image"))
        images[s["id"]] = _photo(s, src) if src else None

    def draw(s: dict) -> tuple[str, dict | None]:
        stem = f"{run.name}-{hashlib.sha1(s['id'].encode()).hexdigest()[:8]}"
        try:
            path = illustrate(gw, s.get("headline") or "", beats.get(s.get("beat_id"), "news"), run / "site" / "art", stem)
        except Exception as e:  # noqa: BLE001 - any failure costs only this story's image
            notes.append(f"illustration dropped for {s['id']}: {type(e).__name__}: {str(e)[:120]}")
            return s["id"], None
        return s["id"], {"kind": "illustration", "src": f"/art/{path.name}"}

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        images.update(dict(pool.map(draw, [s for s in stories if images[s["id"]] is None])))

    out = {s["id"]: {"paragraphs": paragraphs, "image": images[s["id"]]} for s, (paragraphs, _) in zip(stories, articles)}
    write_json(run, "stories.json", out)
    kinds = [i["kind"] for i in images.values() if i]
    counts = {"articles": sum(1 for p, _ in articles if p), "photos": kinds.count("photo"),
              "illustrations": kinds.count("illustration"), "apify_usd": apify_usd, "notes": notes}
    return out, counts
