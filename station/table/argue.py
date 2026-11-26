"""Table step 3: the writer drafts the debate's claims from the thread, with no verdict.

Code checks every draft: the right 8 claims, sources that exist in this thread, no usernames or
handles (commenters are private people), every claim attributed, 60 words at most. One retry with
the problems listed; a second failure stops the episode (spec §11; plan Review Focus 2).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from station.gateway import GatewayError

PARTS = ("opening", "round1", "round2", "round3")
SIDES = ("anchor", "uncle")
MAX_WORDS = 60
HANDLE = re.compile(r"@\w|\bu/\w+", re.I)  # Bluesky/HN-style @name and Reddit u/name
# Declaring a result is code's job. "win" as an ordinary verb ("details win people over") is fine.
FORBIDDEN = re.compile(r"\d\s*%|\bpercent\b|\bwinner\b|\b(?:I|we|you|he|anchor|uncle)\s+wins?\b"
                       r"|\bwins?\s+(?:this|the|today's|tonight's)\s+(?:one|round|debate|argument|day)\b"
                       r"|\bverdict\b|\bscor(?:e|ed|ing)\b|@\w", re.I)
ATTRIBUTION = re.compile(r"\b(posters?|commenters?|people in the thread|someone in the thread|one person|"
                         r"some (?:people|folks|users)|others? (?:say|argue|claim))\b", re.I)

SYSTEM = """You write claims for The Table, a daily radio debate. Two characters argue about one online thread.
The Anchor: calm, careful, cites sources. The Uncle: confident, full of theories, often wrong; a character defined
by his theories, not by any background or group.
Rules:
- Argue only positions found in the comments, and attribute them: "some posters say", "one commenter argues".
- Never name or quote a username or handle. Never voice or impersonate a real person.
- Each claim is one or two spoken sentences, at most 60 words.
- Each claim lists the comment ids it draws on in "sources". The Anchor always cites at least one.
- Each character holds ONE position for the whole debate: the Anchor answers the question one way, the Uncle
  the other way. Every Anchor claim supports anchor_position; every Uncle claim supports uncle_position.
- Do not say who wins or how strong a claim is. A referee scores the claims later.
Reply with JSON only:
{"question": "<the dispute as one short yes-or-no question>",
 "anchor_position": "<Yes or No, and why, in one sentence>",
 "uncle_position": "<the opposite answer, in one sentence>",
 "claims": [{"side": "anchor"|"uncle", "part": "opening"|"round1"|"round2"|"round3", "text": "...", "sources": ["<comment id>"]}]}
Exactly one claim per side per part: 8 claims."""


@dataclass(frozen=True)
class Claim:
    side: str
    part: str
    text: str
    source_ids: tuple[str, ...]


def _names(comments: list[dict]) -> set[str]:
    return {c["author"] for c in comments if c.get("author") and len(c["author"]) >= 3}


def problems(data: dict, comments: list[dict]) -> list[str]:
    found = []
    claims = data.get("claims") or []
    if not str(data.get("question") or "").strip():
        found.append("missing question")
    pa, pu = (str(data.get(k) or "").strip() for k in ("anchor_position", "uncle_position"))
    if not pa or not pu or pa.lower() == pu.lower():
        found.append("state anchor_position and uncle_position: opposite answers to the question")
    if sorted((c.get("side"), c.get("part")) for c in claims) != sorted((s, p) for s in SIDES for p in PARTS):
        found.append("need exactly one claim per side for opening, round1, round2, round3")
    ids, names = {c["id"] for c in comments}, _names(comments)
    for label in ("question", "anchor_position", "uncle_position"):  # spoken and shown too (review finding 3)
        text = str(data.get(label) or "")
        if HANDLE.search(text):
            found.append(f"{label}: remove the handle")
        found += [f"{label}: remove the username {n}" for n in names if re.search(rf"\b{re.escape(n)}\b", text, re.I)]
    for c in claims:
        where, text = f"{c.get('side')} {c.get('part')}", str(c.get("text") or "")
        for sid in c.get("sources") or []:
            if sid not in ids:
                found.append(f"{where}: source {sid} is not a comment in this thread")
        if c.get("side") == "anchor" and not c.get("sources"):
            found.append(f"{where}: the Anchor must cite at least one comment id")
        if HANDLE.search(text):
            found.append(f"{where}: remove the handle")
        if FORBIDDEN.search(text):  # the script fallback speaks claim text as written (review finding 4)
            found.append(f"{where}: no percent figures, scores, winners or verdicts; the referee handles those")
        for n in names:
            if re.search(rf"\b{re.escape(n)}\b", text, re.I):
                found.append(f"{where}: remove the username {n}")
        if len(text.split()) > MAX_WORDS:
            found.append(f"{where}: keep it to {MAX_WORDS} words")
        if not ATTRIBUTION.search(text):
            found.append(f"{where}: attribute it (\"some posters say\", \"one commenter argues\")")
    return found


def _messages(story: dict, comments: list[dict]) -> list[dict]:
    thread = "\n".join(f"[{c['id']}] {c['text'][:600]}" for c in comments)  # ids only; no usernames reach the writer
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Thread: {story['title']} ({story['source']})\n\nComments:\n{thread}"}]


def draft(gw, model: str, story: dict, comments: list[dict]) -> tuple[str, list[Claim], tuple[str, str]]:
    """Returns (question, 8 claims in broadcast order, (anchor_position, uncle_position))."""
    messages, last = _messages(story, comments), "no reply"
    for _ in range(2):
        try:
            content = gw.json("POST", "ollama", "/api/chat", {"model": model, "messages": messages, "stream": False,
                                                              "think": False, "options": {"temperature": 0.6}})["message"]["content"]
            data = json.loads(re.search(r"\{.*\}", content, re.S).group(0))
            issues = problems(data, comments)
        except GatewayError:
            raise
        except (AttributeError, ValueError, KeyError, TypeError) as e:
            issues, content = [f"unusable reply ({type(e).__name__}); reply with the JSON only"], ""
        if not issues:
            order = {(s, p): i for i, (p, s) in enumerate((p, s) for p in PARTS for s in SIDES)}
            claims = sorted((Claim(c["side"], c["part"], c["text"].strip(), tuple(c.get("sources") or ()))
                             for c in data["claims"]), key=lambda c: order[(c.side, c.part)])
            return data["question"].strip(), claims, (data["anchor_position"].strip(), data["uncle_position"].strip())
        last = "; ".join(issues)
        messages = [*messages, {"role": "assistant", "content": content},
                    {"role": "user", "content": f"Fix these problems and reply with the full JSON again: {last}"}]
    raise ValueError(f"The Table's claims failed checks twice: {last}")
