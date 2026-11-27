import sqlite3
from datetime import UTC, datetime

import pytest

import station.radio.run as run_mod
from station.config import load_prefs
from station.radio.extract import Extracted
from station.radio.model import load_station, open_radio
from station.radio.page import render_sampler
from station.radio.poll import FeedItem
from station.radio.program import Block
from station.radio.resolve import AppleRefused, Match

NOW = datetime(2026, 11, 27, 18, tzinfo=UTC)
TRACK = {"candidate_id": "c1", "song_id": "1747390578", "artist": "Nubya <b>Garcia</b>", "title": "Odyssey", "album": "Odyssey",
         "release_date": "2024-09-20", "duration_ms": 443488, "preview_url": "https://audio-ssl.itunes.apple.com/p.m4a",
         "apple_url": "https://music.apple.com/us/album/odyssey/1", "artwork_url": "https://is1-ssl.mzstatic.com/300x300bb.jpg",
         "fit": 0.9, "note": "Found in UK Vibe: Odyssey review", "source_url": "javascript:alert(1)", "era": "recent"}


def page(tracks=(TRACK,)):
    return render_sampler(load_station("uk-jazz"), Block("uk-jazz", "b1", NOW.isoformat(), list(tracks)),
                          {"items": 3, "extracted": 2, "resolved": 1, "held": 0, "not_on_apple": 1, "scheduled": 1}, load_prefs())


def test_previews_never_autoplay_next():  # Review Focus 5
    html = page([TRACK, {**TRACK, "candidate_id": "c2", "song_id": "2"}])
    assert "autoplay" not in html and "ended" not in html
    assert html.count('data-preview="https://audio-ssl.itunes.apple.com/p.m4a"') == 2


def test_every_track_has_source_and_apple_link():
    html = page()
    assert 'href="https://music.apple.com/us/album/odyssey/1"' in html and "Listen on Apple Music" in html
    assert "Found in UK Vibe: Odyssey review" in html


def test_text_is_escaped():
    html = page()
    assert "Nubya &lt;b&gt;Garcia&lt;/b&gt;" in html and "javascript:alert" not in html


@pytest.fixture
def db():
    d = sqlite3.connect(":memory:")
    open_radio(d)
    d.execute("CREATE TABLE source_state (source_key TEXT PRIMARY KEY, last_success_at TEXT)")
    d.execute("CREATE TABLE decisions (post_id TEXT, question_id TEXT, answer_type TEXT, value TEXT, probability REAL, "
              "confidence REAL, raw TEXT, model TEXT, asked_at TEXT, PRIMARY KEY (post_id, question_id))")
    return d


def test_apple_refusal_keeps_last_page(db, tmp_path, monkeypatch):  # Review Focus 4
    item = FeedItem("fi1", "UK Vibe", "g1", "Odyssey review", "https://ukvibe.org/r", "2026-11-26", "Nubya Garcia's Odyssey.")
    def fake_poll(gw, st, d, now):  # stores the item like the real poller
        d.execute("INSERT INTO feed_items (id, station_id, feed, guid, title, link, published_at, excerpt, seen_at) "
                  "VALUES (?, 'uk-jazz', ?, ?, ?, ?, ?, ?, ?)", (item.id, item.feed, item.guid, item.title, item.link,
                                                                 item.published_at, item.excerpt, now.isoformat()))
        return [item], []
    monkeypatch.setattr(run_mod, "poll", fake_poll)
    monkeypatch.setattr(run_mod, "seed_candidates", lambda gw, st, d, now: ([], []))
    monkeypatch.setattr(run_mod, "extract", lambda gw, m, items: ({"fi1": [Extracted("track", "Nubya Garcia", "Odyssey", "", "", 2024, "")]}, []))
    monkeypatch.setattr(run_mod, "fit_scores", lambda gw, st, c: ({c[0][0]: 0.9}, {c[0][0]: {"type": "noul", "noul": 0.9}}, "jev"))

    def refuse(*a, **k):
        raise AppleRefused("Apple Music refused the developer token (401)")
    monkeypatch.setattr(run_mod, "resolve", refuse)
    uploads = []
    monkeypatch.setattr(run_mod, "put_object", lambda *a, **k: uploads.append(a[2]))
    out = run_mod.run_station(object(), "uk-jazz", db, NOW, load_prefs(), out_root=tmp_path)
    assert uploads == [] and any("refused" in n for n in out["notes"]) and out["scheduled"] == 0


def test_build_runs_radio_after_finish():
    from station.build import STEPS
    from station.manager import FALLBACKS, SKIP_MEANS
    assert STEPS[STEPS.index("finish") + 1] == "radio"
    assert FALLBACKS["radio"] == ["retry", "skip"] and "newscast" in SKIP_MEANS["radio"]


def test_seed_tracks_are_fit_scored_with_feed_finds(db, tmp_path, monkeypatch):
    seed_item = FeedItem("seed1", "the station's seed list", "seed:Ezra Collective", "Ezra Collective, a core artist", "", "", "brief")
    seed = ("sc1", Extracted("track", "Ezra Collective", "Victory Dance", "", "", 2022, ""), seed_item)
    monkeypatch.setattr(run_mod, "poll", lambda gw, st, d, now: ([], []))
    monkeypatch.setattr(run_mod, "extract", lambda gw, m, items: ({}, []))
    monkeypatch.setattr(run_mod, "seed_candidates", lambda gw, st, d, now: ([seed], []))
    seen = []
    monkeypatch.setattr(run_mod, "fit_scores", lambda gw, st, c: (seen.extend(x[0] for x in c), ({}, {}, None))[1])
    monkeypatch.setattr(run_mod, "put_object", lambda *a, **k: None)
    run_mod.run_station(object(), "uk-jazz", db, NOW, load_prefs(), out_root=tmp_path)
    assert seen == ["sc1"]
