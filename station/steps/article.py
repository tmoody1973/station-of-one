"""Story-page articles (plan 2026-11-27-story-pages, Task 2).

One web article per aired story, written by Ollama only from that story's own posts. Length follows the
source material (a two-sentence post gets a short article), every paragraph but the last is attributed,
and the last says what is not known yet. Same retry-once pattern as the newscast writer.
"""
from __future__ import annotations

import re

from station.gateway import GatewayError
from station.steps.write import ATTRIBUTION
from station.store import Post

MIN_WORDS, MAX_WORDS = 120, 350
MIN_SOURCE_WORDS = 25  # less than this (e.g. a Google News headline) and the page keeps the summary
HEADING = re.compile(r"^\s*#")
BULLET = re.compile(r"^\s*[-*•]\s+")
QUOTES = ('"', "“", "”")

SYSTEM = """You write web articles for WONE 1.0 FM, a machine-edited public-radio-style station.
Rules, all mandatory:
- Write only from the posts given. Add no facts, numbers, names or quotes of your own.
- Public-radio web style: the first paragraph says what happened and where it was posted; short paragraphs of
  one to three plain sentences; explain any technical term in a short clause.
- Attribute in every paragraph except the last: "according to <outlet>", "posters on Hacker News say",
  "the post says". Never state a scraped claim as fact.
- The last paragraph says what is not known yet or what to watch for.
- At most one short quoted line, with its author named.
- No headline, no headings, no lists, no links, no markdown. Paragraphs separated by a blank line."""


def word_cap(posts: list[Post]) -> int:
    source_words = sum(len(p.text.split()) for p in posts)
    return max(MIN_WORDS, min(MAX_WORDS, 2 * source_words))


def article_messages(story: dict, posts: list[Post]) -> list[dict]:
    lines = [f"Write the article for this story: at most {word_cap(posts)} words. If the posts give less material, "
             "write less. Never add facts, quotes or comments that are not in the posts.",
             f"Our headline: {story.get('headline', '')}", f"Our summary: {story.get('summary', '')}"]
    for p in posts:
        lines.append(f"\nPOST from {p.source} by {p.author or 'unknown'} at {p.posted_at}\nTITLE: {p.title}\n"
                     f"LINK: {p.url}\nTEXT: {p.text[:3000]}")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def parse_article(text: str) -> list[str]:
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        if HEADING.match(block):
            continue
        para = " ".join(BULLET.sub("", line).strip() for line in block.splitlines()).replace("**", "").replace("__", "")
        if para.strip():
            out.append(para.strip())
    return out


def article_problems(paragraphs: list[str], cap: int) -> list[str]:
    found = []
    words = sum(len(p.split()) for p in paragraphs)
    if not paragraphs:
        found.append("empty article")
    if words > cap:
        found.append(f"length: {words} words, at most {cap}")
    if any(not any(a in p.lower() for a in ATTRIBUTION) for p in paragraphs[:-1]):
        found.append("attribution: every paragraph but the last must say where it was posted")
    if sum(p.count(q) for p in paragraphs for q in QUOTES) > 2:
        found.append("quote: at most one short quoted line")
    return found


def write_article(gw, model: str, story: dict, posts: list[Post]) -> tuple[list[str] | None, str | None]:
    if sum(len(p.text.split()) for p in posts) < MIN_SOURCE_WORDS:  # review I3: never pad a headline into an article
        return None, f"article skipped for {story.get('id')}: too little source text"
    messages, cap, last = article_messages(story, posts), word_cap(posts), "no reply"
    for _ in range(2):  # one retry, told what was wrong
        try:
            reply = gw.json("POST", "ollama", "/api/chat", {
                "model": model, "messages": messages, "stream": False, "think": False,
                "options": {"temperature": 0.4}})["message"]["content"]
        except GatewayError as e:
            return None, f"article dropped for {story.get('id')}: writer error {e.status}"
        except (KeyError, TypeError) as e:
            last, reply = f"unusable reply ({e})", ""
        paragraphs = parse_article(reply)
        issues = article_problems(paragraphs, cap) if reply else [last]
        if not issues:
            return paragraphs, None
        last = "; ".join(issues)
        messages = [*messages, {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"Fix these problems and rewrite: {last}. Never add facts."}]
    return None, f"article dropped for {story.get('id')} after retry: {last}"
