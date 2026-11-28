"""The music meeting (plan B1, Task 4): Jev decides adds, moves up and burn-out; code applies the station's
ladder (config "meeting"), the category sizes, a 25% churn cap per category and a floor under the top category.
Every Jev answer is logged with record_decision; every change gets a `meeting` row with its reason."""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from station.gateway import GatewayError
from station.radio.buzz import buzz
from station.radio.model import StationConfig
from station.radio.program import era
from station.radio.scout import DEEPEN_FEED
from station.steps.judge import MODEL
from station.store import record_decision

ADD_MIN = UP_MIN = BURN_MIN = 0.6
FIT_FLOOR = 0.5
BURN_DAYS, AGE_DAYS, CATALOG_YEARS = 28, 365, 10
CHURN = 0.25
BATCH = 25
TZ = "America/Chicago"
QUESTIONS = {
    "add": "Should `songs[{i}]` join the rotation of a station whose brief is `station.brief`, starting now?",
    "up": "Has `songs[{i}]` earned more airplay on this station (moving up from its current category)?",
    "burned": "Has `songs[{i}]` been played so much on this station that listeners are likely tired of it?",
}


STYLE_DESCRIPTIONS = {  # ONE Jazz's styles (Tarik's jazz library README), for Jev's style question
    "contemporary": "Current US jazz",
    "uk_jazz": "The current UK jazz scene",
    "spiritual_avant": "Spiritual, cosmic or avant-garde jazz",
    "jazz_funk_fusion": "Jazz-funk or fusion",
    "heritage": "Classic jazz from the 1940s to the 1970s",
    "vocal": "Jazz singing",
    "latin_brazilian_afro": "Latin, Brazilian or Afro jazz",
    "not_jazz": "Not jazz: pop, house, hip-hop or other music with no real jazz in it",
}


def _ask_styles(gw, station, songs: list[dict], db, now, notes) -> dict[str, str]:
    """Jev's style for each song (a choice among the station's styles, or not_jazz), logged; {candidate: style}."""
    criteria = {k: v for k, v in STYLE_DESCRIPTIONS.items() if k in (station.styles or {}) or k == "not_jazz"}
    out: dict[str, str] = {}
    for start in range(0, len(songs), BATCH):
        batch = songs[start:start + BATCH]
        questions = {f"style_{i}": {"type": "choice", "instructions": f"Which style of jazz is the recording `songs[{i}]`?",
                                    "criteria": criteria} for i in range(len(batch))}
        try:
            resp = gw.json("POST", "typesafe", "/v1/systemone",
                           {"model": MODEL, "state": {"station": {"brief": station.brief}, "songs": batch}, "questions": questions})
            answers = [(s["id"], resp["answers"][f"style_{i}"]) for i, s in enumerate(batch)]
        except (GatewayError, KeyError, TypeError) as e:
            notes.append(f"meeting: Jev style question failed for {len(batch)} songs: {str(e)[:100]}")
            continue
        for cid, a in answers:
            record_decision(db, f"radio:{cid}", "meeting:style", a, resp.get("model") or MODEL, now.isoformat())
            out[cid] = a.get("choice", "")
    return out


@dataclass
class MeetingResult:
    adds: list[str] = field(default_factory=list)
    moves: list[tuple[str, str, str]] = field(default_factory=list)  # (candidate, from, to)
    drops: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


SONG = ("SELECT c.id, c.matched_artist, c.matched_title, c.release_date, sc.fit_score, COALESCE(fi.feed, 'library') "
        "FROM candidates c LEFT JOIN station_candidates sc ON sc.candidate_id = c.id AND sc.station_id = ? "
        "LEFT JOIN feed_items fi ON fi.id = c.feed_item_id ")


def _song(db, station, row, now, category=None, since=None) -> dict:
    cid, artist, title, released, fit, source = row
    days = (now - datetime.fromisoformat(since)).days if since else 0
    return {"id": cid, "artist": artist, "title": title, "category": category, "fit": fit, "source": source,
            "era": era(released, now.date()), "buzz": buzz(db, station.id, artist or "", now - timedelta(days=14)),
            "days_in_category": days}


