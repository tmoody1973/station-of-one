"""stations.json for the station strip (site shell, Task 5): News plus every music station, with what is on
now and next. Written by the page step (new newscast) and the radio step (new music set), served from the bucket
at /data/stations.json; shell.js re-reads it every minute and renders it as text."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from station.config import Prefs
from station.radio.model import STATIONS_ROOT, load_station

RADIO_ROOT = Path("data/radio")


def _line(t: dict) -> str:
    return f"{t.get('artist', '')} · {t.get('title', '')}"


def _clock(dt: datetime) -> str:
    return dt.strftime("%-I:%M %p").lower()


def _next_newscast(newscast: dict, prefs: Prefs) -> str:
    """The next newscast's start time: the next hour, or the first newscast tomorrow after the last one."""
    hour = datetime.fromisoformat(newscast["hour_local"])
    first, last = (int(t.split(":")[0]) for t in (prefs.station.first_newscast, prefs.station.last_newscast))
    nxt = hour + timedelta(hours=1)
    if nxt.hour > last or nxt.hour < first:
        nxt = (hour + timedelta(days=1 if hour.hour >= first else 0)).replace(hour=first, minute=0)
    return _clock(nxt)


def _music_now(t: dict) -> dict:
    return {"at": t.get("at", ""), "title": _line(t), "art": t.get("artwork_url") or ""}


def stations_json(prefs: Prefs, newscast: dict | None, radio_root: Path = RADIO_ROOT,
                  stations_root: Path = STATIONS_ROOT) -> dict:
    from station.steps.page import _hour_label, audio_path  # page imports this module too
    out = []
    if newscast:
        lead = (newscast.get("stories") or [{}])[0].get("headline", "")
        label = f"{_hour_label(newscast)} newscast"
        out.append({"id": "news", "kind": "news", "name": "News", "on_now": f"{label}: {lead}" if lead else label,
                    "now": {"at": _hour_label(newscast), "title": lead or label, "art": "/cover-one.png"},
                    "next": {"at": _next_newscast(newscast, prefs), "title": "The next newscast"},
                    "description": f"{prefs.station.show_name}: five minutes on the hour, 7 am to 7 pm Central, "
                                               "machine-edited from public posts.", "page": "/index.html",
                    "play": {"src": audio_path(newscast), "title": lead or label, "label": f"On air · {label}",
                             "chapters": newscast.get("chapters", []), "kind": "newscast", "start": 0}})
    configs = [load_station(p.stem, stations_root) for p in sorted(Path(stations_root).glob("*.json"))]
    for st in sorted(configs, key=lambda s: (s.type != "flagship", s.name)):  # the flagship first
        latest = Path(radio_root) / st.id / "latest.json"
        if not latest.exists():
            continue  # never published: no chip linking to a page that isn't there
        try:  # a half-written or odd file shows the station quietly; it never stops the front page
            tracks = json.loads(latest.read_text())["block"]["tracks"] if latest.exists() else []
        except (OSError, ValueError, KeyError, TypeError):
            tracks = []
        entry = {"id": st.id, "kind": "music", "name": st.name, "on_now": _line(tracks[0]) if tracks else "",
                 "now": _music_now(tracks[0]) if tracks else {"at": "", "title": "", "art": ""},
                 "next": _music_now(tracks[1]) if len(tracks) > 1 else None,
                 "description": st.brief, "page": f"/radio/{st.id}/index.html"}
        if st.programmer == "clock":  # the name box tunes in live (Plan C); the browser picks now/next from the schedule
            entry["play"] = {"kind": "station", "src": f"/data/radio/{st.id}/queue.json", "title": st.name, "label": f"{st.name} · live"}
            entry["schedule"] = [{"starts_at": t.get("starts_at"), "ends_at": t.get("ends_at"), "at": t.get("at", ""),
                                  "song_id": str(t.get("song_id") or ""), "title": t.get("title", ""), "artist": t.get("artist", ""),
                                  "art": t.get("artwork_url") or ""} for t in tracks if t.get("starts_at")]
        out.append(entry)
    return {"updated": datetime.now(UTC).isoformat(timespec="seconds"), "stations": out, "playlists": "/playlists/index.html"}
