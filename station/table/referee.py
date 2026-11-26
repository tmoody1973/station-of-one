"""Table step 4: Jev referees. Every round claim gets "how likely true?" and "did it answer the other
side?", in one request carrying both sides' cited comments. Code turns the answers into points and a
winner before any script exists, so the writer cannot pick the winner (spec §11, T5–T6)."""
from __future__ import annotations

from dataclasses import dataclass

from station.steps.judge import MODEL
from station.table.argue import Claim

ANSWERED_BONUS, DRAW_MARGIN = 0.25, 0.05


@dataclass(frozen=True)
class Ruling:
    claim_index: int  # position in the full 8-claim list
    side: str
    part: str
    p_true: float
    answered: float


def _questions(k: int) -> dict:
    return {f"true_{k}": {"type": "noul", "instructions":
                          f"How likely is `claims[{k}]` to be true, judged against its `sources` and the other side's?"},
            f"answered_{k}": {"type": "noul", "instructions":
                              f"Does `claims[{k}]` respond to the other side's argument rather than ignore it?"}}


def referee(gw, question: str, claims: list[Claim], comments: list[dict]) -> tuple[list[Ruling], str | None]:
    text = {c["id"]: c["text"][:600] for c in comments}
    scored = [(i, c) for i, c in enumerate(claims) if c.part != "opening"]
    state = {"question": question, "claims": [
        {"side": c.side, "part": c.part, "text": c.text, "sources": [{"id": s, "text": text.get(s, "")} for s in c.source_ids]}
        for _, c in scored]}
    req = {"model": MODEL, "state": state,
           "questions": {q: v for k in range(len(scored)) for q, v in _questions(k).items()}}
    resp = gw.json("POST", "typesafe", "/v1/systemone", req)
    a = resp["answers"]
    return [Ruling(i, c.side, c.part, float(a[f"true_{k}"]["noul"]), float(a[f"answered_{k}"]["noul"]))
            for k, (i, c) in enumerate(scored)], resp.get("model")


def points(r: Ruling) -> float:
    return round(r.p_true + (ANSWERED_BONUS if r.answered >= 0.5 else 0.0), 4)


def verdict(rulings: list[Ruling]) -> dict:
    total = {side: round(sum(points(r) for r in rulings if r.side == side), 4) for side in ("anchor", "uncle")}
    diff = total["anchor"] - total["uncle"]
    return {**total, "winner": "draw" if abs(diff) < DRAW_MARGIN else ("anchor" if diff > 0 else "uncle")}
