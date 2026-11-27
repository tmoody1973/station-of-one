"""The scheduler (plan B1, Task 5): fills one hour of a station's clock from its rotation.

For each music slot: the songs in the slot's category that are rested and pass the hard rules (artist gap,
no two long songs back to back, energy never jumping two levels), ordered by the soft rules (vocal balance,
then era alternation; these give way first) and then by longest rest. An empty slot falls back through the
station's categories in config order. Fixed points (:00 and :30) are never late: a song that
would cross one is swapped for a shorter one, and time left over goes to the segment's break. Hard rules and
rest never relax; a slot nothing can fill stays empty. A language model never picks a song here.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from station.radio.model import StationConfig, normalize
from station.radio.program import era

SPOKEN_MS = {"id": 8000, "id_tease": 12000, "break": 25000, "backsell": 30000}
FIXED_MINUTES = (0, 30)  # :00 and :30 start on time; other clock segments follow on (no dead air after the news)
NEW_DAYS = 7  # "N" on a station without an N category: a C song added in the last 7 days


@dataclass(frozen=True)
class QueueItem:
    starts_at: str  # UTC, ISO
    kind: str  # song | id | id_tease | news | break | backsell
    candidate_id: str | None
    song_id: str | None
    duration_ms: int
    category: str | None
    note: str
    source_url: str


def _songs(db: sqlite3.Connection, station_id: str) -> list[dict]:
    rows = db.execute(
        "SELECT ro.candidate_id, ro.category, COALESCE(ro.energy, 2), ro.vocal, ro.last_played_at, ro.added_at, c.song_id, "
        "c.duration_ms, COALESCE(c.matched_artist, c.artist), c.release_date, ro.source_note, fi.feed, fi.title, fi.link "
        "FROM rotation ro JOIN candidates c ON c.id = ro.candidate_id LEFT JOIN feed_items fi ON fi.id = c.feed_item_id "
        "WHERE ro.station_id = ? AND c.duration_ms > 0 AND c.song_id IS NOT NULL ORDER BY ro.candidate_id", (station_id,)).fetchall()
    return [{"id": r[0], "category": r[1], "energy": r[2], "vocal": r[3], "last_played": r[4], "added_at": r[5],
             "song_id": r[6], "duration_ms": r[7], "artist": normalize(r[8]), "released": r[9],
             "note": r[10] or (f"Found in {r[11]}: {r[12]}" if r[11] else ""), "source_url": "" if r[10] else (r[13] or "")}
            for r in rows]


def _existing(db, station_id, start: datetime, end: datetime) -> list[QueueItem]:
    rows = db.execute("SELECT starts_at, kind, candidate_id, song_id, duration_ms, category, note, source_url FROM queue "
                      "WHERE station_id = ? AND starts_at >= ? AND starts_at < ? ORDER BY starts_at",
                      (station_id, start.isoformat(), end.isoformat())).fetchall()
    return [QueueItem(*r) for r in rows]


class _Hour:
    """What the hard and soft rules look at: recent artists (with times), the previous song, rests."""

    def __init__(self, station: StationConfig, db, start: datetime):
        sep = station.separation or {}
        self.gap = timedelta(hours=sep.get("artist_hours", 3))
        self.long_ms = sep.get("long_ms", 420000)
        self.step = sep.get("max_energy_step", 1)
        self.rest = {c.code: timedelta(hours=c.rest_hours) for c in station.rotation.categories}
        self.artists: list[tuple[datetime, str]] = []
        for when, artist in db.execute(
                "SELECT q.starts_at, COALESCE(c.matched_artist, c.artist) FROM queue q JOIN candidates c ON c.id = q.candidate_id "
                "WHERE q.station_id = ? AND q.kind = 'song' AND q.starts_at >= ? AND q.starts_at < ?",
                (station.id, (start - self.gap).isoformat(), start.isoformat())):
            self.artists.append((datetime.fromisoformat(when), normalize(artist)))
        prev = db.execute("SELECT q.candidate_id, q.duration_ms, COALESCE(ro.energy, 2), ro.vocal, c.release_date FROM queue q "
                          "JOIN rotation ro ON ro.candidate_id = q.candidate_id AND ro.station_id = q.station_id "
                          "JOIN candidates c ON c.id = q.candidate_id WHERE q.station_id = ? AND q.kind = 'song' AND q.starts_at < ? "
                          "ORDER BY q.starts_at DESC LIMIT 1", (station.id, start.isoformat())).fetchone()
        self.prev = {"id": prev[0], "duration_ms": prev[1], "energy": prev[2], "vocal": prev[3], "released": prev[4]} if prev else None
        self.adjacent = False  # was the previous item a song (for "no two long songs back to back")
        self.played: dict[str, datetime] = {}

    def allowed(self, s: dict, at: datetime, category_rest: str) -> bool:
        last = self.played.get(s["id"]) or (datetime.fromisoformat(s["last_played"]) if s["last_played"] else None)
        if last and at - last < self.rest.get(category_rest, timedelta(0)):
            return False
        if any(a == s["artist"] and at - when < self.gap for when, a in self.artists):
            return False
        if self.prev:
            if self.adjacent and self.prev["duration_ms"] >= self.long_ms and s["duration_ms"] >= self.long_ms:
                return False
            if abs(self.prev["energy"] - s["energy"]) > self.step:
                return False
        return True

    def soft(self, s: dict, today) -> int:
        """Higher is better. Vocal balance outweighs era alternation, so era gives way first."""
        if not self.prev:
            return 0
        vocal = 2 if s["vocal"] is None or self.prev["vocal"] is None or s["vocal"] != self.prev["vocal"] else 0
        eras = 1 if era(s["released"], today) != era(self.prev["released"], today) else 0
        return vocal + eras

    def take(self, s: dict, at: datetime) -> None:
        self.artists.append((at, s["artist"]))
        self.played[s["id"]] = at
        self.prev = s
        self.adjacent = True


def _pool(songs, slot: str, codes: list[str], at: datetime) -> list[tuple[str, list[dict]]]:
    """Where a slot looks, in order: its own category, then every category in config order."""
    if slot == "N" and "N" not in codes:
        recent = [s for s in songs if s["category"] == "C" and s["added_at"] and at - datetime.fromisoformat(s["added_at"]) <= timedelta(days=NEW_DAYS)]
        first = [("N", recent)]
    else:
        first = [(slot, [s for s in songs if s["category"] == slot])]
    return first + [(c, [s for s in songs if s["category"] == c]) for c in codes if c != slot]


def schedule_hour(station: StationConfig, db: sqlite3.Connection, hour_start_local: datetime, news_ms: int = 0) -> list[QueueItem]:
    """Fill one local hour of the station's clock; write queue rows; count plays. An hour already in the queue is returned as is."""
    start = hour_start_local.astimezone(UTC)
    end = start + timedelta(hours=1)
    done = _existing(db, station.id, start, end)
    if done:
        return done
    clock = station.clock_for(hour_start_local.hour)  # local wall-clock hour: daylight saving can't double a clock
    songs = _songs(db, station.id)
    codes = [c.code for c in station.rotation.categories]
    rules = _Hour(station, db, start)
    used: set[str] = set()
    items: list[QueueItem] = []
    segments: list[tuple[int, tuple[str, ...]]] = []
    for minute, slots in clock.segments:  # fold floating segments (:05, :55) into the fixed block before them
        if minute in FIXED_MINUTES or not segments:
            segments.append((minute, tuple(slots)))
        else:
            segments[-1] = (segments[-1][0], segments[-1][1] + tuple(slots))
    for n, (minute, slots) in enumerate(segments):
        seg_start = start + timedelta(minutes=minute)
        seg_end = start + timedelta(minutes=segments[n + 1][0]) if n + 1 < len(segments) else end
        cursor, seg_items = seg_start, []
        tail = len(slots)  # trailing spoken items (the backsell) stay last
        while tail and (slots[tail - 1] in SPOKEN_MS or slots[tail - 1] == "news"):
            tail -= 1
        extra = tuple(x for x in slots if x not in SPOKEN_MS and x != "news")  # room left: more from the block's categories
        slots = slots[:tail] + extra + slots[tail:]
        for k, slot in enumerate(slots):
            if slot in SPOKEN_MS or slot == "news":
                ms = news_ms if slot == "news" else SPOKEN_MS[slot]
                if not ms:
                    continue  # no newscast this hour (or news off): nothing to air
                seg_items.append(QueueItem(cursor.isoformat(), slot, None, None, ms, None, "", ""))
                cursor += timedelta(milliseconds=ms)
                rules.adjacent = False
                continue
            reserve = sum(news_ms if s == "news" else SPOKEN_MS.get(s, 0) for s in slots[k + 1:])
            room = (seg_end - cursor).total_seconds() * 1000 - reserve
            pick = None
            for cat, pool in _pool(songs, slot, codes, cursor):
                fits = [s for s in pool if s["id"] not in used and s["duration_ms"] <= room
                        and rules.allowed(s, cursor, s["category"])]
                if fits:
                    rested_first = sorted(fits, key=lambda s: (-rules.soft(s, cursor.date()), s["last_played"] or "", s["id"]))
                    pick = (cat, rested_first[0])
                    break
            if not pick:
                continue  # nothing eligible fits: the time goes to the break
            cat, s = pick
            used.add(s["id"])
            rules.take(s, cursor)
            seg_items.append(QueueItem(cursor.isoformat(), "song", s["id"], s["song_id"], s["duration_ms"], cat, s["note"], s["source_url"]))
            cursor += timedelta(milliseconds=s["duration_ms"])
        items += _close_gap(seg_items, seg_end - cursor)
    _write(db, station.id, items)
    return items


