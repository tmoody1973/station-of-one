"""Hot-topic screen: Jev says whether a story is about elections, contested public policy, religion
or health. Code skips it at HOT_TOPIC_MAX or above. Used by the daily video (Tarik, Nov 26) and by
The Table (spec §11 excludes these topics in code)."""
from __future__ import annotations

from station.steps.judge import MODEL

HOT_TOPIC_MAX = 0.5


def hot_topic_question(i: int) -> dict:
    return {"type": "noul", "instructions": f"Is `stories[{i}]` mainly about elections, contested public policy "
                                            "(such as guns, abortion, immigration or court rulings on them), "
                                            "religion, or health?"}


def hot_topic_scores(gw, stories: list[dict]) -> tuple[dict[str, float], dict[str, dict], str | None]:
    """One request for all stories (dicts with id, headline, summary). Returns (probabilities, raw answers, model)."""
    if not stories:
        return {}, {}, None
    req = {"model": MODEL, "state": {"stories": [{"headline": s["headline"], "summary": s.get("summary", "")}
                                                 for s in stories]},
           "questions": {f"hot_topic_{i}": hot_topic_question(i) for i in range(len(stories))}}
    resp = gw.json("POST", "typesafe", "/v1/systemone", req)
    answers = {s["id"]: resp["answers"][f"hot_topic_{i}"] for i, s in enumerate(stories)}
    return {sid: float(a["noul"]) for sid, a in answers.items()}, answers, resp.get("model")
