from station.config import Thresholds
from station.steps.judge import Judged
from station.steps.rundown import select
from station.store import Post

T = Thresholds(air_min_probability=0.40, private_harm_max_probability=0.20, min_stories=3, max_stories=5)


def j(pid, mw, harm=0.05, part="story", reaction=False, kind="story", overheard_p=0.0, same_story=None):
    answers = {
        "matter_week": {"type": "noul", "noul": mw},
        "private_harm": {"type": "noul", "noul": harm},
        "primary_source": {"type": "noul", "noul": 0.6},
        "new_or_reaction": {"type": "choice", "choice": "reaction" if reaction else "new_information",
                            "probabilities": {}, "confidence": 0.5},
        "part": {"type": "choice", "choice": part, "confidence": 0.5,
                 "probabilities": {"lead": 0, "story": 0, "overheard": overheard_p, "none": 0}},
    }
    earlier = ()
    if same_story is not None:
        answers["same_story_0"] = {"type": "noul", "noul": same_story}
        earlier = ("hn:earlier",)
    post = Post(pid, "HN", "ai-dev", kind, "u", f"Title {pid}", f"https://ex.com/{pid}", "", "2026-11-27T14:00:00Z", {}, "public")
    return Judged(post, answers, "jev-1.14.0", earlier)


def ids(js):
    return [x.post.id for x in js]


def test_private_harm_at_threshold_dropped():
    r = select([j("a", 0.6, harm=0.20), j("b", 0.6, harm=0.19)], T, first_of_day=False)
    assert ids(r.stories) == ["b"] and r.dropped_ids == ("a",)


def test_floor_is_at_or_above():
    r = select([j("a", 0.40), j("b", 0.39)], T, first_of_day=False)
    assert ids(r.stories) == ["a"]


def test_top_five_only_and_lead_is_highest():
    r = select([j(str(i), 0.40 + i / 100) for i in range(8)], T, first_of_day=False)
    assert ids(r.stories) == ["7", "6", "5", "4", "3"]


def test_reaction_none_and_merged_excluded():
    r = select([j("a", 0.6, reaction=True), j("b", 0.6, part="none"), j("c", 0.6, same_story=0.9), j("d", 0.5)],
               T, first_of_day=False)
    assert ids(r.stories) == ["d"]


def test_comments_never_stories():  # real Nov 27 data: comments outscore stories
    r = select([j("c", 0.69, kind="comment", part="overheard", overheard_p=0.7), j("s", 0.45)], T, first_of_day=False)
    assert ids(r.stories) == ["s"] and r.overheard.post.id == "c"


def test_overheard_needs_overheard_part_and_not_dropped():
    r = select([j("c1", 0.5, kind="comment", part="story", overheard_p=0.9),
                j("c2", 0.5, kind="comment", part="overheard", overheard_p=0.6, harm=0.3)], T, first_of_day=False)
    assert r.overheard is None


def test_short_when_fewer_than_three():  # Review Focus 3
    assert select([j("a", 0.5), j("b", 0.5)], T, first_of_day=False).short is True
    assert select([j(c, 0.5) for c in "abc"], T, first_of_day=False).short is False


def test_dropped_never_in_almost():
    r = select([j("x", 0.39, harm=0.5), j("y", 0.39), j("z", 0.9)], T, first_of_day=False)
    assert ids(r.almost) == ["y"]


def test_almost_is_top_five_not_aired():
    r = select([j(str(i), 0.30 + i / 100) for i in range(12)], T, first_of_day=False)
    assert len(r.almost) == 5 and not set(ids(r.almost)) & set(ids(r.stories))
    assert ids(r.almost) == sorted(ids(r.almost), key=lambda x: -int(x))


def test_lead_gets_90_without_corrections_and_jev_seconds_for_others():
    r = select([j("a", 0.6), j("b", 0.5)], T, first_of_day=False, seconds={"b": 28})
    assert r.corrections is False and r.seconds == {"a": 90, "b": 28}
