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
CREATE TABLE IF NOT EXISTS table_episodes (
  day TEXT PRIMARY KEY, question TEXT, anchor REAL, uncle REAL, winner TEXT, story_id TEXT);
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
    image: str | None = None  # publisher's image URL; shown linked, never copied (decision 004)


def open_db(path: Path = DEFAULT_DB) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.executescript(SCHEMA)
    if "image" not in {r[1] for r in db.execute("PRAGMA table_info(posts)")}:
        db.execute("ALTER TABLE posts ADD COLUMN image TEXT")  # databases from before Nov 26 images
        db.commit()
    return db


def _now() -> str:
    return datetime.now(UTC).isoformat()


def upsert_posts(db: sqlite3.Connection, posts: Iterable[Post]) -> list[Post]:
    """Insert posts not seen before; return only the new ones, in input order."""
    new: list[Post] = []
    for p in posts:
        cur = db.execute(
            "INSERT OR IGNORE INTO posts (id, source, beat, kind, author, title, url, text, posted_at,"
            " engagement_json, visibility, scraped_at, image) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.id, p.source, p.beat, p.kind, p.author, p.title, p.url, p.text, p.posted_at,
             json.dumps(p.engagement), p.visibility, _now(), p.image))
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
        p = answer.get("probabilities", {}).get(value)
        prob, conf = (float(p) if p is not None else None), answer.get("confidence")
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
    """Row from an explicit column list: the 11 post fields, optionally image as the 12th (not SELECT *)."""
    (pid, source, beat, kind, author, title, url, text, posted_at, engagement_json, visibility) = row[:11]
    return Post(pid, source, beat, kind, author, title, url, text, posted_at, json.loads(engagement_json or "{}"),
                visibility, row[11] if len(row) > 11 else None)


def aired_posts_since(db: sqlite3.Connection, since_utc: datetime) -> list[Post]:
    rows = db.execute(
        "SELECT p.id, p.source, p.beat, p.kind, p.author, p.title, p.url, p.text, p.posted_at, p.engagement_json,"
        " p.visibility, p.image FROM aired a JOIN posts p ON p.id = a.post_id WHERE a.aired_at >= ? ORDER BY a.aired_at",
        (since_utc.isoformat(),)).fetchall()
    return [post_from_row(r) for r in rows]


def aired_count_since(db: sqlite3.Connection, since_utc: datetime) -> int:
    return db.execute("SELECT COUNT(*) FROM aired WHERE aired_at >= ?", (since_utc.isoformat(),)).fetchone()[0]


def recent_unaired_judged(db: sqlite3.Connection, since_utc: datetime) -> list[tuple[Post, dict, str]]:
    """Posts judged since `since_utc` that never aired, with their latest answer per question."""
    rows = db.execute(
        "SELECT d.post_id, d.question_id, d.raw, d.model FROM decisions d"
        " WHERE d.asked_at >= ? AND d.post_id NOT IN (SELECT post_id FROM aired)"
        " ORDER BY d.post_id, d.asked_at", (since_utc.isoformat(),)).fetchall()
    answers: dict[str, dict] = {}
    models: dict[str, str] = {}
    for post_id, qid, raw, model in rows:
        answers.setdefault(post_id, {})[qid] = json.loads(raw)
        models[post_id] = model
    out = []
    for post_id in sorted(answers):
        row = db.execute("SELECT id, source, beat, kind, author, title, url, text, posted_at, engagement_json, visibility,"
                         " image FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row:
            out.append((post_from_row(row), answers[post_id], models[post_id]))
    return out


def counts_by_beat(db: sqlite3.Connection, start_utc: datetime, end_utc: datetime) -> dict[str, tuple[int, int]]:
    """{beat: (posts scraped, stories aired)} in [start, end)."""
    s, e = start_utc.isoformat(), end_utc.isoformat()
    posts = dict(db.execute("SELECT beat, COUNT(*) FROM posts WHERE scraped_at >= ? AND scraped_at < ? GROUP BY beat",
                            (s, e)).fetchall())
    aired = dict(db.execute("SELECT p.beat, COUNT(*) FROM aired a JOIN posts p ON p.id = a.post_id"
                            " WHERE a.aired_at >= ? AND a.aired_at < ? GROUP BY p.beat", (s, e)).fetchall())
    return {b: (posts.get(b, 0), aired.get(b, 0)) for b in sorted(set(posts) | set(aired))}


def record_episode(db: sqlite3.Connection, day: str, question: str, anchor: float, uncle: float, winner: str,
                   story_id: str) -> None:
    """The Table's result for a day; a re-run of the same day replaces it."""
    db.execute("INSERT OR REPLACE INTO table_episodes VALUES (?,?,?,?,?,?)", (day, question, anchor, uncle, winner, story_id))
    db.commit()


def season_record(db: sqlite3.Connection, exclude_day: str | None = None) -> dict[str, int]:
    counts = dict(db.execute("SELECT winner, COUNT(*) FROM table_episodes WHERE day IS NOT ? GROUP BY winner",
                             (exclude_day,)).fetchall())
    return {k: counts.get(k, 0) for k in ("anchor", "uncle", "draw")}
