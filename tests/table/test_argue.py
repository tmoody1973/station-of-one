import json

import pytest

from station.table.argue import PARTS, draft, problems
from tests.fakes import FakeGateway, ok

COMMENTS = [{"id": "hn:11", "author": "fontnerd42", "text": "Ligatures are a crutch."},
            {"id": "hn:12", "author": "mallory", "text": "Intel One Mono reads better at small sizes."}]
STORY = {"id": "hn:1", "title": "Intel One Mono font", "source": "Hacker News"}


def reply(override=None):
    claims = [{"side": side, "part": part, "sources": ["hn:12"] if side == "anchor" else [],
               "text": f"Some posters say the {part} point for the {side} is sound."} for part in PARTS for side in ("anchor", "uncle")]
    for (side, part), text in (override or {}).items():
        next(c for c in claims if c["side"] == side and c["part"] == part)["text"] = text
    return ok({"message": {"content": "Here you go:\n" + json.dumps({"question": "Is Intel One Mono worth switching to?",
                                                                     "anchor_position": "Yes, it reads better.",
                                                                     "uncle_position": "No, it changes nothing.",
                                                                     "claims": claims})}})


def chat(*replies):
    return FakeGateway({("POST", "ollama", "/api/chat"): list(replies)})


def test_parses_eight_claims():
    question, claims, positions = draft(chat(reply()), "m", STORY, COMMENTS)
    assert positions == ("Yes, it reads better.", "No, it changes nothing.")
    assert question == "Is Intel One Mono worth switching to?" and len(claims) == 8
    assert {(c.side, c.part) for c in claims} == {(s, p) for s in ("anchor", "uncle") for p in PARTS}
    assert claims[0].source_ids == ("hn:12",)


def test_unknown_source_id_rejected():
    bad = json.loads(json.loads(reply().body)["message"]["content"].split("\n", 1)[1])
    bad["claims"][0]["sources"] = ["hn:999"]
    assert any("hn:999" in p for p in problems(bad, COMMENTS))


def test_author_name_rejected_then_retry_succeeds():  # Review Focus 2
    gw = chat(reply({("uncle", "round1"): "Some posters, like fontnerd42, say ligatures are a crutch."}), reply())
    _, claims, _ = draft(gw, "m", STORY, COMMENTS)
    assert len(claims) == 8 and len(gw.calls) == 2
    assert "fontnerd42" in gw.calls[1][3]["messages"][-1]["content"]  # the retry is told what was wrong


def test_second_failure_raises():
    handle = reply({("anchor", "round2"): "As @mallory says, it reads better."})
    with pytest.raises(ValueError, match="mallory"):
        draft(chat(handle, handle), "m", STORY, COMMENTS)


def test_unattributed_or_long_claims_flagged():
    data = json.loads(json.loads(reply({("uncle", "opening"): "Monospace fonts are a government plot. " * 12}).body)
                      ["message"]["content"].split("\n", 1)[1])
    found = problems(data, COMMENTS)
    assert any("60 words" in p for p in found) and any("attribute" in p for p in found)


def test_cli_writes_claims_and_skips_quiet_day(tmp_path, monkeypatch):
    from station.__main__ import main

    monkeypatch.setattr("station.__main__.Gateway", lambda: chat(reply()))
    run = tmp_path / "2026-11-26"
    run.mkdir()
    (run / "topic.json").write_text(json.dumps({"story": STORY, "comments": COMMENTS, "scores": {}}))
    assert main(["table-argue", "--run", str(run)]) == 0
    out = json.loads((run / "claims.json").read_text())
    assert out["question"].startswith("Is Intel") and len(out["claims"]) == 8 and out["positions"]["uncle"] and out["claims"][0]["source_ids"] == ["hn:12"]
    quiet = tmp_path / "2026-11-27"
    quiet.mkdir()
    (quiet / "topic.json").write_text(json.dumps({"none": True, "reason": "x"}))
    assert main(["table-argue", "--run", str(quiet)]) == 0 and not (quiet / "claims.json").exists()


def test_each_side_must_state_one_position():  # the first real draft had the Anchor switch sides
    data = json.loads(json.loads(reply().body)["message"]["content"].split("\n", 1)[1])
    del data["uncle_position"]
    assert any("position" in p for p in problems(data, COMMENTS))
    data["uncle_position"] = data["anchor_position"]
    assert any("position" in p for p in problems(data, COMMENTS))
