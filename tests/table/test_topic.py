from station.table.threads import Thread
from station.table.topic import pick_topic, score_threads
from tests.fakes import FakeGateway, ok
from tests.table.test_threads import p


def thread(i, n=7):
    return Thread(p(f"hn:{i}", "story", f"Story {i}"), tuple(p(f"hn:{i}{k}", "comment", f"Comment on: Story {i}") for k in range(n)))


def jev(per_thread):
    answers = {}
    for i, (d, lo, hot) in enumerate(per_thread):
        answers |= {f"dispute_{i}": {"type": "noul", "noul": d}, f"low_stakes_{i}": {"type": "noul", "noul": lo},
                    f"hot_topic_{i}": {"type": "noul", "noul": hot}}
    return FakeGateway({("POST", "typesafe", "/v1/systemone"): [ok({"model": "jev-1.14.0", "answers": answers})]})


def test_one_request_three_questions_per_thread():
    gw = jev([(0.8, 0.9, 0.1), (0.4, 0.9, 0.0)])
    scored, model = score_threads(gw, [thread(1), thread(2)])
    (_, _, _, req), = gw.calls
    assert set(req["questions"]) == {"dispute_0", "low_stakes_0", "hot_topic_0", "dispute_1", "low_stakes_1", "hot_topic_1"}
    assert "threads[0]" in req["questions"]["hot_topic_0"]["instructions"]
    assert req["state"]["threads"][0]["title"] == "Story 1" and len(req["state"]["threads"][0]["comments"]) == 7
    assert scored[0] == {"story_id": "hn:1", "dispute": 0.8, "low_stakes": 0.9, "hot_topic": 0.1} and model == "jev-1.14.0"


def test_pick_highest_passing_both():
    scored = [{"story_id": "a", "dispute": 0.95, "low_stakes": 0.5, "hot_topic": 0.0},  # not low-stakes enough
              {"story_id": "b", "dispute": 0.7, "low_stakes": 0.8, "hot_topic": 0.0},
              {"story_id": "c", "dispute": 0.9, "low_stakes": 0.9, "hot_topic": 0.0}]
    assert pick_topic(scored)["story_id"] == "c"


def test_hot_topic_never_picked():
    scored = [{"story_id": "a", "dispute": 0.99, "low_stakes": 0.99, "hot_topic": 0.6},
              {"story_id": "b", "dispute": 0.7, "low_stakes": 0.7, "hot_topic": 0.1}]
    assert pick_topic(scored)["story_id"] == "b"


def test_no_qualifying_thread_returns_none():  # Review Focus 1
    assert pick_topic([{"story_id": "a", "dispute": 0.3, "low_stakes": 0.9, "hot_topic": 0.0}]) is None
    assert pick_topic([]) is None


def test_cli_writes_topic_and_logs_every_answer(tmp_path, monkeypatch, make_db):
    import json

    from station.__main__ import main
    from station.table import topic as topic_mod
    from tests.table.test_threads import add

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    from station.store import open_db

    db = open_db(tmp_path / "s.db")
    add(db, [p("hn:1", "story", "Fonts"), *[p(f"hn:1{k}", "comment", "Comment on: Fonts") for k in range(7)]])
    db.close()
    monkeypatch.setattr(topic_mod, "score_threads", lambda gw, ts: (
        [{"story_id": "hn:1", "dispute": 0.8, "low_stakes": 0.9, "hot_topic": 0.1}], "jev-1.14.0"))
    monkeypatch.setattr("station.__main__.Gateway", lambda: None)
    run = tmp_path / "table" / "2026-11-26"
    assert main(["table-topic", "--run", str(run)]) == 0
    out = json.loads((run / "topic.json").read_text())
    assert out["story"]["id"] == "hn:1" and len(out["comments"]) == 7 and out["scores"]["dispute"] == 0.8
    db = open_db(tmp_path / "s.db")
    logged = {r[0] for r in db.execute("SELECT question_id FROM decisions WHERE post_id = 'hn:1'")}
    assert logged == {"table_dispute", "table_low_stakes", "hot_topic"}


def test_cli_quiet_day_writes_none(tmp_path, monkeypatch):
    import json

    from station.__main__ import main

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    monkeypatch.setattr("station.__main__.Gateway", lambda: None)
    run = tmp_path / "table" / "2026-11-26"
    assert main(["table-topic", "--run", str(run)]) == 0
    assert json.loads((run / "topic.json").read_text()) == {"none": True, "reason": "no thread with 6 or more comments"}
