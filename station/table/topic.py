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
        f"private_harm_{i}": {"type": "noul", "instructions":  # spec: posts likely to harm a private person never air
                              f"Could discussing `threads[{i}]` on air harm a private individual?"},
    }


def _state(t: Thread) -> dict:
    return {"title": t.story.title, "source": t.story.source,
            "comments": [{"id": c.id, "text": c.text[:COMMENT_CHARS]} for c in t.comments[:COMMENTS_PER_THREAD]]}


def score_threads(gw, threads: list[Thread], limit: int = 25) -> tuple[list[dict], str | None]:
    threads = threads[:limit]
    if not threads:
        return [], None
    req = {"model": MODEL, "state": {"threads": [_state(t) for t in threads]},
           "questions": {k: v for i in range(len(threads)) for k, v in _questions(i).items()}}
    resp = gw.json("POST", "typesafe", "/v1/systemone", req)
    a = resp["answers"]
    scored = [{"story_id": t.story.id, "dispute": float(a[f"dispute_{i}"]["noul"]),
               "low_stakes": float(a[f"low_stakes_{i}"]["noul"]), "hot_topic": float(a[f"hot_topic_{i}"]["noul"]),
               "private_harm": float(a[f"private_harm_{i}"]["noul"])}
              for i, t in enumerate(threads)]
    return scored, resp.get("model")


def pick_topic(scored: list[dict], dispute_min: float = 0.6, low_stakes_min: float = 0.6,
               harm_max: float = 0.2) -> dict | None:
    ok = [s for s in scored if s["dispute"] >= dispute_min and s["low_stakes"] >= low_stakes_min
          and s["hot_topic"] < HOT_TOPIC_MAX and s.get("private_harm", 0.0) < harm_max]
    return max(ok, key=lambda s: s["dispute"] * s["low_stakes"], default=None)
