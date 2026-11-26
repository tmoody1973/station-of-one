"""Table step 5: the spoken script. The writer only rewrites each claim for its speaker (the Uncle as
his theories, the Anchor careful) and the Anchor's welcome. Rulings, totals, winner, season record and
the welcome and the WNCL station ID are written by code from rulings.json, so the writer cannot change the outcome.
A delivery that mentions numbers, winning, a verdict or a username is rejected; after a second
failure the show uses the already-checked claim text (plan Review Focus 3)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from station.gateway import GatewayError
from station.steps.write import Turn
from station.table.argue import ATTRIBUTION, PARTS, SIDES, Claim
from station.table.referee import Ruling

STATION_ID = "WNCL, broadcasting to a potential audience of one."
WELCOME = "Welcome to The Table, where two of us argue about one thread and Jev keeps score."  # code-written: the writer repeated the question
SPEAKER = {"anchor": "Anchor", "uncle": "Uncle"}
# Declaring a result is code's job. "win" as an ordinary verb ("details win people over") is fine.
FORBIDDEN = re.compile(r"\d\s*%|\bpercent\b|\bwinner\b|\b(?:I|we|you|he|anchor|uncle)\s+wins?\b|\bwins?\s+(?:this|the|today|tonight)\b"
                       r"|\bverdict\b|\bscor(?:e|ed|ing)\b|@\w", re.I)
MAX_WORDS = 75

SYSTEM = """You voice two characters on The Table, a daily radio debate. Rewrite each claim so its character can say it
out loud. The Anchor: calm, careful, cites what commenters said. The Uncle: confident, full of theories, often wrong;
he frames points as his theories ("Here's my theory..."); he is defined by his theories, not by any background or group.
Keep each claim's meaning and its attribution ("some posters say", "one commenter argues"). Never add facts.
Never name a username or handle. Never mention scores, percentages, winning or a verdict: a referee handles that.
At most 75 words per line.
Reply with JSON only: {"lines": [{"side": "anchor"|"uncle", "part": "opening"|"round1"|"round2"|"round3", "text": "..."}]}"""


@dataclass(frozen=True)
class TablePart:
    index: int
    kind: str  # question | opening | round1 | round2 | round3 | verdict | record
    title: str
    turns: tuple[Turn, ...]
    story_id: str | None = None  # lets the newscast's chapter_timings() time Table parts too


def _issues(data: dict) -> list[str]:
    found = []
    got = {(x.get("side"), x.get("part")): str(x.get("text") or "") for x in data.get("lines") or []}
    for side in SIDES:
        for part in PARTS:
            text = got.get((side, part), "")
            if not text:
                found.append(f"{side} {part}: missing")
            elif FORBIDDEN.search(text):
                found.append(f"{side} {part}: no numbers, percentages, winning, verdicts or handles")
            elif len(text.split()) > MAX_WORDS or not ATTRIBUTION.search(text):
                found.append(f"{side} {part}: keep the attribution and stay under {MAX_WORDS} words")
    return found


def write_script(gw, model: str, topic: dict, question: str, claims: list[Claim]) -> dict:
    """Returns {"lines": {"<side>:<part>": text}}; empty lines mean: use the claim text."""
    user = json.dumps({"thread": topic["title"], "question": question,
                       "claims": [{"side": c.side, "part": c.part, "text": c.text} for c in claims]})
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    for _ in range(2):
        try:
            content = gw.json("POST", "ollama", "/api/chat", {"model": model, "messages": messages, "stream": False,
                                                              "think": False, "options": {"temperature": 0.7}})["message"]["content"]
            data = json.loads(re.search(r"\{.*\}", content, re.S).group(0))
            issues = _issues(data)
        except GatewayError:
            raise
        except (AttributeError, ValueError, KeyError, TypeError):
            issues, content = ["reply with the JSON only"], ""
        if not issues:
            return {"lines": {f"{x['side']}:{x['part']}": x["text"].strip() for x in data["lines"]}}
        messages = [*messages, {"role": "assistant", "content": content},
                    {"role": "user", "content": "Fix and resend the full JSON: " + "; ".join(issues)}]
    return {"lines": {}}  # fall back to the checked claim text


def _ruling(r: Ruling) -> Turn:
    return Turn("Anchor", f"Jev's ruling. That claim: {round(r.p_true * 100)}% likely true.")


def parts(script: dict, claims: list[Claim], rulings: list[Ruling], verdict: dict, record: dict, topic: dict,
          question: str) -> list[TablePart]:
    say = lambda c: Turn(SPEAKER[c.side], script["lines"].get(f"{c.side}:{c.part}") or c.text)
    by_index = {r.claim_index: r for r in rulings}
    out = [TablePart(0, "question", "The question", (
        Turn("Anchor", f"{WELCOME} Today's question comes from a {topic['source']} thread about {topic['title']}. {question}"),
        Turn("Uncle", "Oh, I have theories.")))]
    for n, part in enumerate(PARTS, start=1):
        turns = []
        for i, c in enumerate(claims):
            if c.part == part:
                turns.append(say(c))
                if i in by_index:
                    turns.append(_ruling(by_index[i]))
        out.append(TablePart(n, part, "Opening claims" if part == "opening" else f"Round {part[-1]}", tuple(turns)))
    winner = {"anchor": "The Anchor takes it.", "uncle": "The Uncle takes it.", "draw": "It's a draw."}[verdict["winner"]]
    reaction = {"anchor": "The numbers are in on it too.", "uncle": "Told you.", "draw": "I'll take it."}[verdict["winner"]]
    out.append(TablePart(5, "verdict", "The verdict", (
        Turn("Anchor", f"Jev's totals. The Anchor: {verdict['anchor']:.1f} points. The Uncle: {verdict['uncle']:.1f}. {winner}"),
        Turn("Uncle", reaction))))
    out.append(TablePart(6, "record", "The record", (
        Turn("Anchor", f"The season so far: Anchor {record['anchor']}, Uncle {record['uncle']}, draws {record['draw']}. "
                       f"That's The Table. {STATION_ID}"),)))
    return out
