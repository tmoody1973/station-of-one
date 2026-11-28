"""Sampler page (plan 2026-11-27-music-station-a, Task 8; PRD "Without Apple Music").

The programmed block as a tracklist: each track's note and source link, a 30-second Apple preview that
plays only when tapped (one at a time, never advancing on its own), and a "Listen on Apple Music" link.
"""
from __future__ import annotations

import math

from station.config import Prefs
from station.radio.model import Clock, StationConfig
from station.radio.program import Block
from station.steps.page import env


def sampler_path(station_id: str) -> str:
    return f"radio/{station_id}/index.html"


def meeting_path(station_id: str) -> str:
    return f"radio/{station_id}/meeting/index.html"


def render_sampler(station: StationConfig, block: Block, counts: dict, prefs: Prefs, on_now: dict | None = None) -> str:
    minutes = round(sum(t["duration_ms"] for t in block.tracks) / 60000)
    return env().get_template("radio.html").render(st=station, block=block, counts=counts, minutes=minutes,
                                                   station=prefs.station, on_now=on_now)


def render_meeting(station: StationConfig, rows: list[dict], board: list[dict], prefs: Prefs) -> str:
    return env().get_template("meeting.html").render(st=station, rows=rows, board=board, station=prefs.station)


EXPLAINER_PATH = "radio/how-it-works/index.html"
SONG_MS = 240000  # a typical song, for drawing the clock
NEWS_MS = 165000
COLORS = ("var(--red)", "var(--yellow)", "var(--blue)", "#3a3833", "#9b9277", "#c9a227")


def _arc(cx: float, cy: float, r1: float, r2: float, a0: float, a1: float) -> str:
    """A ring segment from angle a0 to a1 (degrees, 0 at the top, clockwise)."""
    pt = lambda r, a: (cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a)))
    large = 1 if a1 - a0 > 180 else 0
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pt(r2, a0), pt(r2, a1), pt(r1, a1), pt(r1, a0)
    return f"M{x0:.1f},{y0:.1f} A{r2},{r2} 0 {large} 1 {x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f} A{r1},{r1} 0 {large} 0 {x3:.1f},{y3:.1f} Z"


def clock_arcs(station: StationConfig, clock: Clock) -> list[dict]:
    """Each clock slot as an arc, sized by its planned length within its half hour (the same lists the scheduler uses)."""
    from station.radio.scheduler import FIXED_MINUTES, SPOKEN_MS
    blocks: list[tuple[int, list[str]]] = []
    for minute, slots in clock.segments:
        if minute in FIXED_MINUTES or not blocks:
            blocks.append((minute, list(slots)))
        else:
            blocks[-1][1].extend(slots)
    color = {c.code: COLORS[i % len(COLORS)] for i, c in enumerate(station.rotation.categories)}
    arcs = []
    for n, (minute, slots) in enumerate(blocks):
        end = blocks[n + 1][0] if n + 1 < len(blocks) else 60
        lengths = [NEWS_MS if s == "news" else SPOKEN_MS.get(s, SONG_MS) for s in slots]
        a = minute * 6.0
        for slot, ms in zip(slots, lengths):
            span = (end - minute) * 6.0 * ms / sum(lengths)
            spoken = slot in SPOKEN_MS or slot == "news"
            arcs.append({"slot": slot, "d": _arc(120, 120, 64, 104, a, a + span - 0.4), "spoken": spoken,
                         "fill": "var(--paper)" if spoken else color.get(slot, color.get("C", COLORS[0]))})
            a += span
    return arcs


def render_explainer(station: StationConfig, counts: dict[str, int], last_meeting: str | None, prefs: Prefs) -> str:
    from station.radio import meeting, resolve, scheduler
    numbers = {"add": meeting.ADD_MIN, "up": meeting.UP_MIN, "burn": meeting.BURN_MIN, "burn_days": meeting.BURN_DAYS,
               "churn": round(meeting.CHURN * 100), "fit_floor": meeting.FIT_FLOOR, "match": resolve.MATCH_MIN,
               "spoken": scheduler.SPOKEN_MS}
    clocks = [{"clock": c, "arcs": clock_arcs(station, c)} for c in station.clocks]
    return env().get_template("how_programmed.html").render(st=station, counts=counts, last_meeting=last_meeting, n=numbers,
                                                            clocks=clocks, station=prefs.station)


PLAYLISTS_PATH = "playlists/index.html"


def render_playlists(tabs: list[dict], prefs: Prefs) -> str:
    return env().get_template("playlists.html").render(tabs=tabs, station=prefs.station)
