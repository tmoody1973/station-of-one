"""Fixes from the final review of The Table (Nov 26). Each test failed before its fix."""
import json
from dataclasses import asdict

from station.config import load_prefs
from station.store import open_db
from station.table.argue import problems
from station.table.topic import pick_topic
from tests.table.test_argue import COMMENTS, reply

PREFS = load_prefs()


def drafted():
    return json.loads(json.loads(reply().body)["message"]["content"].split("\n", 1)[1])


def test_handles_in_question_or_positions_rejected():  # finding 3
    d = drafted()
    d["question"] = "Is fontnerd42 right about tabs?"
    assert any("fontnerd42" in p for p in problems(d, COMMENTS))
    d = drafted()
    d["anchor_position"] = "Yes, as @bob99 and u/someone say."
    assert any("handle" in p for p in problems(d, COMMENTS))


def test_percentages_and_winner_phrases_in_claims_rejected():  # finding 4
    d = drafted()
    d["claims"][2]["text"] = "Some posters say 80% of devs use tabs."
    assert any("percent" in p or "number" in p for p in problems(d, COMMENTS))
    d = drafted()
    d["claims"][3]["text"] = "Some posters say the Uncle wins this one."
    assert problems(d, COMMENTS)


def test_private_harm_thread_never_picked():  # finding 5
    scored = [{"story_id": "a", "dispute": 0.9, "low_stakes": 0.9, "hot_topic": 0.0, "private_harm": 0.3},
              {"story_id": "b", "dispute": 0.7, "low_stakes": 0.7, "hot_topic": 0.0, "private_harm": 0.05}]
    assert pick_topic(scored, harm_max=0.2)["story_id"] == "b"


def test_topic_request_asks_private_harm():  # finding 5
    from station.table.topic import score_threads
    from tests.fakes import FakeGateway, ok
    from tests.table.test_topic import thread

    answers = {f"{q}_0": {"type": "noul", "noul": v} for q, v in
               (("dispute", .8), ("low_stakes", .9), ("hot_topic", .1), ("private_harm", .02))}
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [ok({"model": "m", "answers": answers})]})
    scored, _ = score_threads(gw, [thread(1)])
    assert "private_harm_0" in gw.calls[0][3]["questions"] and scored[0]["private_harm"] == 0.02


def _referee_run(tmp_path, monkeypatch):
    from station.table.argue import Claim
    from tests.table.test_referee import CLAIMS, jev

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    monkeypatch.setattr("station.__main__.Gateway", lambda: jev([(0.8, 0.9), (0.2, 0.3), (0.7, 0.6), (0.4, 0.2), (0.6, 0.7), (0.1, 0.9)]))
    run = tmp_path / "2026-11-26"
    run.mkdir()
    (run / "topic.json").write_text(json.dumps({"story": {"id": "hn:1", "title": "T"}, "comments": COMMENTS}))
    (run / "claims.json").write_text(json.dumps({"question": "Q?", "positions": {}, "claims": [asdict(c) for c in CLAIMS]}))
    return run


def test_season_record_only_counts_published_episodes(tmp_path, monkeypatch):  # finding 1
    from station.__main__ import main

    run = _referee_run(tmp_path, monkeypatch)
    assert main(["table-referee", "--run", str(run)]) == 0
    assert json.loads((run / "rulings.json").read_text())["record"] == {"anchor": 1, "uncle": 0, "draw": 0}
    db = open_db(tmp_path / "s.db")
    assert db.execute("SELECT COUNT(*) FROM table_episodes").fetchone()[0] == 0  # not recorded until published


def _publish(tmp_path, monkeypatch, archive_fails=False):
    import station.steps.archive as arc
    import station.table.build as tb
    from station.__main__ import main

    run = _referee_run(tmp_path, monkeypatch)
    main(["table-referee", "--run", str(run)])
    monkeypatch.setattr(tb, "publish_table", lambda gw, r, prefs: ["a", "b", "c"])

    def fake_archive(gw, r, files):
        if archive_fails:
            raise RuntimeError("Box 503")
        return "box1"
    monkeypatch.setattr(arc, "archive", fake_archive)
    assert main(["table-publish", "--run", str(run)]) == 0
    return run


def test_publish_records_the_episode_and_marks_it(tmp_path, monkeypatch):  # findings 1, 2
    run = _publish(tmp_path, monkeypatch)
    db = open_db(tmp_path / "s.db")
    assert db.execute("SELECT winner FROM table_episodes WHERE day = '2026-11-26'").fetchone() == ("anchor",)
    assert (run / "published").exists()


def test_archive_failure_does_not_fail_publish(tmp_path, monkeypatch):  # finding 6
    run = _publish(tmp_path, monkeypatch, archive_fails=True)
    step = json.loads((run / "run_log.json").read_text())["steps"][-1]
    assert step["status"] == "done" and any("Box" in n for n in step["notes"]) and (run / "published").exists()


def test_unpublished_episodes_not_listed(tmp_path):  # finding 2
    from station.steps.page import table_episodes

    for day, published in (("2026-11-25", True), ("2026-11-26", False)):
        (tmp_path / day).mkdir()
        (tmp_path / day / "table.json").write_text(json.dumps({"id": f"table-{day}", "day": day}))
        if published:
            (tmp_path / day / "published").write_text("")
    assert [e["day"] for e in table_episodes(tmp_path)] == ["2026-11-25"]


def test_rerun_clears_published_marker_first(tmp_path, monkeypatch):  # finding 2, second scenario
    from station import __main__ as cli

    monkeypatch.setenv("STATION_TABLE", str(tmp_path))
    (tmp_path / "2026-11-26").mkdir()
    (tmp_path / "2026-11-26" / "published").write_text("")
    seen = []

    def topic(run):
        seen.append((run / "published").exists())
        raise RuntimeError("stop")
    monkeypatch.setitem(cli.COMMANDS, "table-topic", topic)
    try:
        cli.run_table("2026-11-26")
    except RuntimeError:
        pass
    assert seen == [False]


def test_totals_shown_with_two_decimals():  # minor 2, re-graded: "2.3 to 2.3, the Anchor takes it"
    from station.table.script import parts
    from tests.table.test_table_script import CLAIMS, RECORD, RULINGS, TOPIC

    ps = parts({"lines": {}}, CLAIMS, RULINGS, {"anchor": 2.34, "uncle": 2.28, "winner": "anchor"}, RECORD, TOPIC, "Q?")
    assert "2.34" in ps[5].turns[0].text and "2.28" in ps[5].turns[0].text
