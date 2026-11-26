from station.store import record_episode, season_record
from station.table.argue import Claim
from station.table.referee import Ruling, points, referee, verdict
from tests.fakes import FakeGateway, ok

COMMENTS = [{"id": "hn:11", "text": "Ligatures are a crutch."}, {"id": "hn:12", "text": "It reads better small."}]
CLAIMS = [Claim(side, part, f"Some posters say {side} {part}.", ("hn:12",) if side == "anchor" else ("hn:11",))
          for part in ("opening", "round1", "round2", "round3") for side in ("anchor", "uncle")]


def jev(pairs):
    answers = {}
    for k, (t, a) in enumerate(pairs):
        answers |= {f"true_{k}": {"type": "noul", "noul": t}, f"answered_{k}": {"type": "noul", "noul": a}}
    return FakeGateway({("POST", "typesafe", "/v1/systemone"): [ok({"model": "jev-1.14.0", "answers": answers})]})


def test_one_request_two_questions_per_round_claim():
    gw = jev([(0.8, 0.9), (0.2, 0.3), (0.7, 0.6), (0.4, 0.2), (0.6, 0.7), (0.1, 0.9)])
    rulings, model = referee(gw, "Q?", CLAIMS, COMMENTS)
    (_, _, _, req), = gw.calls
    assert set(req["questions"]) == {f"{q}_{k}" for q in ("true", "answered") for k in range(6)}
    first = req["state"]["claims"][0]
    assert first["side"] == "anchor" and first["part"] == "round1" and first["sources"] == [{"id": "hn:12", "text": "It reads better small."}]
    assert [r.claim_index for r in rulings] == [2, 3, 4, 5, 6, 7] and rulings[0].p_true == 0.8 and model == "jev-1.14.0"


def test_points_and_winner():
    assert points(Ruling(2, "anchor", "round1", 0.8, 0.9)) == 1.05 and points(Ruling(3, "uncle", "round1", 0.2, 0.3)) == 0.2
    rs = [Ruling(2, "anchor", "round1", 0.8, 0.9), Ruling(3, "uncle", "round1", 0.2, 0.3)]
    v = verdict(rs)
    assert v == {"anchor": 1.05, "uncle": 0.2, "winner": "anchor"}


def test_draw_within_005():  # Review Focus 4
    rs = [Ruling(2, "anchor", "round1", 0.50, 0.1), Ruling(3, "uncle", "round1", 0.53, 0.1)]
    assert verdict(rs)["winner"] == "draw"


def test_record_counts_wins_and_draws(make_db):
    db = make_db()
    record_episode(db, "2026-11-26", "Q1?", 2.1, 1.4, "anchor", "hn:1")
    record_episode(db, "2026-11-27", "Q2?", 1.0, 1.9, "uncle", "hn:2")
    record_episode(db, "2026-11-28", "Q3?", 1.5, 1.5, "draw", "hn:3")
    record_episode(db, "2026-11-28", "Q3?", 1.5, 1.6, "uncle", "hn:3")  # a re-run replaces that day's result
    assert season_record(db) == {"anchor": 1, "uncle": 2, "draw": 0}


def test_cli_writes_rulings_records_episode_and_logs(tmp_path, monkeypatch):
    import json
    from dataclasses import asdict

    from station.__main__ import main
    from station.store import open_db

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    monkeypatch.setattr("station.__main__.Gateway", lambda: jev([(0.8, 0.9), (0.2, 0.3), (0.7, 0.6), (0.4, 0.2), (0.6, 0.7), (0.1, 0.9)]))
    run = tmp_path / "2026-11-26"
    run.mkdir()
    (run / "topic.json").write_text(json.dumps({"story": {"id": "hn:1", "title": "T"}, "comments": COMMENTS}))
    (run / "claims.json").write_text(json.dumps({"question": "Q?", "positions": {}, "claims": [asdict(c) for c in CLAIMS]}))
    assert main(["table-referee", "--run", str(run)]) == 0
    out = json.loads((run / "rulings.json").read_text())
    assert len(out["rulings"]) == 6 and out["verdict"]["winner"] == "anchor" and out["record"] == {"anchor": 1, "uncle": 0, "draw": 0}
    db = open_db(tmp_path / "s.db")
    assert db.execute("SELECT COUNT(*) FROM decisions WHERE question_id IN ('table_true','table_answered')").fetchone()[0] == 12
