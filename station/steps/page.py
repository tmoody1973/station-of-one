"""Step 8, page: the front page and a permanent page per hour, from newscast.json.

Layout follows mockups/Front page.png; copy and colors follow mockups/Main.dc.html. Static
files only, served from the public bucket; Tigris serves no index documents, so every internal
link names its file (/index.html, /h/<date>/<HHMM>/index.html).
"""
from __future__ import annotations

import json
import re
import unicodedata
import os
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


def _slug(text: str, fallback: str) -> str:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()  # Citroën -> Citroen
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:60].rstrip("-") or fallback


def story_path(newscast_id: str, index: int, headline: str) -> str:
    """One page per aired story; the position prefix keeps two identical headlines apart."""
    d = datetime.strptime(newscast_id, "%Y-%m-%dT%H")
    return f"s/{d:%Y-%m-%d}/{d:%H}00/{index + 1}-{_slug(headline, 'story')}/index.html"


def pick_path(day: str, index: int, artist: str, title: str) -> str:
    return f"m/{day}/{index + 1}-{_slug(f'{artist} {title}', 'pick')}/index.html"


def _with_links(newscast: dict, extras: dict | None) -> list[dict]:
    """Stories plus their page URL and extra (article, image) when the story step ran this hour."""
    if extras is None:
        return newscast["stories"]
    return [{**s, "url": "/" + story_path(newscast["id"], i, s.get("headline") or ""), "extra": extras.get(s["id"])}
            for i, s in enumerate(newscast["stories"])]


YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALBUM_ID = re.compile(r"^\d{1,12}$")


def embed_url(pick: dict, big: bool = False) -> str:
    """Official player address, built from a validated id only; "" when the id is not valid.
    big: the pick page's player (Bandcamp with large artwork and the tracklist)."""
    eid = str(pick.get("embed_id") or "")
    if pick.get("kind") == "youtube" and YOUTUBE_ID.match(eid):
        return f"https://www.youtube-nocookie.com/embed/{eid}?autoplay=1"
    if pick.get("kind") == "bandcamp" and ALBUM_ID.match(eid):
        style = "tracklist=true/transparent=true/" if big else "tracklist=false/artwork=small/transparent=true/"
        return f"https://bandcamp.com/EmbeddedPlayer/album={eid}/size=large/bgcol=ffffff/linkcol=d62d20/{style}"
    return ""


def latest_picks(picks_root: Path, today: str | None = None) -> dict | None:
    """The newest day up to `today` with at least one playable pick (an empty day keeps the last real picks).
    A damaged file is skipped, never fatal: this runs in every hourly page build (review, Nov 27)."""
    for f in sorted(Path(picks_root).glob("????-??-??.json"), reverse=True):
        if today and f.stem > today:
            continue
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        day = data.get("day") or f.stem
        playable = [{**p, "embed": embed_url(p), "page": "/" + pick_path(day, i, p.get("artist", ""), p.get("title", ""))}
                    for i, p in enumerate(data.get("picks") or []) if embed_url(p)]
        if playable:
            return {**data, "picks": playable}
    return None


def _hour_label(n: dict) -> str:
    t = datetime.fromisoformat(n["hour_local"])
    return f"{t.hour % 12 or 12}:00 {'am' if t.hour < 12 else 'pm'}"


def _date_label(n: dict) -> str:
    t = datetime.fromisoformat(n["hour_local"])
    return f"{t:%A}, {t:%B} {t.day}"


def _context(current: dict, today: list[dict], prefs: Prefs, mode: str, extras: dict | None = None) -> dict:
    beats = {b.id: {"name": b.name, "color": b.color} for b in prefs.beats}
    ordered = sorted(today, key=lambda n: n["id"], reverse=True)
    for n in ordered:
        n["hour_label"] = _hour_label(n)
        n["page"] = "/" + hour_path(n["id"])
        n["audio_url"] = audio_path(n)
    current = {**current, "hour_label": _hour_label(current), "page": "/" + hour_path(current["id"]),
               "audio_url": audio_path(current)}
    stories = _with_links(current, extras)
    return {"n": current, "lead": stories[0] if stories else None, "others": stories[1:], "today": ordered,
            "beats": beats, "station": prefs.station, "date_label": _date_label(current), "mode": mode,
            "chapters_json": json.dumps(current["chapters"])}


