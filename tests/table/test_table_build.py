import json

import pytest

from station.config import load_prefs
from station.steps.write import Turn
from station.table.script import TablePart

PREFS = load_prefs()
PART = TablePart(2, "round1", "Round 1", (Turn("Anchor", "Some posters say A."), Turn("Anchor", "Jev's ruling. That claim: 79% likely true."),
                                          Turn("Uncle", "Here's my theory: some posters say B.")))
EPISODE = {
    "id": "table-2026-11-26", "day": "2026-11-26", "question": "Is Intel One Mono worth switching to?",
    "positions": {"anchor": "No.", "uncle": "Yes."},
    "thread": {"title": "Intel One Mono font", "source": "Hacker News", "url": "https://news.ycombinator.com/item?id=1"},
    "rounds": [{"part": "round1", "title": "Round 1", "claims": [
        {"side": "anchor", "text": "Some posters say <b>A</b>.", "p_true": 0.79, "sources": [{"id": "hn:11", "url": "https://news.ycombinator.com/item?id=11"}]},
        {"side": "uncle", "text": "Some posters say B.", "p_true": 0.68, "sources": []}]}],
    "verdict": {"anchor": 2.87, "uncle": 2.67, "winner": "anchor"}, "record": {"anchor": 1, "uncle": 0, "draw": 0},
    "chapters": [{"title": "The question", "start_ms": 0, "end_ms": 9000}],
    "audio": {"duration_ms": 160000, "key": "audio/table-2026-11-26-abc12345.mp3", "bytes": 1200000},
}


def test_tts_request_uses_the_table_voices():
    from station.table.build import tts_request

    req = tts_request(PART, PREFS.table_voices)
    cfg = req["generationConfig"]["speechConfig"]["multiSpeakerVoiceConfig"]["speakerVoiceConfigs"]
    assert {c["speaker"]: c["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] for c in cfg} == {"Anchor": "Schedar", "Uncle": "Gacrux"}
    assert [p["speech_metadata"]["speaker"] for p in req["contents"][0]["parts"]] == ["Anchor", "Anchor", "Uncle"]


def test_no_publish_when_assemble_failed(tmp_path, monkeypatch):  # Review Focus 5
    from station import __main__ as cli

    calls = []
    monkeypatch.setitem(cli.COMMANDS, "table-topic", lambda run: calls.append("topic"))
    for step in ("table-argue", "table-referee", "table-script", "table-voice"):
        monkeypatch.setitem(cli.COMMANDS, step, lambda run, s=step: calls.append(s))

    def broken(run):
        raise RuntimeError("ffmpeg failed")
    monkeypatch.setitem(cli.COMMANDS, "table-assemble", broken)
    monkeypatch.setitem(cli.COMMANDS, "table-page", lambda run: calls.append("page"))
    monkeypatch.setitem(cli.COMMANDS, "table-publish", lambda run: calls.append("publish"))
    monkeypatch.setenv("STATION_TABLE", str(tmp_path))
    with pytest.raises(RuntimeError):
        cli.main(["table", "--day", "2026-11-26"])
    assert "publish" not in calls and "page" not in calls


def test_page_shows_rulings_and_sources():
    from station.table.build import render_table

    html = render_table(EPISODE, PREFS)
    assert "79%" in html and "68%" in html and 'href="https://news.ycombinator.com/item?id=11"' in html
    assert "&lt;b&gt;A&lt;/b&gt;" in html and "WNCL" in html and "synthetic" in html.lower()
    assert "The Anchor takes it" in html and "Anchor 1" in html and 'src="/audio/table-2026-11-26-abc12345.mp3"' in html


def test_feed_keeps_table_episodes():
    import xml.etree.ElementTree as ET

    from station.steps.page import render_feed
    from tests.test_page import newscast

    other = {**EPISODE, "id": "table-2026-11-25", "day": "2026-11-25", "audio": {**EPISODE["audio"], "key": "audio/table-2026-11-25-x.mp3"}}
    items = ET.fromstring(render_feed(newscast(), PREFS, 1, table_episodes=[EPISODE, other])).findall("channel/item")
    assert len(items) == 3 and {i.find("guid").text for i in items} >= {"table-2026-11-26", "table-2026-11-25"}
    t = next(i for i in items if i.find("guid").text == "table-2026-11-26")
    assert t.find("title").text.startswith("The Table") and t.find("enclosure").get("url").endswith("abc12345.mp3")


def test_front_card_links_latest_episode():
    from station.steps.page import render_front
    from tests.test_page import newscast

    n = newscast()
    html = render_front(n, [n], PREFS, table=EPISODE)
    assert 'href="/table/2026-11-26/index.html"' in html and "Is Intel One Mono worth switching to?" in html
    assert "The Table" not in render_front(n, [n], PREFS).split("<footer>")[0]


def test_build_runs_table_after_7am_newscast(monkeypatch):
    from station import build as build_mod
    from station.__main__ import main

    got = []
    monkeypatch.setattr(build_mod, "build", lambda hour, **kw: got.append(kw.get("steps")))
    main(["build", "--hour", "2026-11-27T07"])
    steps = got[0]
    assert steps[-2:] == ["table", "picks"] and "corrections" in steps  # Corrections joins the first build too
