from station.picks.choose import QUESTION, choose, key, rank
from station.picks.sources import Pick
from tests.fakes import FakeGateway, ok


def p(source, eid, kind="youtube"):
    return Pick(source, kind, eid, f"t{eid}", "a", "https://x", "")


def test_choose_one_per_source_top_scores():
    ranked = [(p("NPR Music", "aaaaaaaaaa1"), 0.9), (p("NPR Music", "aaaaaaaaaa2"), 0.8),
              (p("KEXP", "bbbbbbbbbb1"), 0.7), (p("Sub Pop", "123", "bandcamp"), 0.4), (p("COLORS", "ccccccccc11"), 0.2)]
    chosen = choose(ranked, 3, set())
    assert [c[0].embed_id for c in chosen] == ["aaaaaaaaaa1", "bbbbbbbbbb1", "123"]


def test_no_repeat_within_a_week():  # Review Focus 5
    ranked = [(p("NPR Music", "aaaaaaaaaa1"), 0.9), (p("KEXP", "aaaaaaaaaa1"), 0.85), (p("KEXP", "bbbbbbbbbb1"), 0.5)]
    chosen = choose(ranked, 3, {key(p("x", "aaaaaaaaaa1"))})
    assert [c[0].embed_id for c in chosen] == ["bbbbbbbbbb1"]
    same_release_twice = [(p("NPR Music", "zzzzzzzzzz1"), 0.9), (p("KEXP", "zzzzzzzzzz1"), 0.8)]
    assert len(choose(same_release_twice, 3, set())) == 1


def test_rank_sends_one_batched_request():
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [ok({"model": "jev-1", "answers": {
        "interest_0": {"type": "noul", "noul": 0.3}, "interest_1": {"type": "noul", "noul": 0.8}}})]})
    ranked, raw, model = rank(gw, [p("A", "aaaaaaaaaa1"), p("B", "bbbbbbbbbb1")])
    assert [(r[0].source, r[1]) for r in ranked] == [("B", 0.8), ("A", 0.3)]
    assert raw[key(p("A", "aaaaaaaaaa1"))]["noul"] == 0.3 and model == "jev-1"
    body = gw.calls[0][3]
    assert len(gw.calls) == 1 and body["questions"]["interest_1"]["instructions"].startswith(QUESTION[:20])
    assert body["state"]["releases"][1]["title"] == "tbbbbbbbbbb1"


def test_rank_nothing_makes_no_call():
    gw = FakeGateway({})
    assert rank(gw, []) == ([], {}, None) and gw.calls == []