def audio_path(n: dict) -> str:
    """Public path of a newscast's MP3: its fingerprinted key, or the plain name for older hours."""
    return "/" + ((n.get("audio") or {}).get("key") or f"audio/{n['id']}.mp3")


def render_front(current: dict, today: list[dict], prefs: Prefs, video_url: str | None = None,
                 table: dict | None = None, corrections: dict | None = None, extras: dict | None = None,
                 picks: dict | None = None) -> str:
    if picks is not None and any("embed" not in p for p in picks.get("picks", [])):
        picks = {**picks, "picks": [{**p, "embed": embed_url(p)} for p in picks["picks"] if embed_url(p)]}
    return env().get_template("front.html").render(**_context(current, today, prefs, "front", extras),
                                                   video_url=video_url, table=table, corrections=corrections, picks=picks)


def render_hour(newscast: dict, prefs: Prefs, today: list[dict] | None = None, extras: dict | None = None) -> str:
    return env().get_template("front.html").render(**_context(newscast, today or [newscast], prefs, "hour", extras))


def render_pick(picks: dict, pick: dict, prefs: Prefs) -> str:
    day = picks.get("day", "")
    others = [{**p, "page": p.get("page") or "/" + pick_path(day, i, p.get("artist", ""), p.get("title", ""))}
              for i, p in enumerate(picks.get("picks", [])) if p.get("embed_id") != pick.get("embed_id")]
    return env().get_template("music.html").render(p=pick, big=embed_url(pick, big=True), picks_day=day, others=others,
                                                   station=prefs.station)


def render_story(newscast: dict, story: dict, extra: dict | None, prefs: Prefs) -> str:
    stories = _with_links(newscast, {})
    image = (extra or {}).get("image")
    og = ""
    if image:
        og = image["src"] if image["kind"] == "photo" else prefs.hosting.public_base + image["src"]
    return env().get_template("story.html").render(
        n={**newscast, "hour_label": _hour_label(newscast), "page": "/" + hour_path(newscast["id"]),
           "audio_url": audio_path(newscast)},
        s=story, extra=extra or {}, image=image, og_image=og, others=[x for x in stories if x["id"] != story["id"]],
        beats={b.id: {"name": b.name, "color": b.color} for b in prefs.beats}, station=prefs.station,
        date_label=_date_label(newscast), floor=round(prefs.thresholds.air_min_probability * 100))


