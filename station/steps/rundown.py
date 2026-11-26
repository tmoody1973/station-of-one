"""Step 4, rundown: code applies the thresholds to Jev's answers. No model chooses what airs.

Rules: spec §2 and §4, decision 002 (top five at or above the 0.40 floor), and the Task 7
ruling that only stories (not comments) fill story slots.
"""
from __future__ import annotations

from dataclasses import dataclass

from station.config import Thresholds
from station.steps.judge import Judged

LEAD_SECONDS = 60
LEAD_BONUS_WITHOUT_CORRECTIONS = 30
DEFAULT_STORY_SECONDS = 40
ALMOST_COUNT = 5


@dataclass(frozen=True)
class Rundown:
    stories: tuple[Judged, ...]
    seconds: dict[str, int]
    overheard: Judged | None
    dropped_ids: tuple[str, ...]
    almost: tuple[Judged, ...]
    short: bool
    corrections: bool

    def to_dict(self) -> dict:
        return {"stories": [s.to_dict() for s in self.stories], "seconds": self.seconds,
                "overheard": self.overheard.to_dict() if self.overheard else None,
                "dropped_ids": list(self.dropped_ids), "almost": [a.to_dict() for a in self.almost],
                "short": self.short, "corrections": self.corrections}

    @classmethod
    def from_dict(cls, d: dict) -> "Rundown":
        return cls(tuple(Judged.from_dict(s) for s in d["stories"]), d["seconds"],
                   Judged.from_dict(d["overheard"]) if d["overheard"] else None, tuple(d["dropped_ids"]),
                   tuple(Judged.from_dict(a) for a in d["almost"]), d["short"], d["corrections"])


def _rank(items: list[Judged]) -> list[Judged]:
    return sorted(items, key=lambda x: (-x.matter_week, x.post.id))


def _mix_beats(ranked: list[Judged], limit: int) -> list[Judged]:
    """Best eligible story from each beat first, then the rest by score (Tarik, Nov 26).
    Returned in score order, so the lead is still the highest score overall."""
    picked: list[Judged] = []
    for s in ranked:
        if s.post.beat not in {p.post.beat for p in picked}:
            picked.append(s)
    for s in ranked:
        if s not in picked:
            picked.append(s)
    chosen = picked[:limit]
    return [s for s in ranked if s in chosen]


def select(judged: list[Judged], t: Thresholds, first_of_day: bool,
           seconds: dict[str, int] | None = None) -> Rundown:
    dropped = [x for x in judged if x.private_harm >= t.private_harm_max_probability]
    kept = [x for x in judged if x.private_harm < t.private_harm_max_probability]
    stories_pool = [x for x in kept if x.post.kind == "story" and x.same_as is None]
    eligible = [x for x in stories_pool
                if not x.is_reaction and x.part != "none" and x.matter_week >= t.air_min_probability]
    stories = _mix_beats(_rank(eligible), t.max_stories)
    aired_ids = {s.post.id for s in stories}
    almost = [x for x in _rank(stories_pool) if x.post.id not in aired_ids][:ALMOST_COUNT]
    comments = [x for x in kept if x.post.kind == "comment" and x.part == "overheard"]
    overheard = max(comments, key=lambda x: (x.part_probability("overheard"), x.post.id), default=None)

    corrections = False  # should-have; not built this weekend (plan "Later" section)
    secs: dict[str, int] = {}
    for i, s in enumerate(stories):
        if i == 0:
            secs[s.post.id] = LEAD_SECONDS + (0 if corrections else LEAD_BONUS_WITHOUT_CORRECTIONS)
        else:
            secs[s.post.id] = (seconds or {}).get(s.post.id, DEFAULT_STORY_SECONDS)
    return Rundown(stories=tuple(stories), seconds=secs, overheard=overheard,
                   dropped_ids=tuple(x.post.id for x in dropped), almost=tuple(almost),
                   short=len(stories) < t.min_stories, corrections=corrections)
