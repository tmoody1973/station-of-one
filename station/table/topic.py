"""Table step 2: Jev scores yesterday's threads (real dispute? low-stakes? hot topic?); code picks the
question: highest dispute × low_stakes among threads passing both, never a hot topic (spec §11, T1–T3)."""
from __future__ import annotations

from station.steps.judge import MODEL
from station.steps.topics import HOT_TOPIC_MAX, hot_topic_question
from station.table.threads import Thread

COMMENTS_PER_THREAD, COMMENT_CHARS = 12, 600


def _questions(i: int) -> dict:
    return {
        f"dispute_{i}": {"type": "noul", "instructions":
                         f"Do the comments in `threads[{i}]` show a real disagreement with two sides?"},
        f"low_stakes_{i}": {"type": "noul", "instructions":
                            f"Is `threads[{i}]` low-stakes (tools, habits, taste or a sports-bar argument) rather "
                            "than something that affects people's safety, money or rights?"},
        f"hot_topic_{i}": hot_topic_question(i, "threads"),
        # spec: posts likely to harm a private person never air. Saying who counts (Nov 28 calibration, check 25): the vaguer
        # "could discussing it harm a private individual?" scored harmless threads 0.14-0.51, so nothing passed the 0.20 cut;
        # this wording scored them 0.01-0.12 and threads naming a private person 0.95-0.97.
        f"private_harm_{i}": {"type": "noul", "instructions":
                              f"Does `threads[{i}]` name, identify or single out a private individual (a person who is "
                              "not a public figure; companies, products, projects and organizations are not private "
                              "individuals) in a way that discussing it on air could harm them?"},
    }


def _state(t: Thread) -> dict:
    return {"title": t.story.title, "source": t.story.source,
            "comments": [{"id": c.id, "text": c.text[:COMMENT_CHARS]} for c in t.comments[:COMMENTS_PER_THREAD]]}


def score_threads(gw, threads: list[Thread], limit: int = 25) -> tuple[list[dict], str | None]:
    """One Jev request per thread (Nov 28 calibration): in a shared request, answers bled between neighbouring threads."""
    scored, model = [], None
    for t in threads[:limit]:  # ponytail: sequential, ~0.3 s each (under 10 s a day); parallel if the limit grows
        resp = gw.json("POST", "typesafe", "/v1/systemone",
                       {"model": MODEL, "state": {"threads": [_state(t)]}, "questions": _questions(0)})
        a = resp["answers"]
        scored.append({"story_id": t.story.id, "dispute": float(a["dispute_0"]["noul"]),
                       "low_stakes": float(a["low_stakes_0"]["noul"]), "hot_topic": float(a["hot_topic_0"]["noul"]),
                       "private_harm": float(a["private_harm_0"]["noul"])})
        model = model or resp.get("model")
    return scored, model


def pick_topic(scored: list[dict], dispute_min: float = 0.6, low_stakes_min: float = 0.6,
               harm_max: float = 0.2) -> dict | None:
    ok = [s for s in scored if s["dispute"] >= dispute_min and s["low_stakes"] >= low_stakes_min
          and s["hot_topic"] < HOT_TOPIC_MAX and s.get("private_harm", 0.0) < harm_max]
    return max(ok, key=lambda s: s["dispute"] * s["low_stakes"], default=None)
