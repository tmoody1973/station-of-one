"""Step 8, page: the front page and a permanent page per hour, from newscast.json.

Layout follows mockups/Front page.png; copy and colors follow mockups/Main.dc.html. Static
files only, served from the public bucket; Tigris serves no index documents, so every internal
link names its file (/index.html, /h/<date>/<HHMM>/index.html).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from station.config import Prefs
from station.runs import RUNS_ROOT

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def env() -> Environment:
    e = Environment(loader=FileSystemLoader(TEMPLATES),
                    autoescape=select_autoescape(enabled_extensions=("html", "xml"), default_for_string=True))
    e.filters["duration"] = _duration
    e.filters["pct"] = lambda p: f"{round(float(p) * 100)}%"
    e.filters["thousands"] = lambda n: f"{int(n):,}"
    e.filters["safe_url"] = safe_url
    return e


def safe_url(url: str | None) -> str:
    """Scraped links are untrusted: only http(s) URLs become links (no javascript:, data:, ...)."""
    url = (url or "").strip()
    return url if url.lower().startswith(("https://", "http://")) else "#"


def _duration(ms: int) -> str:
    s = round(ms / 1000)
    return f"{s // 60}:{s % 60:02d}"


def hour_path(newscast_id: str) -> str:
    d = datetime.strptime(newscast_id, "%Y-%m-%dT%H")
    return f"h/{d:%Y-%m-%d}/{d:%H}00/index.html"


def _hour_label(n: dict) -> str:
    t = datetime.fromisoformat(n["hour_local"])
    return f"{t.hour % 12 or 12}:00 {'am' if t.hour < 12 else 'pm'}"


def _date_label(n: dict) -> str:
    t = datetime.fromisoformat(n["hour_local"])
    return f"{t:%A}, {t:%B} {t.day}"


def _context(current: dict, today: list[dict], prefs: Prefs, mode: str) -> dict:
    beats = {b.id: {"name": b.name, "color": b.color} for b in prefs.beats}
    ordered = sorted(today, key=lambda n: n["id"], reverse=True)
    for n in ordered:
        n["hour_label"] = _hour_label(n)
        n["page"] = "/" + hour_path(n["id"])
        n["audio_url"] = f"/audio/{n['id']}.mp3"
    current = {**current, "hour_label": _hour_label(current), "page": "/" + hour_path(current["id"]),
               "audio_url": f"/audio/{current['id']}.mp3"}
    stories = current["stories"]
    return {"n": current, "lead": stories[0] if stories else None, "others": stories[1:], "today": ordered,
            "beats": beats, "station": prefs.station, "date_label": _date_label(current), "mode": mode,
            "chapters_json": json.dumps(current["chapters"])}


def render_front(current: dict, today: list[dict], prefs: Prefs) -> str:
    return env().get_template("front.html").render(**_context(current, today, prefs, "front"))


def render_hour(newscast: dict, prefs: Prefs, today: list[dict] | None = None) -> str:
    return env().get_template("front.html").render(**_context(newscast, today or [newscast], prefs, "hour"))


def todays_newscasts(run: Path, runs_root: Path = RUNS_ROOT) -> list[dict]:
    day = run.name[:10]
    out = []
    for f in sorted(runs_root.glob(f"{day}T??/newscast.json")):
        out.append(json.loads(f.read_text()))
    return out


def page(run: Path, prefs: Prefs, runs_root: Path = RUNS_ROOT) -> list[Path]:
    current = json.loads((run / "newscast.json").read_text())
    today = todays_newscasts(run, runs_root) or [current]
    site = run / "site"
    front = site / "index.html"
    hour = site / hour_path(current["id"])
    hour.parent.mkdir(parents=True, exist_ok=True)
    front.write_text(render_front(current, today, prefs))
    hour.write_text(render_hour(current, prefs, today))
    player = site / "player.js"
    player.write_text((TEMPLATES / "player.js").read_text())
    return [front, hour, player]
