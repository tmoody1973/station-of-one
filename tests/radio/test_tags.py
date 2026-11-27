from station.radio.tags import tag_songs
from tests.fakes import FakeGateway, ok

URL = ("POST", "typesafe", "/v1/systemone")


def songs(n):
    return [{"id": f"c{i}", "artist": "Nubya Garcia", "title": f"T{i}", "album": "Odyssey", "release_date": "2024-09-20"} for i in range(n)]


def jev(n, energy="high", vocal=0.8):
    answers = {}
    for i in range(n):
        answers[f"energy_{i}"] = {"type": "choice", "choice": energy, "confidence": 0.7}
        answers[f"vocal_{i}"] = {"type": "noul", "noul": vocal}
    return ok({"model": "jev-1", "answers": answers})


def test_tags_map_choice_and_noul():
    gw = FakeGateway({URL: [jev(2, "high", 0.8)]})
    tags, raw, model, notes = tag_songs(gw, songs(2))
    assert tags["c0"] == {"energy": 3, "vocal": 1} and model == "jev-1" and notes == []
    assert raw["c1"]["energy"]["choice"] == "high" and raw["c1"]["vocal"]["noul"] == 0.8
    q = gw.calls[0][3]["questions"]
    assert q["energy_0"]["type"] == "choice" and set(q["energy_0"]["criteria"]) == {"low", "mid", "high"}
    assert q["vocal_1"]["type"] == "noul" and "sung vocals" in q["vocal_1"]["instructions"]
    low = tag_songs(FakeGateway({URL: [jev(1, "low", 0.2)]}), songs(1))[0]
    assert low["c0"] == {"energy": 1, "vocal": 0}


def test_tags_batch_by_20():
    gw = FakeGateway({URL: [jev(20), jev(5, "mid")]})
    tags, _, _, _ = tag_songs(gw, songs(25))
    assert len(gw.calls) == 2 and len(tags) == 25 and tags["c24"]["energy"] == 2


def test_a_failed_batch_is_a_note():
    gw = FakeGateway({URL: [jev(20), ok({"answers": {}})]})
    tags, _, _, notes = tag_songs(gw, songs(25))
    assert len(tags) == 20 and "c20" not in tags and notes and "5 songs" in notes[0]


def test_no_songs_no_call():
    gw = FakeGateway({})
    assert tag_songs(gw, []) == ({}, {}, None, []) and gw.calls == []
