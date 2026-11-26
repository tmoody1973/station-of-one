import json

from station.table.argue import Claim
from station.table.referee import Ruling
from station.table.script import STATION_ID, parts, write_script
from tests.fakes import FakeGateway, ok

CLAIMS = [Claim(side, part, f"Some posters say {side} {part}.", ()) for part in ("opening", "round1", "round2", "round3")
          for side in ("anchor", "uncle")]
RULINGS = [Ruling(i, c.side, c.part, p, 0.6) for i, (c, p) in enumerate(zip(CLAIMS, [0, 0, .79, .68, .8, .72, .78, .77])) if i >= 2]
VERDICT = {"anchor": 2.87, "uncle": 2.67, "winner": "anchor"}
RECORD = {"anchor": 1, "uncle": 0, "draw": 0}
TOPIC = {"title": "Intel One Mono font", "source": "Hacker News"}


def delivered(override=None):
    lines = [{"side": c.side, "part": c.part, "text": f"Some posters say, in my words, {c.side} {c.part}."} for c in CLAIMS]
    for (side, part), text in (override or {}).items():
        next(x for x in lines if x["side"] == side and x["part"] == part)["text"] = text
    return ok({"message": {"content": json.dumps({"intro": "Welcome to The Table.", "lines": lines})}})


def built(*replies):
    gw = FakeGateway({("POST", "ollama", "/api/chat"): list(replies)})
    return parts(write_script(gw, "m", TOPIC, "Is it worth switching?", CLAIMS), CLAIMS, RULINGS, VERDICT, RECORD, TOPIC,
                 "Is it worth switching?"), gw


def test_rulings_inserted_verbatim_after_each_round_claim():
    ps, _ = built(delivered())
    r1 = next(p for p in ps if p.kind == "round1")
    assert [t.speaker for t in r1.turns] == ["Anchor", "Anchor", "Uncle", "Anchor"]
    assert r1.turns[1].text == "Jev's ruling. That claim: 79% likely true." and r1.turns[3].text == "Jev's ruling. That claim: 68% likely true."
    assert [p.kind for p in ps] == ["question", "opening", "round1", "round2", "round3", "verdict", "record"]


def test_verdict_and_record_are_code_written():
    ps, _ = built(delivered())
    v = next(p for p in ps if p.kind == "verdict")
    assert "2.9" in v.turns[0].text and "2.7" in v.turns[0].text and "The Anchor takes it" in v.turns[0].text
    rec = next(p for p in ps if p.kind == "record")
    assert "Anchor 1, Uncle 0" in rec.turns[0].text


def test_station_id_line_3_in_record_part():
    ps, _ = built(delivered())
    assert STATION_ID == "WNCL, broadcasting to a potential audience of one." and ps[-1].turns[-1].text.endswith(STATION_ID)


def test_writer_percentage_rejected_then_falls_back_to_checked_claims():  # Review Focus 3
    bad = delivered({("uncle", "round2"): "Some posters say this claim is 99% true and the Uncle wins."})
    ps, gw = built(bad, bad)
    assert len(gw.calls) == 2
    r2 = next(p for p in ps if p.kind == "round2")
    assert r2.turns[2].text == "Some posters say uncle round2."  # the checked claim text, not the writer's


def test_draw_verdict_line():
    p = parts({"intro": "Hi.", "lines": {}}, CLAIMS, RULINGS, {"anchor": 2.5, "uncle": 2.52, "winner": "draw"}, RECORD,
              TOPIC, "Q?")
    assert "a draw" in next(x for x in p if x.kind == "verdict").turns[0].text


def test_cli_writes_script(tmp_path, monkeypatch):
    from dataclasses import asdict

    from station.__main__ import main

    monkeypatch.setattr("station.__main__.Gateway", lambda: FakeGateway({("POST", "ollama", "/api/chat"): [delivered()]}))
    run = tmp_path / "2026-11-26"
    run.mkdir()
    (run / "topic.json").write_text(json.dumps({"story": {"id": "hn:1", **TOPIC}, "comments": []}))
    (run / "claims.json").write_text(json.dumps({"question": "Q?", "positions": {}, "claims": [asdict(c) for c in CLAIMS]}))
    (run / "rulings.json").write_text(json.dumps({"rulings": [asdict(r) for r in RULINGS], "verdict": VERDICT, "record": RECORD}))
    assert main(["table-script", "--run", str(run)]) == 0
    out = json.loads((run / "script.json").read_text())
    assert [p["kind"] for p in out["parts"]][-1] == "record" and out["fallback"] is False
    assert out["parts"][2]["turns"][1] == {"speaker": "Anchor", "text": "Jev's ruling. That claim: 79% likely true."}


def test_intro_that_asks_the_question_is_rejected():  # real run said the question twice
    from station.table.script import _issues

    lines = json.loads(json.loads(delivered().body)["message"]["content"])["lines"]
    assert _issues({"intro": "Welcome! Is Intel One Mono worth it?", "lines": lines})
    assert not _issues({"intro": "Welcome to The Table.", "lines": lines})
