"""Plan B2, Task 4: voice the queue's spoken items ahead of air."""
import json
import sqlite3
from datetime import UTC, datetime, timedelta

from station.config import load_prefs
from station.gateway import GatewayError
from station.radio.model import load_station, open_radio
from station.radio.voicing import VOICE_AHEAD, voice_spoken
from station.store import SCHEMA

PREFS = load_prefs()
NOW = datetime(2026, 11, 28, 18, 0, tzinfo=UTC)   # noon Central
ST = load_station("jazz")


def db():
    d = sqlite3.connect(":memory:")
    d.executescript(SCHEMA)
    open_radio(d)
    return d


def q(d, minutes, kind, cid=None, dur=240000):
    at = (NOW + timedelta(minutes=minutes)).isoformat()
    if cid:
        d.execute("INSERT OR IGNORE INTO candidates (id, kind, artist, title, status, matched_artist, matched_title) "
                  "VALUES (?, 'track', ?, ?, 'resolved', ?, ?)", (cid, f"Artist {cid}", f"Song {cid}", f"Artist {cid}", f"Song {cid}"))
    d.execute("INSERT INTO queue (station_id, starts_at, kind, candidate_id, duration_ms) VALUES ('jazz', ?, ?, ?, ?)", (at, kind, cid, dur))


class Rec:
    def __init__(self, fail=False):
        self.texts, self.uploads, self.fail, self.calls = [], {}, fail, 0

    def tts(self, text, host):
        self.calls += 1
        if self.fail:
            raise GatewayError("gemini", 500, "down")
        self.texts.append((text, host["voice"]))
        return b"ID3fake", 9.5

    def put(self, key, data):
        self.uploads[key] = data


def hour(d):
    q(d, 0, "id")
    q(d, 1, "song", "a")
    q(d, 5, "song", "b")
    q(d, 9, "break")
    q(d, 10, "song", "c")


def test_spoken_items_get_audio_once():
    d, r = db(), Rec()
    hour(d)
    counts = voice_spoken(object(), d, ST, PREFS, NOW, tts=r.tts, put=r.put, facts=lambda cid: [])
    rows = d.execute("SELECT kind, text, audio_url, audio_ms FROM queue WHERE kind != 'song' ORDER BY starts_at").fetchall()
    assert [k for k, *_ in rows] == ["id", "break"] and all(t and u and u.startswith("/audio/radio/jazz/") and ms == 9500 for _, t, u, ms in rows)
    assert "Song b" in rows[1][1] and "Song c" in rows[1][1]              # the break back-announces b, teases c
    assert {v for _, v in r.texts} == {"Sulafat"} and counts["voiced"] == 2
    again = voice_spoken(object(), d, ST, PREFS, NOW, tts=r.tts, put=r.put, facts=lambda cid: [])
    assert again["voiced"] == 0 and len(r.texts) == 2


def test_tts_failure_leaves_item_unvoiced():  # B2 Focus 3, server side
    d, r = db(), Rec(fail=True)
    hour(d)
    counts = voice_spoken(object(), d, ST, PREFS, NOW, tts=r.tts, put=r.put, facts=lambda cid: [])
    assert d.execute("SELECT COUNT(*) FROM queue WHERE audio_url IS NOT NULL").fetchone()[0] == 0
    assert counts["voiced"] == 0 and any("voice" in n for n in counts["notes"])
    assert d.execute("SELECT COUNT(*) FROM queue WHERE kind = 'song'").fetchone()[0] == 3


def test_id_audio_reused():
    d, r = db(), Rec()
    q(d, 0, "id")
    q(d, 60, "id")   # 1 pm: the same hour parity picks... a line; identical text is voiced once
    q(d, 120, "id")
    voice_spoken(object(), d, ST, PREFS, NOW, tts=r.tts, put=r.put, facts=lambda cid: [])
    texts = [t for t, _ in r.texts]
    assert len(texts) == len(set(texts)) and len(r.uploads) == len(set(texts))


def test_voicing_window_is_two_hours():
    d, r = db(), Rec()
    q(d, 30, "id")
    q(d, 60 * 3, "id")
    voice_spoken(object(), d, ST, PREFS, NOW, tts=r.tts, put=r.put, facts=lambda cid: [])
    assert VOICE_AHEAD == timedelta(hours=2) and len(r.texts) == 1


def test_queue_json_carries_voice_fields():
    from station.radio.onair import window
    d, r = db(), Rec()
    hour(d)
    voice_spoken(object(), d, ST, PREFS, NOW, tts=r.tts, put=r.put, facts=lambda cid: [])
    items = window(d, "jazz", NOW - timedelta(minutes=1), NOW + timedelta(hours=1))
    brk = next(it for it in items if it["kind"] == "break")
    assert brk["audio_url"].endswith(".mp3") and brk["text"] and json.loads(brk["sources"] or "[]") == [] and brk["audio_ms"] == 9500



def test_voicing_keeps_to_its_budget():  # review I2: never past the build lock
    d, r = db(), Rec()
    hour(d)
    counts = voice_spoken(object(), d, ST, PREFS, NOW, tts=r.tts, put=r.put, facts=lambda cid: [], budget_s=0)
    assert counts["voiced"] == 0 and any("budget" in n for n in counts["notes"])


def test_voicing_stops_after_repeated_failures():
    d, r = db(), Rec(fail=True)
    for m in range(0, 100, 10):
        q(d, m, "id")
    voice_spoken(object(), d, ST, PREFS, NOW, tts=r.tts, put=r.put, facts=lambda cid: [])
    assert r.calls <= 2


def test_voicing_passes_the_slot_length(monkeypatch):  # clock sync Task 1
    import station.radio.voicing as voicing
    seen = []
    real = voicing.script_for
    monkeypatch.setattr(voicing, "script_for", lambda *a, **k: (seen.append(k.get("target_s")), real(*a, **k))[1])
    d, r = db(), Rec()
    hour(d)
    voice_spoken(object(), d, ST, PREFS, NOW, tts=r.tts, put=r.put, facts=lambda cid: [])
    assert sorted(seen) == [240.0, 240.0]                                # each item's planned slot (q() plans 240 s)