STEP_LABELS = {"scrape": "Scrape sources", "dedupe": "Find duplicates", "judge": "Judge every post",
               "rundown": "Build the rundown", "write": "Write the scripts", "voice": "Voice the newscast",
               "assemble": "Assemble audio", "story": "Write story pages", "radio": "Music station", "page": "Build the page", "publish": "Publish", "archive": "Archive",
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
        "publish": f"{g('files', 0)} files to the public bucket",
        "archive": f"bundle of {round(g('bytes', 0) / 1e6, 1)} MB with the decision log",
        "finish": "control room updated, Sprite checkpoint",
        "video": f"{g('seconds', 0):.0f} s video, {g('words', 0)} captioned words",
        "table": "The Table, from yesterday's threads",
        "radio": f"{g('items', 0)} feed items, {g('resolved', 0)} matched, {g('scheduled', 0)} in the set",
        "story": f"{g('articles', 0)} articles, {g('photos', 0)} photos, {g('illustrations', 0)} illustrations",
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


def table_episodes(table_root: Path) -> list[dict]:
    """The Table's episodes, newest first (data/table/<day>/table.json)."""
    return [json.loads(f.read_text()) for f in sorted(table_root.glob("*/table.json"), reverse=True)
            if (f.parent / "published").exists()]  # never link an episode that failed to upload


def render_feed(newscast: dict, prefs: Prefs, audio_bytes: int, table_episodes: list[dict] = ()) -> str:
    """Podcast feed (spec §9): one item, the latest newscast, replaced each hour."""
    from email.utils import format_datetime

    return env().get_template("feed.xml").render(
        n=newscast, station=prefs.station, base=prefs.hosting.public_base, audio_bytes=audio_bytes,
        audio=audio_path(newscast),
        hour_label=_hour_label(newscast), date_label=_date_label(newscast), page=hour_path(newscast["id"]),
        pub_date=format_datetime(datetime.fromisoformat(newscast["hour_local"])),
        table_episodes=[{**t, "pub_date": format_datetime(datetime.fromisoformat(f"{t['day']}T08:00:00-06:00"))}
                        for t in table_episodes])


def todays_newscasts(run: Path, runs_root: Path = RUNS_ROOT) -> list[dict]:
    day = run.name[:10]
    out = []
    for f in sorted(runs_root.glob(f"{day}T??/newscast.json")):
        out.append(json.loads(f.read_text()))
    return out


MUSICKIT_TOKEN = Path("data/musickit_token")  # Tarik's origin-locked web token (Plan C, decision 012); git-ignored


def musickit_config(token_path: Path) -> dict | None:
    """MusicKit on the Web's settings for the browser, or None until Tarik has placed the web token."""
    try:
        token = Path(token_path).read_text().strip()
    except OSError:
        return None
    return {"developerToken": token, "app": {"name": "ONE 1.0 FM", "build": "2026.11.27"}} if token else None


def page(run: Path, prefs: Prefs, runs_root: Path = RUNS_ROOT, beat_counts: dict | None = None,
         control_room: bool = True, musickit_token: Path = MUSICKIT_TOKEN) -> list[Path]:
    current = json.loads((run / "newscast.json").read_text())
    today = todays_newscasts(run, runs_root) or [current]
    site = run / "site"
    front = site / "index.html"
    hour = site / hour_path(current["id"])
    hour.parent.mkdir(parents=True, exist_ok=True)
    day = current["id"][:10]
    has_video = (TEMPLATES.parent / "video" / "out" / f"{day}.mp4").exists()  # rendered after the last newscast
    episodes = table_episodes(Path(os.environ.get("STATION_TABLE", "data/table")))
    graded = sorted(runs_root.glob(f"{day}T??/corrections.json"))  # written by the day's first build
    picks = latest_picks(Path(os.environ.get("STATION_PICKS", "data/picks")), today=day)
    extras_file = run / "stories.json"  # written by the story step; absent when it was skipped
    extras = json.loads(extras_file.read_text()) if extras_file.exists() else None
    front.write_text(render_front(current, today, prefs, video_url=f"/video/{day}.mp4" if has_video else None,
                                  table=episodes[0] if episodes else None,
                                  corrections=json.loads(graded[0].read_text()) if graded else None, extras=extras,
                                  picks=picks))
    hour.write_text(render_hour(current, prefs, today, extras=extras))
    story_pages = []
    if extras is not None:
        for i, st in enumerate(current["stories"]):
            sp = site / story_path(current["id"], i, st.get("headline") or "")
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(render_story(current, st, extras.get(st["id"]), prefs))
            story_pages.append(sp)
    for i, pk in enumerate((picks or {}).get("picks", [])):  # one page per music pick, rebuilt each hour
        mp = site / pk["page"].lstrip("/")
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(render_pick(picks, pk, prefs))
        story_pages.append(mp)
    player = site / "shell.js"  # the site shell: one player for every page (decision 010)
    player.write_text((TEMPLATES / "shell.js").read_text())
    live_js = site / "live.js"  # loaded by shell.js only when a listener tunes in (Plan C)
    live_js.write_text((TEMPLATES / "live.js").read_text())
    from station.steps.stations import stations_json
    strip = site / "data" / "stations.json"  # the station strip's data
    strip.parent.mkdir(parents=True, exist_ok=True)
    strip.write_text(json.dumps(stations_json(prefs, current)))
    feed = site / "feed.xml"
    mp3 = run / "newscast.mp3"
    feed.write_text(render_feed(current, prefs, mp3.stat().st_size if mp3.exists() else 0, episodes))
    for asset in ("cover-one.png", "logo-one.png"):  # a changed asset gets a new name: images are cached long
        if (TEMPLATES.parent / "assets" / asset).exists():
            (site / asset).write_bytes((TEMPLATES.parent / "assets" / asset).read_bytes())
    written = [front, hour, player, live_js, strip, feed, *story_pages]
    mk = musickit_config(musickit_token)
    if mk:  # public by design: MusicKit on the Web needs it in the browser; Apple honours it only from our origin
        mk_path = site / "data" / "musickit.json"
        mk_path.write_text(json.dumps(mk))
        written.append(mk_path)
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
