"""Sampler page (plan 2026-11-27-music-station-a, Task 8; PRD "Without Apple Music").

The programmed block as a tracklist: each track's note and source link, a 30-second Apple preview that
plays only when tapped (one at a time, never advancing on its own), and a "Listen on Apple Music" link.
"""
from __future__ import annotations

from station.config import Prefs
from station.radio.model import StationConfig
from station.radio.program import Block
from station.steps.page import env


def sampler_path(station_id: str) -> str:
    return f"radio/{station_id}/index.html"


def render_sampler(station: StationConfig, block: Block, counts: dict, prefs: Prefs) -> str:
    minutes = round(sum(t["duration_ms"] for t in block.tracks) / 60000)
    return env().get_template("radio.html").render(st=station, block=block, counts=counts, minutes=minutes,
                                                   station=prefs.station)
