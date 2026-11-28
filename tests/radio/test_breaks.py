"""Plan B2, Task 3: what the host says between songs."""
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from station.config import load_prefs
from station.radio.breaks import CUT_AT, id_text, script_for
from station.radio.model import load_station, open_radio
from station.store import SCHEMA
from tests.fakes import FakeGateway, ok

PREFS = load_prefs()
CHI = ZoneInfo("America/Chicago")
ST = load_station("jazz")
PREV = [{"artist": "Nubya Garcia", "title": "Pace"}, {"artist": "Kokoroko", "title": "Abusey Junction"}]
NEXT = {"artist": "Alfa Mist", "title": "Keep On"}
FACTS = [{"text": "Pace is on Nubya Garcia's 2020 album Source, released on Concord Jazz.",
          "source_url": "https://example.org/source-review", "source_name": "example.org"}]
GOOD = ("That was Kokoroko with Abusey Junction, and before it Nubya Garcia with Pace. Pace is on her 2020 album Source, "
        "released on Concord Jazz, according to example dot org. I found it in the station's library. "
        "Coming up, Alfa Mist with Keep On.")


def db():
    d = sqlite3.connect(":memory:")
    d.executescript(SCHEMA)
    open_radio(d)
    return d


def gw(script=GOOD, beyond=0.05):
    return FakeGateway({("POST", "ollama", "/api/chat"): [ok({"message": {"content": script}})] * 3,
                        ("POST", "typesafe", "/v1/systemone"): [ok({"model": "jev-1", "answers": {"beyond_facts": {"type": "noul", "noul": beyond}}})] * 3})


def item(kind, hhmm="12:20"):
    h, m = (int(x) for x in hhmm.split(":"))
    return {"kind": kind, "candidate_id": None, "starts_at": datetime(2026, 11, 28, h, m, tzinfo=CHI).isoformat()}


def test_break_names_what_played_and_one_fact():
    out = script_for(gw(), db(), ST, item("break"), PREV, NEXT, PREFS, FACTS)
    assert "Abusey Junction" in out["text"] and out["sources"] == [{"url": FACTS[0]["source_url"], "name": "example.org"}]


def test_script_beyond_facts_is_cut():  # B2 Focus 2: Jev says the script claims more than its facts
    d = db()
    out = script_for(gw(beyond=0.4), d, ST, item("break"), PREV, NEXT, PREFS, FACTS)
    assert out["sources"] == [] and "Concord" not in out["text"] and "Abusey Junction" in out["text"] and "Alfa Mist" in out["text"]
    assert d.execute("SELECT COUNT(*) FROM decisions WHERE question_id = 'break:beyond_facts'").fetchone()[0] == 1
    assert CUT_AT == 0.3


def test_no_facts_means_plain_back_announce():
    g = gw()
    out = script_for(g, db(), ST, item("backsell"), PREV, NEXT, PREFS, [])
    assert out["sources"] == [] and "Abusey Junction" in out["text"] and not g.calls   # no model when there is nothing to say


def test_id_lines_from_preferences():
    texts = {id_text(ST, PREFS, n) for n in range(4)}
    assert all(t.startswith("ONE Jazz.") for t in texts)
    assert {t.split(". ", 1)[1] for t in texts} == set(PREFS.station.id_lines_newscast)


def test_tease_promises_news_only_before_a_newscast_hour():
    day = script_for(gw(), db(), ST, item("id_tease", "12:30"), PREV, NEXT, PREFS, FACTS)["text"]
    night = script_for(gw(), db(), ST, item("id_tease", "21:30"), PREV, NEXT, PREFS, FACTS)["text"]
    assert "news" in day.lower() and "news" not in night.lower()


def test_script_never_reads_urls():
    out = script_for(gw(script=GOOD + " Read more at https://example.org/x"), db(), ST, item("break"), PREV, NEXT, PREFS, FACTS)
    assert "http" not in out["text"]
