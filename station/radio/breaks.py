"""What the host says between songs (Plan B2, Task 3). Station IDs and teases are templates; breaks and back-announces
are written by the newscast's writer model from cited facts only, then Jev checks the script against its facts
(PRD "Voice breaks and news": cite or cut; back-announce, one fact, where it was found, tease what's next)."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from station.config import Prefs
from station.gateway import GatewayError
from station.radio.meeting import MODEL as JEV
from station.radio.model import StationConfig
from station.store import record_decision

CUT_AT = 0.3  # Jev's probability that a script states something beyond its facts, at or above which it is cut
MIN_WORDS, MAX_WORDS = 25, 110
RULES = ("You are the on-air host of {name}, a music station programmed by an agent. Write one voice break of 55 to 75 "
         "words, plain spoken English, no lists, no URLs, no stage directions. Back-announce what just played (artist and "
         "title), give exactly one fact from the facts provided, naming where it comes from, and tease what is next. Use only "
         "the facts provided; if none fits, say nothing beyond the back-announce. Never claim to have been anywhere or met "
         "anyone: you are an agent. One idea only.")


def id_text(station: StationConfig, prefs: Prefs, n: int) -> str:
    lines = prefs.station.id_lines_newscast
    return f"{station.name}. {lines[n % len(lines)]}"


def _said(s: dict) -> str:
    return f"{s.get('artist', '')} with {s.get('title', '')}"


def plain_back_announce(station: StationConfig, prev: list[dict], nxt: dict | None) -> str:
    """The break with nothing beyond the playlist: what played, what's next, the station."""
    parts = []
    if prev:
        parts.append(f"That was {_said(prev[-1])}" + (f", and before it, {_said(prev[-2])}" if len(prev) > 1 else "") + ".")
    if nxt:
        parts.append(f"Coming up, {_said(nxt)}.")
    parts.append(f"This is {station.name}.")
    return " ".join(parts)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", text or "")).strip()


def _write(gw, prefs: Prefs, station: StationConfig, prev: list[dict], nxt: dict | None, facts: list[dict]) -> str:
    user = {"just_played": [{"artist": s.get("artist"), "title": s.get("title")} for s in prev[-2:]],
            "next": {"artist": nxt.get("artist"), "title": nxt.get("title")} if nxt else None,
            "facts": [{"fact": f["text"], "source": f["source_name"]} for f in facts]}
    reply = gw.json("POST", "ollama", "/api/chat", {
        "model": prefs.writer.model, "stream": False, "think": False,
        "messages": [{"role": "system", "content": RULES.format(name=station.name)}, {"role": "user", "content": repr(user)}]})
    return _clean(reply["message"]["content"])


def _beyond_facts(gw, text: str, facts: list[dict], prev: list[dict], nxt: dict | None) -> tuple[float, dict, str]:
    playlist = {"just_played": [{"artist": s.get("artist"), "title": s.get("title")} for s in prev[-2:]],
                "next": {"artist": nxt.get("artist"), "title": nxt.get("title")} if nxt else None}
    resp = gw.json("POST", "typesafe", "/v1/systemone", {"model": JEV,
        "state": {"script": text, "facts": [f["text"] for f in facts], "playlist": playlist},
        "questions": {"beyond_facts": {"type": "noul", "instructions": "Does `script` state any fact about the music or the artists "
                                       "that is not in `facts`? Naming the songs and artists in `playlist`, the station's name, "
                                       "and mood or opinion words (warm, classic, a groove) are not facts and don't count."}}})
    answer = resp["answers"]["beyond_facts"]
    return float(answer["noul"]), answer, resp.get("model") or JEV


def script_for(gw, db: sqlite3.Connection, station: StationConfig, item: dict, prev_songs: list[dict], next_song: dict | None,
               prefs: Prefs, facts: list[dict]) -> dict:
    """The words for one spoken queue item: {"text", "sources": [{url, name}], "kind"}. A "news" item has no script."""
    kind, at = item["kind"], datetime.fromisoformat(item["starts_at"])
    if kind == "news":
        return {"text": "", "sources": [], "kind": kind}
    if kind in ("id", "id_tease"):
        text = id_text(station, prefs, at.hour)
        if kind == "id_tease":
            first, last = (int(t.split(":")[0]) for t in (prefs.station.first_newscast, prefs.station.last_newscast))
            text += " The news is at the top of the hour." if first <= at.hour + 1 <= last else f" More {station.name} after this."
        return {"text": text, "sources": [], "kind": kind}
    plain = {"text": plain_back_announce(station, prev_songs, next_song), "sources": [], "kind": kind}
    facts = [f for f in facts if str(f.get("source_url", "")).startswith(("http://", "https://"))][:2]  # cite or cut
    if not facts:
        return plain
    try:
        text = _write(gw, prefs, station, prev_songs, next_song, facts)
        named = prev_songs and any(x and x.lower() in text.lower() for x in (prev_songs[-1].get("title"), prev_songs[-1].get("artist")))
        if not named or not MIN_WORDS <= len(text.split()) <= MAX_WORDS:
            return plain
        p, answer, model = _beyond_facts(gw, text, facts, prev_songs, next_song)
    except (GatewayError, KeyError, TypeError, ValueError):
        return plain  # no script, or no check: the plain back-announce is always safe
    record_decision(db, f"radio:{station.id}:{item['starts_at']}", "break:beyond_facts", answer, model, at.isoformat())
    if p >= CUT_AT:
        return plain
    return {"text": text, "sources": [{"url": f["source_url"], "name": f["source_name"]} for f in facts], "kind": kind}
