"""Every page in today's design (Tarik, Nov 28). Pages are built once, in their own hour, so a change to the site's
design used to leave every older page with the old look. Each hourly build now compares a fingerprint of the design
files with the last one; when it changed, every published page is rebuilt and republished: each past hour and its
story pages, each Table episode, and the front-page set from the newest newscast. Content never changes, only the frame."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from station.config import Prefs
from station.runs import RUNS_ROOT
from station.steps.page import all_newscasts, hour_pages, page, table_episodes
from station.steps.publish import CONTENT_TYPES, cache_control, put_object
from station.table.build import render_table, table_path

REPO = Path(__file__).resolve().parents[2]
RENDERERS = ("station/steps/page.py", "station/table/build.py", "station/radio/page.py")
STATE = Path("data/site_design.txt")


def design_fingerprint(repo_root: Path = REPO) -> str:
    """A hash of the templates and the modules that render pages."""
    h = hashlib.sha1()
    for f in sorted((repo_root / "templates").rglob("*")) + [repo_root / r for r in RENDERERS]:
        if f.is_file():
            h.update(str(f.relative_to(repo_root)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _table_root(table_root: Path | None) -> Path:
    return Path(table_root or os.environ.get("STATION_TABLE", "data/table"))


def rebuild_site(gw, prefs: Prefs, runs_root: Path = RUNS_ROOT, table_root: Path | None = None, put=None) -> int:
    """Rebuild and republish every published page; returns how many files went up. Audio is never touched."""
    send = put or (lambda key, data, ctype: put_object(gw, prefs.hosting.bucket, key, data, ctype, cache_control(key)))
    done: set[str] = set()

    def put(key: str, data: bytes, ctype: str) -> None:
        if key not in done:  # the newest hour's page comes from both passes: send it once
            send(key, data, ctype)
            done.add(key)

    casts = all_newscasts(Path(runs_root))
    for nc in casts:
        for key, html in hour_pages(Path(runs_root) / nc["id"], prefs, Path(runs_root)).items():
            put(key, html.encode(), "text/html; charset=utf-8")
    for ep in table_episodes(_table_root(table_root)):
        put(table_path(ep["day"]), render_table(ep, prefs).encode(), "text/html; charset=utf-8")
    if casts:  # the front page, Music hub, Archive, settings, control room and site files, from the newest newscast
        run = Path(runs_root) / casts[0]["id"]
        for path in page(run, prefs, Path(runs_root)):
            if path.suffix in CONTENT_TYPES and path.suffix != ".mp3":
                put(str(path.relative_to(run / "site")), path.read_bytes(), CONTENT_TYPES[path.suffix])
    return len(done)


def maybe_rebuild(gw, prefs: Prefs, runs_root: Path = RUNS_ROOT, table_root: Path | None = None, state: Path = STATE,
                  repo_root: Path = REPO, put=None) -> int | None:
    """Rebuild everything when the design changed since the last rebuild; None when it didn't."""
    fp = design_fingerprint(repo_root)
    if state.exists() and state.read_text().strip() == fp:
        return None
    n = rebuild_site(gw, prefs, runs_root, table_root, put)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(fp)  # only after every page went up: a failed rebuild is tried again next hour
    return n


def safe_rebuild(gw, prefs: Prefs) -> str:
    """For the hourly build: a note, never an exception (a stale page must not stop a newscast)."""
    try:
        n = maybe_rebuild(gw, prefs)
    except Exception as e:  # noqa: BLE001
        return f"site rebuild failed, retried next hour: {type(e).__name__}: {str(e)[:160]}"
    return f"site rebuilt in the current design: {n} files" if n is not None else ""
