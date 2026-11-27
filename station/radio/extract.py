"""Extractor (plan 2026-11-27-music-station-a, Task 4; PRD "Discovery pipeline" step 3).

Ollama reads feed items (8 per call) and lists only the music each one explicitly names: a track, or a
release (album/EP) when no track is named. Version strings ("VIP", "Live at ...", "Extended Mix") are kept
so the resolver can match them exactly. Anything without an artist and a title or release is dropped.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from station.gateway import GatewayError
from station.radio.poll import FeedItem

BATCH = 8
SYSTEM = """You extract music from feed items for a radio station's music library.
For each item, list only tracks and releases that the item explicitly names. Never guess, never add music
the item does not name, never invent a year or label. If an item names no music, return an empty list.
Reply with JSON only, in exactly this shape:
{"items": [{"id": "<item id>", "music": [{"kind": "track" or "release", "artist": "...", "title": "<track title or empty>",
 "release": "<album or EP title or empty>", "label": "<label or empty>", "year": <year number or null>,
 "version": "<version words such as VIP, remix, Live at ..., Extended Mix, or empty>"}]}]}
Use kind "release" for an album or EP with no specific track named."""


@dataclass(frozen=True)
class Extracted:
    kind: Literal["track", "release"]
    artist: str
    title: str
    release: str
    label: str
    year: int | None
    version: str


def _year(value) -> int | None:
    try:
        y = int(str(value)[:4])
    except (TypeError, ValueError):
        return None
    return y if 1900 <= y <= 2100 else None


def parse_reply(text: str, ids: set[str]) -> dict[str, list[Extracted]]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    data = json.loads(m.group(0))
    out: dict[str, list[Extracted]] = {}
    for entry in data.get("items") or []:
        if entry.get("id") not in ids:
            continue
        music = []
        for x in entry.get("music") or []:
            artist, title, release = (str(x.get(k) or "").strip() for k in ("artist", "title", "release"))
            kind = "track" if title else "release"
            if not artist or not (title or release):
                continue
            music.append(Extracted(kind, artist, title, release, str(x.get("label") or "").strip(), _year(x.get("year")),
                                   str(x.get("version") or "").strip()))
        out[entry["id"]] = music
    return out


def _messages(items: list[FeedItem]) -> list[dict]:
    body = "\n\n".join(f"ITEM id={it.id}\nFROM: {it.feed}\nTITLE: {it.title}\nTEXT: {it.excerpt}" for it in items)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": body}]


def extract(gw, model: str, items: list[FeedItem]) -> tuple[dict[str, list[Extracted]], list[str]]:
    found: dict[str, list[Extracted]] = {}
    notes: list[str] = []
    for start in range(0, len(items), BATCH):
        batch = items[start:start + BATCH]
        messages, ids, last = _messages(batch), {it.id for it in batch}, ""
        for _ in range(2):  # one retry, told what was wrong
            try:
                reply = gw.json("POST", "ollama", "/api/chat", {"model": model, "messages": messages, "stream": False,
                                                                "think": False, "options": {"temperature": 0}})["message"]["content"]
                found.update(parse_reply(reply, ids))
                break
            except GatewayError as e:
                last = f"writer error {e.status}"
                break
            except (ValueError, KeyError, TypeError) as e:
                last = str(e)[:80]
                messages = [*messages, {"role": "user", "content": "That was not valid JSON in the required shape. Reply with the JSON only."}]
        else:
            notes.append(f"extract dropped {len(batch)} items: {last}")
            continue
        if last.startswith("writer error"):
            notes.append(f"extract dropped {len(batch)} items: {last}")
    return found, notes
