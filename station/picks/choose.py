"""Music picks: Jev ranks the candidates, code chooses (plan 2026-11-27-music-picks, Task 3).

One batched TypeSafe request, one noul question per release. Code takes the top scores, at most one per
source, and never repeats a release picked in the last week. A language model never picks.
"""
from __future__ import annotations

from station.picks.sources import Pick
from station.steps.judge import MODEL

QUESTION = "Is the new release in `releases[{i}]` likely to interest a public-radio listener who follows independent music?"


def key(pick: Pick) -> str:
    return f"{pick.kind}:{pick.embed_id}"


def rank(gw, picks: list[Pick]) -> tuple[list[tuple[Pick, float]], dict[str, dict], str | None]:
    """Returns (picks with Jev's score, highest first; raw answers by key, for the decision log; model)."""
    if not picks:
        return [], {}, None
    state = {"releases": [{"title": p.title, "artist": p.artist, "from": p.source, "kind": p.kind} for p in picks]}
    questions = {f"interest_{i}": {"type": "noul", "instructions": QUESTION.format(i=i)} for i in range(len(picks))}
    resp = gw.json("POST", "typesafe", "/v1/systemone", {"model": MODEL, "state": state, "questions": questions})
    raw = {key(p): resp["answers"][f"interest_{i}"] for i, p in enumerate(picks)}
    ranked = sorted(((p, float(raw[key(p)]["noul"])) for p in picks), key=lambda x: -x[1])
    return ranked, raw, resp.get("model")


def choose(ranked: list[tuple[Pick, float]], count: int, recent: set[str]) -> list[tuple[Pick, float]]:
    chosen, sources, seen = [], set(), set(recent)
    for pick, score in ranked:
        if pick.source in sources or key(pick) in seen:
            continue
        chosen.append((pick, score))
        sources.add(pick.source)
        seen.add(key(pick))
        if len(chosen) == count:
            break
    return chosen
