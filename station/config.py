"""Preferences: the one file every run reads (config/preferences.json)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PREFS = Path("config/preferences.json")


@dataclass(frozen=True)
class Source:
    type: str
    ref: str
    visibility: str


@dataclass(frozen=True)
class Beat:
    id: str
    name: str
    used_in: str
    color: str
    sources: tuple[Source, ...]


@dataclass(frozen=True)
class Thresholds:
    air_min_probability: float
    private_harm_max_probability: float
    min_stories: int
    max_stories: int


@dataclass(frozen=True)
class Voices:
    host: str
    reporter: str
    style: str


@dataclass(frozen=True)
class Station:
    name: str
    show_name: str
    call_sign: str
    timezone: str
    first_newscast: str
    last_newscast: str
    frequency: str
    id_lines_newscast: tuple[str, ...]


@dataclass(frozen=True)
class Writer:
    model: str


@dataclass(frozen=True)
class Prefs:
    station: Station
    voices: Voices
    thresholds: Thresholds
    beats: tuple[Beat, ...]
    writer: Writer


def _need(d: dict[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise ValueError(f"preferences: missing '{key}' in {where}")
    return d[key]


def load_prefs(path: Path = DEFAULT_PREFS) -> Prefs:
    """Load and validate preferences; raises ValueError naming the first missing key."""
    d = json.loads(Path(path).read_text())
    t = _need(d, "thresholds", "top level")
    thresholds = Thresholds(
        air_min_probability=float(_need(t, "air_min_probability", "thresholds")),
        private_harm_max_probability=float(_need(t, "private_harm_max_probability", "thresholds")),
        min_stories=int(_need(t, "min_stories", "thresholds")),
        max_stories=int(_need(t, "max_stories", "thresholds")),
    )
    s = _need(d, "station", "top level")
    station = Station(
        name=_need(s, "name", "station"),
        show_name=_need(s, "show_name", "station"),
        call_sign=_need(s, "call_sign", "station"),
        timezone=_need(s, "timezone", "station"),
        first_newscast=_need(s, "first_newscast", "station"),
        last_newscast=_need(s, "last_newscast", "station"),
        frequency=_need(s, "frequency", "station"),
        id_lines_newscast=tuple(_need(_need(s, "id_lines", "station"), "newscast", "station.id_lines")),
    )
    v = _need(d, "voices", "top level")
    voices = Voices(host=_need(v, "host", "voices"), reporter=_need(v, "reporter", "voices"),
                    style=_need(v, "style", "voices"))
    beats = tuple(
        Beat(id=b["id"], name=b["name"], used_in=b["used_in"], color=b["color"],
             sources=tuple(Source(type=x["type"], ref=x["ref"], visibility=x["visibility"]) for x in b["sources"]))
        for b in _need(d, "beats", "top level")
    )
    writer = Writer(model=_need(_need(d, "writer", "top level"), "model", "writer"))
    return Prefs(station=station, voices=voices, thresholds=thresholds, beats=beats, writer=writer)
