from station.radio.extract import Extracted
from station.radio.fit import fit_scores
from station.radio.model import load_station
from station.radio.poll import FeedItem
from tests.fakes import FakeGateway, ok

IT = FeedItem("a", "UK Vibe", "g", "Odyssey review", "https://x", "2026-11-26", "Nubya Garcia's Odyssey, reviewed.")


def cands(n):
    return [(f"c{i}", Extracted("track", "Nubya Garcia", f"T{i}", "Odyssey", "", 2024, ""), IT) for i in range(n)]


def jev(n, start=0):
    return ok({"model": "jev-1", "answers": {f"fit_{i}": {"type": "noul", "noul": 0.5 + (start + i) / 100} for i in range(n)}})


def test_fit_batches_by_25():
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [jev(25), jev(5, 25)]})
    scores, raw, model, _ = fit_scores(gw, load_station("uk-jazz"), cands(30))
    assert len(gw.calls) == 2 and len(scores) == 30 and model == "jev-1"
    assert scores["c29"] == 0.79 and raw["c0"]["noul"] == 0.5


def test_fit_state_carries_brief_seeds_and_excerpt():
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [jev(1)]})
    fit_scores(gw, load_station("uk-jazz"), cands(1))
    body = gw.calls[0][3]
    assert "London first" in body["state"]["station"]["brief"] and "Ezra Collective" in body["state"]["station"]["seed_artists"]
    c = body["state"]["candidates"][0]
    assert c["artist"] == "Nubya Garcia" and c["found_in"]["excerpt"].startswith("Nubya Garcia")
    assert "brief" in body["questions"]["fit_0"]["instructions"]


def test_no_candidates_no_call():
    gw = FakeGateway({})
    assert fit_scores(gw, load_station("uk-jazz"), []) == ({}, {}, None, []) and gw.calls == []


def test_a_failed_batch_keeps_earlier_scores():  # review I5
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [jev(25), ok({"e": 1}, status=500)]})
    scores, raw, model, notes = fit_scores(gw, load_station("uk-jazz"), cands(30))
    assert len(scores) == 25 and any("fit" in n for n in notes)