def _ask(gw, station, asks: list[tuple[str, dict]], db, now, notes) -> dict[tuple[str, str], float]:
    """Jev's answers as {(kind, candidate): p}. A failed batch is a note; its songs are simply not moved."""
    out: dict[tuple[str, str], float] = {}
    for start in range(0, len(asks), BATCH):
        batch = asks[start:start + BATCH]
        state = {"station": {"brief": station.brief, "name": station.name}, "songs": [s for _, s in batch]}
        questions = {f"{k}_{i}": {"type": "noul", "instructions": QUESTIONS[k].format(i=i)} for i, (k, _) in enumerate(batch)}
        try:
            resp = gw.json("POST", "typesafe", "/v1/systemone", {"model": MODEL, "state": state, "questions": questions})
            answers = [(k, s["id"], resp["answers"][f"{k}_{i}"]) for i, (k, s) in enumerate(batch)]
            ps = [float(a["noul"]) for _, _, a in answers]
        except (GatewayError, KeyError, TypeError, ValueError) as e:
            notes.append(f"meeting: Jev failed for {len(batch)} questions: {str(e)[:100]}")
            continue
        for (k, cid, a), p in zip(answers, ps):
            record_decision(db, f"radio:{cid}", f"meeting:{k}", a, resp.get("model") or MODEL, now.isoformat())
            out[(k, cid)] = p
    return out


