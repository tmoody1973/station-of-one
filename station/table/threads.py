"""Table step 1: yesterday's comment threads. A comment belongs to the story in the same source whose
title it names ("Comment on: <story title>", set by the scrapers)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from station.store import Post, post_from_row

COLUMNS = "id, source, beat, kind, author, title, url, text, posted_at, engagement_json, visibility, image"
MAX_COMMENTS = 40


@dataclass(frozen=True)
class Thread:
    story: Post
    comments: tuple[Post, ...]


def _day_bounds(day: str, tz: str) -> tuple[str, str]:
    start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo(tz))
    return start.astimezone(ZoneInfo("UTC")).isoformat(), (start + timedelta(days=1)).astimezone(ZoneInfo("UTC")).isoformat()


def _points(p: Post) -> float:
    v = p.engagement.get("points")
    return float(v) if isinstance(v, (int, float)) else 0.0


def threads(db: sqlite3.Connection, day: str, tz: str, min_comments: int = 6) -> list[Thread]:
    start, end = _day_bounds(day, tz)
    rows = db.execute(f"SELECT {COLUMNS} FROM posts WHERE scraped_at >= ? AND scraped_at < ?", (start, end)).fetchall()
    posts = [post_from_row(r) for r in rows]
    by_parent: dict[tuple[str, str], list[Post]] = {}
    for c in posts:
        if c.kind == "comment" and c.title.startswith("Comment on: "):
            by_parent.setdefault((c.source, c.title.removeprefix("Comment on: ")), []).append(c)
    out = []
    for s in posts:
        comments = by_parent.get((s.source, s.title), []) if s.kind == "story" else []
        if len(comments) >= min_comments:
            ranked = sorted(comments, key=lambda c: (-_points(c), c.posted_at, c.id))[:MAX_COMMENTS]
            out.append(Thread(s, tuple(ranked)))
    return sorted(out, key=lambda t: -len(t.comments))
