"""Hot-topic screen (Tarik, Nov 26): the daily video skips elections, contested policy, religion and
health. Jev answers; code applies the 50% threshold. The Table reuses the same question."""
from station.steps.topics import HOT_TOPIC_MAX, hot_topic_scores
from station.steps.video import candidates, pick
from tests.fakes import FakeGateway, ok
from tests.test_captions import day


def test_one_request_with_a_question_per_story():
    stories = [{"id": "a", "headline": "Court weighs AR-15 bans", "summary": "..."},
               {"id": "b", "headline": "Titian self-portrait found", "summary": "..."}]
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [ok({"model": "jev-1.14.0", "answers": {
        "hot_topic_0": {"type": "noul", "noul": 0.93}, "hot_topic_1": {"type": "noul", "noul": 0.04}}})]})
    scores, answers, model = hot_topic_scores(gw, stories)
    assert scores == {"a": 0.93, "b": 0.04} and model == "jev-1.14.0" and set(answers) == {"a", "b"}
    (_, _, _, req), = gw.calls
    assert req["state"]["stories"][0] == {"headline": "Court weighs AR-15 bans", "summary": "..."}
    assert set(req["questions"]) == {"hot_topic_0", "hot_topic_1"} and HOT_TOPIC_MAX == 0.5


def test_no_stories_no_request():
    gw = FakeGateway({})
    assert hot_topic_scores(gw, []) == ({}, {}, None) and gw.calls == []


def test_video_skips_excluded_story_for_next_best():
    ns = day(("2026-11-26T13", [("court", 0.81, 40), ("art", 0.6, 35), ("tiny", 0.95, 10)]))
    assert [s["id"] for _, s in candidates(ns)] == ["court", "art"]  # only chapters long enough, best first
    _, story, _, _ = pick(ns, exclude={"court"})
    assert story["id"] == "art"
