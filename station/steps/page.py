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
    e.filters["clock"] = _clock
    return e


def _clock(hhmm: str) -> str:
    """'19:00' -> '7:00 pm'."""
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{h % 12 or 12}:{m:02d} {'am' if h < 12 else 'pm'}"


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


STEP_LABELS = {"scrape": "Scrape sources", "dedupe": "Find duplicates", "judge": "Judge every post",
               "rundown": "Build the rundown", "write": "Write the scripts", "voice": "Voice the newscast",
               "assemble": "Assemble audio", "page": "Build the page", "publish": "Publish", "archive": "Archive",
               "finish": "Finish"}
DOTS = {"done": "green", "repaired": "amber", "failed": "red", "running": "white"}


def _detail(name: str, c: dict) -> str:
    g = c.get
    return {
        "scrape": f"{g('new_posts', 0)} new posts, {g('seen', 0)} seen",
        "dedupe": f"{g('clusters', 0)} stories, {g('candidates', 0)} same-story checks",
        "judge": f"{g('decisions', 0)} typed decisions",
        "rundown": f"{g('stories', 0)} stories, lead chosen" + (", short newscast" if g("short") else ""),
        "write": f"{g('chapters', 0)} chapters, {g('words', 0)} words",
        "voice": f"{g('chapters_voiced', 0)} chapters voiced" + (f", {g('failed')} failed" if g("failed") else ""),
        "assemble": f"join, normalize, {g('chapters', 0)} chapters",
        "page": "front page and hour page",
    }.get(name, "")


def step_rows(run_log: dict) -> list[dict]:
    return [{"label": STEP_LABELS.get(s["name"], s["name"]), "tool": s["tool"], "dot": DOTS.get(s["status"], "grey"),
             "time": _duration(round(s["seconds"] * 1000)), "detail": _detail(s["name"], s["counts"]),
             "notes": s["notes"], "status": s["status"]} for s in run_log.get("steps", [])]


def decision_log(judged: list, rundown, floor: float = 0.40, limit: int = 80) -> list[dict]:
    """Jev's calls for the control room. Dropped posts show only their verdict, never their title."""
    aired = {s.post.id: ("lead story" if i == 0 else "newscast") for i, s in enumerate(rundown.stories)}
    if rundown.overheard:
        aired[rundown.overheard.post.id] = "overheard"
    dropped = set(rundown.dropped_ids)
    rows = []
    for x in judged:
        pid = x.post.id
        if pid in dropped:
            rows.append({"post_id": pid, "verdict": "DROP", "score": x.private_harm, "title": "",
                         "reason": "may harm a private individual"})
        elif pid in aired:
            rows.append({"post_id": pid, "verdict": "AIR", "score": x.matter_week, "title": x.post.title,
                         "reason": aired[pid]})
        elif x.post.kind == "comment":
            continue
        elif x.same_as:
            ans = next((x.answers.get(f"same_story_{i}") for i, e in enumerate(x.earlier_ids) if e == x.same_as), None)
            rows.append({"post_id": pid, "verdict": "MERGE", "score": float(ans["noul"]) if ans else 0.0,
                         "title": x.post.title, "reason": "same story as an earlier post"})
        else:
            if x.is_reaction:
                reason = "reaction, not news"
            elif x.part == "none":
                reason = "no part of the newscast fits"
            elif x.matter_week < floor:
                reason = f"below the {round(floor * 100)}% floor"
            else:
                reason = "not in the top five"
            rows.append({"post_id": pid, "verdict": "CUT", "score": x.matter_week, "title": x.post.title, "reason": reason})
    order = {"AIR": 0, "MERGE": 1, "DROP": 2, "CUT": 3}
    rows.sort(key=lambda r: (order[r["verdict"]], -r["score"]))
    return rows[:limit]


def render_control_room(run_log: dict, decisions: list[dict], newscast: dict, prefs: Prefs) -> str:
    started = datetime.fromisoformat(run_log["started_at"])
    from zoneinfo import ZoneInfo

    local = started.astimezone(ZoneInfo(prefs.station.timezone))
    judge = next((s for s in run_log.get("steps", []) if s["name"] == "judge"), {"counts": {}})
    repairs = [{"note": n, "step": STEP_LABELS.get(s["name"], s["name"])} for s in run_log.get("steps", [])
               if s["status"] == "repaired" for n in s["notes"]]
    return env().get_template("control_room.html").render(
        n={**newscast, "hour_label": _hour_label(newscast)}, rows=step_rows(run_log), decisions=decisions,
        repairs=repairs, station=prefs.station, started=f"{local.hour % 12 or 12}:{local:%M:%S} {'am' if local.hour < 12 else 'pm'}",
        total=_duration(round(run_log.get("total_seconds", 0) * 1000)), decisions_count=judge["counts"].get("decisions", 0),
        floor=round(prefs.thresholds.air_min_probability * 100))


def render_settings(prefs: Prefs, beat_counts: dict[str, tuple[int, int]]) -> str:
    return env().get_template("settings.html").render(
        prefs=prefs, station=prefs.station, beat_counts=beat_counts,
        floor=round(prefs.thresholds.air_min_probability * 100),
        harm=round(prefs.thresholds.private_harm_max_probability * 100))


def todays_newscasts(run: Path, runs_root: Path = RUNS_ROOT) -> list[dict]:
    day = run.name[:10]
    out = []
    for f in sorted(runs_root.glob(f"{day}T??/newscast.json")):
        out.append(json.loads(f.read_text()))
    return out


def page(run: Path, prefs: Prefs, runs_root: Path = RUNS_ROOT, beat_counts: dict | None = None,
         control_room: bool = True) -> list[Path]:
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
    written = [front, hour, player]
    if control_room and (run / "run_log.json").exists() and (run / "rundown.json").exists():
        written += write_control_room(run, prefs, current)
    if beat_counts is not None:
        settings = site / "settings" / "index.html"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(render_settings(prefs, beat_counts))
        written.append(settings)
    return written


def write_control_room(run: Path, prefs: Prefs, newscast: dict) -> list[Path]:
    """Also called by the finish step so the page reflects publish and archive."""
    from station.steps.judge import Judged
    from station.steps.rundown import Rundown

    run_log = json.loads((run / "run_log.json").read_text())
    rundown = Rundown.from_dict(json.loads((run / "rundown.json").read_text()))
    judged = [Judged.from_dict(d) for d in json.loads((run / "judged.json").read_text())] \
        if (run / "judged.json").exists() else []
    out = run / "site" / "control-room" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    unique = list({x.post.id: x for x in [*judged, *rundown.stories]}.values())  # carried-over stories too
    out.write_text(render_control_room(run_log, decision_log(unique, rundown, prefs.thresholds.air_min_probability),
                                       newscast, prefs))
    return [out]