def music_meeting(gw, station: StationConfig, db: sqlite3.Connection, now: datetime) -> MeetingResult:
    rules, res = station.meeting or {}, MeetingResult()
    if not rules:
        res.notes.append("no meeting rules for this station")
        return res
    sid, held = station.id, now.isoformat()
    db.execute("INSERT INTO meeting (station_id, held_at) VALUES (?, ?)", (sid, held))  # held, even if nothing changes (review I1)
    db.commit()
    members = [_song(db, station, r[:6], now, r[6], r[7]) for r in db.execute(
        "SELECT c.id, c.matched_artist, c.matched_title, c.release_date, sc.fit_score, COALESCE(fi.feed, 'library'), "
        "ro.category, COALESCE(ro.moved_at, ro.added_at) FROM rotation ro JOIN candidates c ON c.id = ro.candidate_id "
        "LEFT JOIN station_candidates sc ON sc.candidate_id = c.id AND sc.station_id = ro.station_id "
        "LEFT JOIN feed_items fi ON fi.id = c.feed_item_id WHERE ro.station_id = ? ORDER BY c.id", (sid,))]
    addable = [_song(db, station, r, now) for r in db.execute(
        SONG + "WHERE sc.station_id = ? AND c.status = 'resolved' AND sc.fit_score >= ? AND c.id NOT IN "
               "(SELECT candidate_id FROM rotation WHERE station_id = ?) ORDER BY sc.fit_score DESC, c.id",
        (sid, sid, FIT_FLOOR, sid))]
    asks = [("add", s) for s in addable]
    asks += [("up", s) for s in members if s["category"] in rules["up"]]
    asks += [("burned", s) for s in members if s["category"] in rules["burn"]]
    p = _ask(gw, station, asks, db, now, res.notes)

    size = {c.code: c.size for c in station.rotation.categories}
    count = {c: 0 for c in size}
    for s in members:
        count[s["category"]] = count.get(s["category"], 0) + 1
    budget = {c: max(1, math.floor(CHURN * n)) for c, n in count.items()}
    top_min = size.get(rules["top"], 0) // 2

    def log(cid, action, frm, to, prob, reason):
        db.execute("INSERT INTO meeting (station_id, held_at, candidate_id, action, from_cat, to_cat, p, reason) VALUES (?,?,?,?,?,?,?,?)",
                   (sid, held, cid, action, frm, to, prob, reason))

    def can_leave(frm):
        return budget.get(frm, 0) > 0 and not (frm == rules["top"] and count[frm] - 1 < top_min)

    def move(cid, frm, to, prob, reason):
        if not can_leave(frm):
            res.notes.append(f"{cid}: stays in {frm} ({reason}; churn cap or floor)")
            return
        if to is not None and count.get(to, 0) >= size.get(to, 0):  # like adds: a full category waits (review I2)
            res.notes.append(f"{cid}: stays in {frm} ({reason}; no room in {to})")
            return
        if to is None and cid.startswith("lib:"):  # Tarik's library is never dropped from the rotation
            res.notes.append(f"{cid}: kept in {frm} (library song; {reason})")
            return
        if to is None:
            db.execute("DELETE FROM rotation WHERE station_id = ? AND candidate_id = ?", (sid, cid))
            res.drops.append(cid)
        else:
            db.execute("UPDATE rotation SET category = ?, moved_at = ? WHERE station_id = ? AND candidate_id = ?", (to, held, sid, cid))
            res.moves.append((cid, frm, to))
            count[to] = count.get(to, 0) + 1
        count[frm] -= 1
        budget[frm] -= 1
        log(cid, "drop" if to is None else "move", frm, to, prob, reason)

    proposals = []  # departures: (p, candidate, from, to, reason)
    for s in members:
        cid, cat, days = s["id"], s["category"], s["days_in_category"]
        if cat in rules["burn"]:
            pb = p.get(("burned", cid), 0.0)
            if pb >= BURN_MIN:
                proposals.append((pb, cid, cat, rules["burn"][cat], f"Jev: burned out ({pb:.2f})"))
            elif days >= BURN_DAYS:
                proposals.append((1.0, cid, cat, rules["burn"][cat], f"{days} days in {cat}"))
        if cat in rules["age"] and days >= AGE_DAYS:
            proposals.append((1.0, cid, cat, rules["age"][cat], f"{days} days in {cat}"))
        if cat in rules["up"] and p.get(("up", cid), 0.0) >= UP_MIN:
            proposals.append((p[("up", cid)], cid, cat, rules["up"][cat], f"Jev: earned more airplay ({p[('up', cid)]:.2f})"))
    for prob, cid, frm, to, reason in sorted(proposals, key=lambda x: (-x[0], x[1])):
        move(cid, frm, to, prob, reason)

    styles = {}
    if station.styles:  # a styled station (ONE Jazz): Jev names each passing find's style before it can be added
        styles = _ask_styles(gw, station, [s for s in addable if p.get(("add", s["id"]), 0.0) >= ADD_MIN], db, now, res.notes)
    catalog_before = f"{now.year - CATALOG_YEARS:04d}{now.strftime('-%m-%d')}"
    for s in sorted(addable, key=lambda s: (-p.get(("add", s["id"]), 0.0), s["id"])):
        pa = p.get(("add", s["id"]), 0.0)
        if pa < ADD_MIN:
            continue
        style = styles.get(s["id"]) if station.styles else None
        if station.styles and style not in station.styles:
            res.notes.append(f"{s['id']}: not added (Jev: {'not jazz' if style == 'not_jazz' else 'no style'})")
            continue
        released = db.execute("SELECT release_date FROM candidates WHERE id = ?", (s["id"],)).fetchone()[0] or ""
        deepen = s["source"] == DEEPEN_FEED  # catalog deepening for a thin style: never the New category
        to = rules["catalog"] if deepen or (released and released < catalog_before) else rules["new"]
        if count.get(to, 0) >= size.get(to, 0):
            res.notes.append(f"{s['id']}: no room in {to}")
            continue
        db.execute("INSERT INTO rotation (station_id, candidate_id, category, added_at, moved_at, style) VALUES (?,?,?,?,?,?)",
                   (sid, s["id"], to, held, held, style))
        count[to] = count.get(to, 0) + 1
        res.adds.append(s["id"])
        log(s["id"], "add", None, to, pa, f"Jev: join the rotation ({pa:.2f})" + (" as a catalog record" if to == rules["catalog"] else ""))

    for cat, cap in size.items():  # over size: the lowest-fit songs step down (or out)
        over = count.get(cat, 0) - cap
        if over > 0:
            lowest = db.execute("SELECT ro.candidate_id, COALESCE(sc.fit_score, 0) FROM rotation ro LEFT JOIN station_candidates sc "
                                "ON sc.station_id = ro.station_id AND sc.candidate_id = ro.candidate_id WHERE ro.station_id = ? "
                                "AND ro.category = ? ORDER BY 2, ro.candidate_id LIMIT ?", (sid, cat, over)).fetchall()
            for cid, fit in lowest:
                move(cid, cat, rules["down"].get(cat), fit, f"{cat} over its size ({cap})")
    db.commit()
    return res


def meeting_due(db: sqlite3.Connection, station: StationConfig, now: datetime, tz: str = TZ) -> bool:
    """Daily in the station's first 7 days, then Mondays; never before 6 am local; once per local day."""
    local = now.astimezone(ZoneInfo(tz))
    if local.hour < 6:
        return False
    last = db.execute("SELECT MAX(held_at) FROM meeting WHERE station_id = ?", (station.id,)).fetchone()[0]
    if last and datetime.fromisoformat(last).astimezone(ZoneInfo(tz)).date() == local.date():
        return False
    started = db.execute("SELECT MIN(added_at) FROM rotation WHERE station_id = ?", (station.id,)).fetchone()[0]
    first_week = started is None or now - datetime.fromisoformat(started) < timedelta(days=7)
    return first_week or local.weekday() == 0
