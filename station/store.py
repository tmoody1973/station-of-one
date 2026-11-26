"""SQLite on the Sprite: posts, every Jev decision, per-source cursors, what aired."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_DB = Path("data/station.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY, source TEXT, beat TEXT, kind TEXT, author TEXT, title TEXT, url TEXT,
  text TEXT, posted_at TEXT, engagement_json TEXT, visibility TEXT, scraped_at TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  post_id TEXT, question_id TEXT, answer_type TEXT, value TEXT, probability REAL,
  confidence REAL, raw TEXT, model TEXT, asked_at TEXT,
  PRIMARY KEY (post_id, question_id, asked_at));
CREATE TABLE IF NOT EXISTS source_state (source_key TEXT PRIMARY KEY, last_success_at TEXT);
CREATE TABLE IF NOT EXISTS aired (
  post_id TEXT, newscast_id TEXT, part TEXT, score_matter_week REAL, aired_at TEXT);
"""


@dataclass(frozen=True)
class Post:
    id: str
    source: str
    beat: str
    kind: str  # "story" | "comment"
    author: str | None
    title: str
    url: str
    text: str
    posted_at: str
    engagement: dict
    visibility: str


def open_db(path: Path = DEFAULT_DB) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.executescript(SCHEMA)
    return db


def _now() -> str:
    return datetime.now(UTC).isoformat()


def upsert_posts(db: sqlite3.Connection, posts: Iterable[Post]) -> list[Post]:
    """Insert posts not seen before; return only the new ones, in input order."""
    new: list[Post] = []
    for p in posts:
        cur = db.execute(
            "INSERT OR IGNORE INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.id, p.source, p.beat, p.kind, p.author, p.title, p.url, p.text, p.posted_at,
             json.dumps(p.engagement), p.visibility, _now()))
        if cur.rowcount:
            new.append(p)
    db.commit()
    return new


def record_decision(db: sqlite3.Connection, post_id: str, question_id: str, answer: dict,
                    model: str, asked_at: str) -> None:
    if answer["type"] == "noul":
        prob = float(answer["noul"])
        value, conf = ("yes" if prob >= 0.5 else "no"), None
    elif answer["type"] == "choice":
        value = answer["choice"]
        prob, conf = float(answer["probabilities"][value]), answer.get("confidence")
    else:  # score
        value, prob, conf = str(answer["score"]), None, answer.get("confidence")
    db.execute("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?,?,?)",
               (post_id, question_id, answer["type"], value, prob, conf, json.dumps(answer), model, asked_at))
    db.commit()


def local_midnight_utc(now_utc: datetime, tz: str) -> datetime:
    local = now_utc.astimezone(ZoneInfo(tz))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def posts_read_since(db: sqlite3.Connection, since_utc: datetime) -> int:
    return db.execute("SELECT COUNT(*) FROM posts WHERE scraped_at >= ?", (since_utc.isoformat(),)).fetchone()[0]


def get_cursor(db: sqlite3.Connection, key: str) -> datetime | None:
    row = db.execute("SELECT last_success_at FROM source_state WHERE source_key = ?", (key,)).fetchone()
    return datetime.fromisoformat(row[0]) if row else None


def set_cursor(db: sqlite3.Connection, key: str, when: datetime) -> None:
    db.execute("INSERT OR REPLACE INTO source_state VALUES (?, ?)", (key, when.isoformat()))
    db.commit()


def record_aired(db: sqlite3.Connection, newscast_id: str, stories: Iterable[tuple[str, str, float]],
                 aired_at: str) -> None:
    db.executemany("INSERT INTO aired VALUES (?,?,?,?,?)",
                   [(pid, newscast_id, part, score, aired_at) for pid, part, score in stories])
    db.commit()


def post_from_row(row: tuple) -> Post:
    (pid, source, beat, kind, author, title, url, text, posted_at, engagement_json, visibility) = row[:11]
    return Post(pid, source, beat, kind, author, title, url, text, posted_at, json.loads(engagement_json or "{}"), visibility)


def aired_posts_since(db: sqlite3.Connection, since_utc: datetime) -> list[Post]:
    rows = db.execute(
        "SELECT p.id, p.source, p.beat, p.kind, p.author, p.title, p.url, p.text, p.posted_at, p.engagement_json,"
        " p.visibility FROM aired a JOIN posts p ON p.id = a.post_id WHERE a.aired_at >= ? ORDER BY a.aired_at",
        (since_utc.isoformat(),)).fetchall()
    return [post_from_row(r) for r in rows]
