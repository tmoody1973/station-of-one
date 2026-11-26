"""Corrections (spec §4, decided Nov 26: grade every story that aired a week earlier).

For each story aired seven local days ago: Pinecone finds this week's most similar posts among what
the station already scraped (no extra scraping), and Jev answers, in one request, whether each story
is still being discussed. 50% or higher counts as "held up". The on-air segment and the page box are
written by code from Jev's answers. "Not found in the feeds we read" is all a miss can claim.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from station.steps.dedupe import INDEX, NAMESPACE, embed_text, similar
from station.steps.judge import MODEL
from station.steps.write import Chapter, Turn
from station.store import Post, post_from_row

STILL_MIN, FOLLOWUP_MIN, MAX_FOLLOWUPS = 0.5, 0.45, 5
COLUMNS = "p.id, p.source, p.beat, p.kind, p.author, p.title, p.url, p.text, p.posted_at, p.engagement_json, p.visibility, p.image"


@dataclass(frozen=True)
class Call:
    post: Post
    said: float  # Jev's "likely to matter in a week" when it aired
    aired_at: str
    newscast_id: str


def due_calls(db: sqlite3.Connection, day: str, tz: str) -> list[Call]:
    start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo(tz)) - timedelta(days=7)
    s, e = (t.astimezone(ZoneInfo("UTC")).isoformat() for t in (start, start + timedelta(days=1)))
    rows = db.execute(f"SELECT {COLUMNS}, a.score_matter_week, a.aired_at, a.newscast_id FROM aired a "
                      "JOIN posts p ON p.id = a.post_id WHERE a.aired_at >= ? AND a.aired_at < ? ORDER BY a.aired_at, p.id",
                      (s, e)).fetchall()
    return [Call(post_from_row(r[:12]), float(r[12]), r[13], r[14]) for r in rows]


def followups(gw, call: Call, db: sqlite3.Connection, since_utc: datetime) -> list[Post]:
    hits = [(pid, sc) for pid, sc in similar(gw, INDEX, NAMESPACE, embed_text(call.post), top_k=10)
            if pid != call.post.id and sc >= FOLLOWUP_MIN]
    out = []
    for pid, _ in hits:
        row = db.execute(f"SELECT {COLUMNS} FROM posts p WHERE p.id = ? AND p.scraped_at >= ?",
                         (pid, since_utc.isoformat())).fetchone()
        if row:
            out.append(post_from_row(row))
    return out[:MAX_FOLLOWUPS]


def grade(gw, items: list[tuple[Call, list[Post]]]) -> tuple[list[dict], str | None]:
    if not items:
        return [], None
    state = {"calls": [{"story": {"title": c.post.title, "source": c.post.source, "text": c.post.text[:600]},
                        "recent_posts": [{"title": p.title, "source": p.source, "text": p.text[:400]} for p in posts]}
                       for c, posts in items]}
    questions = {f"still_{i}": {"type": "noul", "instructions":
                                f"A week after it aired, is the story in `calls[{i}].story` still being discussed, "
                                f"judging by `calls[{i}].recent_posts`? No recent posts means it was not found this week."}
                 for i in range(len(items))}
    resp = gw.json("POST", "typesafe", "/v1/systemone", {"model": MODEL, "state": state, "questions": questions})
    out = []
    for i, (c, posts) in enumerate(items):
        p = float(resp["answers"][f"still_{i}"]["noul"])
        out.append({"post_id": c.post.id, "title": c.post.title, "url": c.post.url, "said": c.said, "p_still": p,
                    "held_up": p >= STILL_MIN, "newscast_id": c.newscast_id,
                    "followups": [{"id": f.id, "title": f.title, "url": f.url} for f in posts]})
    return out, resp.get("model")


def summarize(day: str, items: list[dict], backfill: bool, model: str | None) -> dict:
    held = sum(1 for i in items if i["held_up"])
    week_of = (datetime.fromisoformat(day) - timedelta(days=7)).date().isoformat()
    return {"day": day, "week_of": week_of, "backfill": backfill, "called": len(items), "held": held,
            "faded": len(items) - held, "items": items, "model": model}


def _was(n: int) -> str:
    return f"{n} was" if n == 1 else f"{n} were"


def corrections_chapter(report: dict) -> Chapter:
    n, held, faded = report["called"], report["held"], report["faded"]
    text = (f"Corrections. A week ago, this station called {n} stor{'y' if n == 1 else 'ies'} likely to matter a week later; "
            f"in the feeds we read this week, {_was(held)} still being discussed, and {faded} {'was' if faded == 1 else 'were'} not.")
    missed = sorted((i for i in report["items"] if not i["held_up"]), key=lambda i: -i["said"])
    if missed:
        m = missed[0]
        text += f" Our strongest miss: {' '.join(m['title'].split()[:12])}. We said {round(m['said'] * 100)} percent."
    if report.get("backfill"):
        text += " These calls were made on last week's posts, scored this week."
    return Chapter(0, "corrections", "Corrections", None, (Turn("host", text),))
