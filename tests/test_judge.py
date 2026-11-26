import pytest

from station.gateway import Response
from station.steps.judge import (
    PER_POST_QUESTIONS, Judged, build_request, judge_all, judge_seconds, seconds_from_score,
)
from station.store import Post, open_db
from tests.conftest import load_fixture
from tests.fakes import FakeGateway, ok


def post(pid="hn:1", text="Mozilla ends Firefox ESR 115 support on March 1."):
    return Post(pid, "Hacker News", "ai-dev", "story", "u", "Firefox ESR 115 ends", "https://ex.com/a", text,
                "2026-11-27T14:00:00Z", {"points": 10}, "public")


def jev(answers, model="jev-1.14.0", tokens=700):
    return ok({"model": model, "answers": answers, "usage": {"input_tokens": tokens, "output_tokens": 50}})


FIVE = {"matter_week": {"type": "noul", "noul": 0.55},
        "new_or_reaction": {"type": "choice", "choice": "new_information", "confidence": 0.4,
                            "probabilities": {"new_information": 0.7, "reaction": 0.3}},
        "part": {"type": "choice", "choice": "story", "confidence": 0.8,
                 "probabilities": {"lead": 0.1, "story": 0.8, "overheard": 0.05, "none": 0.05}},
        "primary_source": {"type": "noul", "noul": 0.6},
        "private_harm": {"type": "noul", "noul": 0.05}}


def test_request_shape_matches_check1():
    req = build_request(post(), earlier=[])
    assert req["model"] == "jev-latest" and set(req["questions"]) == set(PER_POST_QUESTIONS)
    assert req["state"]["post"]["text"] == post().text and req["state"]["post"]["title"] == "Firefox ESR 115 ends"
    assert req["questions"]["matter_week"]["type"] == "noul"
    assert set(req["questions"]["part"]["criteria"]) == {"lead", "story", "overheard", "none"}


def test_parses_check1_fixture():
    j = Judged.from_response(post(), load_fixture("jev_response.json"))
    assert (j.matter_week, j.private_harm, j.part, j.model) == (0.48, 0.08, "story", "jev-1.14.0")
    assert j.is_reaction is False and j.part_probability("overheard") == 0.05


def test_every_answer_logged(tmp_path):
    db = open_db(tmp_path / "s.db")
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [jev(FIVE)]})
    judged = judge_all(gw, db, [post()], candidates=[])
    rows = db.execute("SELECT question_id, model FROM decisions ORDER BY question_id").fetchall()
    assert [r[0] for r in rows] == sorted(PER_POST_QUESTIONS) and {r[1] for r in rows} == {"jev-1.14.0"}
    assert judged[0].input_tokens == 700


def test_same_story_candidate_adds_question(tmp_path):
    a, b = post("hn:1"), post("reddit:2")
    answers = {**FIVE, "same_story_0": {"type": "noul", "noul": 0.9}}
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [jev(FIVE), jev(answers)]})
    judged = judge_all(gw, open_db(tmp_path / "s.db"), [a, b], candidates=[("hn:1", "reddit:2")], concurrency=1)
    sent = [c[3] for c in gw.calls]
    assert "same_story_0" in sent[1]["questions"] and sent[1]["state"]["earlier_posts"][0]["title"] == a.title
    assert {j.post.id: j.same_as for j in judged} == {"hn:1": None, "reddit:2": "hn:1"}


def test_failed_post_is_skipped_not_fatal(tmp_path):
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [Response(400, {}, b'{"error":"max_tokens_exceeded"}'), jev(FIVE)]})
    judged = judge_all(gw, open_db(tmp_path / "s.db"), [post("hn:1"), post("hn:2")], candidates=[], concurrency=1)
    assert [j.post.id for j in judged] == ["hn:2"]


def test_seconds_from_score():
    assert seconds_from_score(0.0) == 20 and seconds_from_score(3.0) == 45 and seconds_from_score(0.92) == 28


def test_judge_seconds_one_request_for_all_stories():
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [jev({
        "seconds_0": {"type": "score", "score": 3.0, "confidence": 1, "legend": {}, "probabilities": {}},
        "seconds_1": {"type": "score", "score": 0.0, "confidence": 1, "legend": {}, "probabilities": {}}})]})
    assert judge_seconds(gw, [post("hn:1"), post("hn:2")]) == {"hn:1": 45, "hn:2": 20}
    assert len(gw.calls) == 1 and "`stories[1]`" in gw.calls[0][3]["questions"]["seconds_1"]["instructions"]
