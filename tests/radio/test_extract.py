import json

from station.radio.extract import Extracted, extract, parse_reply
from station.radio.poll import FeedItem
from tests.fakes import FakeGateway, ok


def item(i="a"):
    return FeedItem(i, "UK Vibe", f"g{i}", "Nubya Garcia 'Odyssey'", "https://ukvibe.org/r", "2026-11-26", "Review of Odyssey (Concord Jazz, 2024).")


def chat(obj):
    return ok({"message": {"content": obj if isinstance(obj, str) else json.dumps(obj)}})


def test_parses_tracks_and_releases_from_json_reply():
    reply = {"items": [{"id": "a", "music": [
        {"kind": "release", "artist": "Nubya Garcia", "title": "", "release": "Odyssey", "label": "Concord Jazz", "year": 2024, "version": ""},
        {"kind": "track", "artist": "Nubya Garcia", "title": "Solstice", "release": "Odyssey", "label": "", "year": None, "version": ""}]}]}
    got = parse_reply(json.dumps(reply), {"a"})
    assert got["a"][0] == Extracted("release", "Nubya Garcia", "", "Odyssey", "Concord Jazz", 2024, "")
    assert got["a"][1].title == "Solstice"


def test_drops_entries_without_artist_or_title():
    reply = {"items": [{"id": "a", "music": [
        {"kind": "track", "artist": "", "title": "X", "release": "", "label": "", "year": None, "version": ""},
        {"kind": "track", "artist": "Kokoroko", "title": "", "release": "", "label": "", "year": None, "version": ""},
        {"kind": "release", "artist": "Kokoroko", "title": "", "release": "Could We Be More", "label": "", "year": "2022", "version": ""},
        {"kind": "track", "artist": "Somebody", "title": "Song", "release": "", "label": "", "year": None, "version": ""}]},
        {"id": "zzz", "music": [{"kind": "track", "artist": "A", "title": "B"}]}]}
    got = parse_reply(json.dumps(reply), {"a"})
    assert [(e.artist, e.title or e.release) for e in got["a"]] == [("Kokoroko", "Could We Be More"), ("Somebody", "Song")]
    assert got["a"][0].year == 2022 and "zzz" not in got


def test_keeps_version_strings():
    reply = {"items": [{"id": "a", "music": [{"kind": "track", "artist": "Alfa Mist", "title": "Keep On", "release": "", "label": "",
                                               "year": None, "version": "Live at Abbey Road"}]}]}
    assert parse_reply(json.dumps(reply), {"a"})["a"][0].version == "Live at Abbey Road"


def test_bad_json_retries_once_then_notes():
    gw = FakeGateway({("POST", "ollama", "/api/chat"): [chat("not json"), chat("still not json")]})
    got, notes = extract(gw, "m", [item()])
    assert got == {} and len(gw.calls) == 2 and "extract" in notes[0]


def test_extract_batches_by_eight():
    reply = chat({"items": []})
    gw = FakeGateway({("POST", "ollama", "/api/chat"): [reply]})
    extract(gw, "m", [item(str(i)) for i in range(17)])
    assert len(gw.calls) == 3


def test_items_left_out_of_the_reply_count_as_no_music():  # review I6
    gw = FakeGateway({("POST", "ollama", "/api/chat"): [chat({"items": [{"id": "a", "music": []}]})]})
    got, notes = extract(gw, "m", [item("a"), item("b")])
    assert got == {"a": [], "b": []} and notes == []
