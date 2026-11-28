"""Every page in today's design (Tarik, Nov 28: "nextjs would be better for all these html changes"): when the site's
design files change, the next hourly build rebuilds and republishes every page."""
import json
from pathlib import Path

import pytest

from station.config import load_prefs
from station.steps import rebuild
from tests.table.test_table_build import EPISODE
from tests.test_past_newscasts import runs

PREFS = load_prefs()


def design(tmp_path, text="<p>v1</p>"):
    root = tmp_path / "repo"
    (root / "templates").mkdir(parents=True)
    (root / "templates" / "front.html").write_text(text)
    for f in rebuild.RENDERERS:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text("# renderer")
    return root


def site(tmp_path, monkeypatch):
    root = runs(tmp_path, "2026-11-26T11", "2026-11-26T12")
    table = tmp_path / "table"
    (table / "2026-11-26").mkdir(parents=True)
    (table / "2026-11-26" / "table.json").write_text(json.dumps({**EPISODE, "day": "2026-11-26"}))
    (table / "2026-11-26" / "published").write_text("yes")
    monkeypatch.setenv("STATION_TABLE", str(table))
    return root, table


def test_fingerprint_follows_the_design_files(tmp_path):
    root = design(tmp_path)
    a = rebuild.design_fingerprint(root)
    assert rebuild.design_fingerprint(root) == a
    (root / "templates" / "front.html").write_text("<p>v2</p>")
    assert rebuild.design_fingerprint(root) != a


def test_rebuild_publishes_every_page(tmp_path, monkeypatch):
    runs_root, table = site(tmp_path, monkeypatch)
    put = {}
    n = rebuild.rebuild_site(object(), PREFS, runs_root, table, put=lambda key, data, ctype: put.__setitem__(key, data))
    for key in ("h/2026-11-26/1100/index.html", "h/2026-11-26/1200/index.html", "table/2026-11-26/index.html",
                "index.html", "music/index.html", "archive/index.html"):
        assert key in put, key
    assert n == len(put) and all(not k.endswith(".mp3") for k in put)   # pages and site files, never audio


def test_rebuilds_only_when_the_design_changes(tmp_path, monkeypatch):
    runs_root, table = site(tmp_path, monkeypatch)
    root, state, calls = design(tmp_path), tmp_path / "site_design.txt", []
    go = lambda: rebuild.maybe_rebuild(object(), PREFS, runs_root, table, state=state, repo_root=root,
                                      put=lambda key, data, ctype: calls.append(key))
    assert go() > 0 and state.read_text() == rebuild.design_fingerprint(root)
    before = len(calls)
    assert go() is None and len(calls) == before                          # nothing changed: nothing republished
    (root / "templates" / "front.html").write_text("<p>v2</p>")
    assert go() > 0


def test_a_failed_rebuild_never_fails_the_build(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bucket down")
    monkeypatch.setattr(rebuild, "maybe_rebuild", boom)
    assert "bucket down" in rebuild.safe_rebuild(object(), PREFS)       # a note, not an exception
