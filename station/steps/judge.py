"""Step 3, judge: every post to Jev with the per-post questions; every answer logged.

Request and response shapes proven in check 1 (docs/THURSDAY-CHECKS.md). Jev decides; code
only reads the numbers. Question wording below is the check 1 wording.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from station.gateway import GatewayError
from station.store import Post, record_decision

MODEL = "jev-latest"
SAME_STORY_MIN = 0.5

PER_POST_QUESTIONS: dict[str, dict] = {
    "matter_week": {"type": "noul",
                    "instructions": "Will the news in `post` still matter to listeners a week from now?"},
    "new_or_reaction": {"type": "choice",
                        "instructions": "Is `post` new information, or a reaction to something already known?",
                        "criteria": {"new_information": "Reports a new fact, release, decision or event",
                                     "reaction": "Comments on, jokes about or reacts to news already out"}},
    "part": {"type": "choice",
             "instructions": "Which part of a five-minute newscast fits `post` best?",
             "criteria": {"lead": "The most important story of the hour",
                          "story": "A regular short news story",
                          "overheard": "A notable single comment worth quoting",
                          "none": "Not suitable for the newscast"}},
    "primary_source": {"type": "noul",
                       "instructions": "Is the central claim in `post` supported by a linked primary source?"},
    "private_harm": {"type": "noul", "instructions": "Could airing `post` harm a private individual?"},
}
SECONDS_LEVELS = ["A one-line mention", "A short item with one fact",
                  "A full story with context", "A story needing background and reaction"]


def same_story_question(i: int) -> dict:
    return {"type": "noul", "instructions": f"Is `post` about the same story as `earlier_posts[{i}]`?"}


def seconds_question(i: int) -> dict:
    return {"type": "score", "instructions": f"How much airtime does `stories[{i}]` deserve in a newscast?",
            "criteria": SECONDS_LEVELS}


def seconds_from_score(score: float, levels: int = 4) -> int:
    return round(20 + score / (levels - 1) * 25)


def _state_post(p: Post) -> dict:
    return {"source": p.source, "title": p.title, "url": p.url, "author": p.author,
            "posted_at": p.posted_at, "text": p.text[:4000], "engagement": p.engagement}


def build_request(post: Post, earlier: list[Post]) -> dict:
    questions = dict(PER_POST_QUESTIONS)
    for i in range(len(earlier)):
        questions[f"same_story_{i}"] = same_story_question(i)
    state = {"post": _state_post(post)}
    if earlier:
        state["earlier_posts"] = [_state_post(e) for e in earlier]
    return {"model": MODEL, "state": state, "questions": questions}


@dataclass(frozen=True)
class Judged:
    post: Post
    answers: dict
    model: str
    earlier_ids: tuple[str, ...] = ()
    input_tokens: int = 0

    @classmethod
    def from_response(cls, post: Post, response: dict, earlier_ids: tuple[str, ...] = ()) -> "Judged":
        return cls(post, response["answers"], response["model"], earlier_ids,
                   response.get("usage", {}).get("input_tokens", 0))

    @classmethod
    def from_dict(cls, d: dict) -> "Judged":
        return cls(Post(**d["post"]), d["answers"], d["model"], tuple(d.get("earlier_ids", ())), d.get("input_tokens", 0))

    def to_dict(self) -> dict:
        return {**asdict(self), "post": asdict(self.post)}

    @property
    def matter_week(self) -> float:
        return float(self.answers["matter_week"]["noul"])

    @property
    def private_harm(self) -> float:
        return float(self.answers["private_harm"]["noul"])

    @property
    def primary_source(self) -> float:
        return float(self.answers["primary_source"]["noul"])

    @property
    def part(self) -> str:
        return self.answers["part"]["choice"]

    def part_probability(self, name: str) -> float:
        return float(self.answers["part"]["probabilities"].get(name, 0.0))

    @property
    def is_reaction(self) -> bool:
        return self.answers["new_or_reaction"]["choice"] == "reaction"

    @property
    def same_as(self) -> str | None:
        for i, earlier_id in enumerate(self.earlier_ids):
            ans = self.answers.get(f"same_story_{i}")
            if ans and float(ans["noul"]) >= SAME_STORY_MIN:
                return earlier_id
        return None


def judge_all(gw, db, posts: list[Post], candidates: list[tuple[str, str]], concurrency: int = 8) -> list[Judged]:
    by_id = {p.id: p for p in posts}
    earlier: dict[str, list[Post]] = {}
    for first, second in candidates:
        if first in by_id and second in by_id:
            earlier.setdefault(second, []).append(by_id[first])

    def ask(p: Post):
        prior = earlier.get(p.id, [])
        try:
            resp = gw.json("POST", "typesafe", "/v1/systemone", build_request(p, prior))
        except GatewayError:
            return None
        return Judged.from_response(p, resp, tuple(e.id for e in prior))

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(ask, posts))
    asked_at = datetime.now(UTC).isoformat()
    judged = [j for j in results if j is not None]
    for j in judged:  # SQLite writes stay on this thread
        for qid, answer in j.answers.items():
            record_decision(db, j.post.id, qid, answer, j.model, asked_at)
    return judged


def judge_seconds(gw, stories: list[Post]) -> dict[str, int]:
    """One request for the whole rundown: how many seconds each chosen story deserves (20-45)."""
    if not stories:
        return {}
    req = {"model": MODEL, "state": {"stories": [_state_post(s) for s in stories]},
           "questions": {f"seconds_{i}": seconds_question(i) for i in range(len(stories))}}
    answers = gw.json("POST", "typesafe", "/v1/systemone", req)["answers"]
    return {s.id: seconds_from_score(float(answers[f"seconds_{i}"]["score"])) for i, s in enumerate(stories)}