def _close_gap(seg: list[QueueItem], gap: timedelta) -> list[QueueItem]:
    """Give unfilled time to the segment's last break, sliding what follows it, so the next fixed point is exact."""
    breaks = [i for i, it in enumerate(seg) if it.kind == "break"]
    if gap <= timedelta(0) or not breaks:
        return seg
    b = breaks[-1]
    out = seg[:b] + [QueueItem(**{**seg[b].__dict__, "duration_ms": seg[b].duration_ms + int(gap.total_seconds() * 1000)})]
    for it in seg[b + 1:]:
        out.append(QueueItem(**{**it.__dict__, "starts_at": (datetime.fromisoformat(it.starts_at) + gap).isoformat()}))
    return out


def _write(db: sqlite3.Connection, station_id: str, items: list[QueueItem]) -> None:
    for it in items:
        db.execute("INSERT INTO queue (station_id, starts_at, kind, candidate_id, song_id, duration_ms, category, note, source_url) "
                   "VALUES (?,?,?,?,?,?,?,?,?)", (station_id, it.starts_at, it.kind, it.candidate_id, it.song_id, it.duration_ms,
                                                   it.category, it.note, it.source_url))
        if it.kind == "song":
            db.execute("UPDATE rotation SET plays = COALESCE(plays, 0) + 1, last_played_at = ? WHERE station_id = ? AND candidate_id = ?",
                       (it.starts_at, station_id, it.candidate_id))
    db.commit()
