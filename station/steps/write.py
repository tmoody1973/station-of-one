"""Step 5, write: scripts for each chapter, from the posts that passed selection only.

Open, Overheard and Sign-off are templates in code. The lead and the other stories are written
by Ollama Cloud (POST /api/chat, stream false, think false; plain text, since cloud models have
no structured output). Rules follow the spec's editorial rules and Google's TTS prompting guide
(docs/reference/gemini-tts-prompting.md): plain spoken words, no labels or stage directions.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime

from station.config import Prefs
from station.gateway import GatewayError
from station.steps.judge import Judged
from station.steps.rundown import Rundown
from station.store import Post

WORDS_PER_SECOND = 2.8  # Kore read ~164-168 wpm on Nov 26 (check 2b)
LENGTH_TOLERANCE = 0.35
HOUR_WORDS = ["twelve", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"]
ATTRIBUTION = ("according to", " say", " says", " said", "posted", "wrote", "report", "posters")
LABEL = re.compile(r"(?im)^\s*(host|reporter|anchor|narrator|speaker\s*\d*)\s*:")
STAGE = re.compile(r"\([^)]*\)|\[[^\]]*\]|\*")
TAG = re.compile(r"<[^>]+>")

SYSTEM = """You write copy for The Hourly Scroll, a five-minute public-radio-style newscast on WONE, 1.0 FM.
Rules, all mandatory:
- Write only from the posts given. Add no facts of your own.
- Attribute every claim to where it was posted: "according to <outlet>", "posters on Hacker News say".
- Never state a scraped claim as fact.
- Summarize in the show's own words. At most one short quoted line, with the author named.
- Calm, dry public-radio pacing. No jokes.
- Plain spoken words only: no stage directions, no parentheses or brackets, no markdown, no emoji.
- Pauses only with punctuation, "--", "..." or <short pause>. Capitals only for rare emphasis.
Reply in exactly this format:
HEADLINE: <a short headline, under 12 words>
SUMMARY: <two sentences in the show's own words, with attribution>
SCRIPT:
<the spoken script>"""


@dataclass(frozen=True)
class Turn:
    speaker: str  # "host" | "reporter"
    text: str


@dataclass(frozen=True)
class Chapter:
    index: int
    kind: str  # open | lead | story | overheard | signoff
    title: str
    story_id: str | None
    turns: tuple[Turn, ...]
    headline: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        return {**asdict(self), "turns": [asdict(t) for t in self.turns]}

    @classmethod
    def from_dict(cls, d: dict) -> "Chapter":
        return cls(d["index"], d["kind"], d["title"], d["story_id"], tuple(Turn(**t) for t in d["turns"]),
                   d.get("headline", ""), d.get("summary", ""))


def open_chapter(hour_local: datetime, id_line: str) -> Chapter:
    word = HOUR_WORDS[hour_local.hour % 12]
    text = f"{id_line} It's {word} o'clock. Here's the last hour on your internet."
    return Chapter(0, "open", "Open", None, (Turn("host", text),))


def signoff_text(read_today: int, not_aired_today: int, short: bool = False) -> str:
    text = f"I've read {read_today:,} posts today so you didn't. {not_aired_today:,} didn't make air."
    if short:
        text += " It was a quiet hour, so this newscast ran short."
    return text


def signoff_chapter(read_today: int, not_aired_today: int, id_line: str, short: bool) -> Chapter:
    return Chapter(0, "signoff", "Sign-off", None,
                   (Turn("host", f"{signoff_text(read_today, not_aired_today, short)} {id_line}"),))


def _first_sentence(text: str, max_words: int = 25) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    words = sentence.split()
    return " ".join(words[:max_words]) + ("..." if len(words) > max_words else "")


def overheard_chapter(comment: Judged) -> Chapter:
    p = comment.post
    text = (f"Overheard this hour, on {p.source}. A poster who goes by {p.author or 'an anonymous user'} "
            f'wrote: "{_first_sentence(p.text)}"')
    return Chapter(0, "overheard", "Overheard", p.id, (Turn("host", text),))


def parse_turns(text: str) -> tuple[Turn, ...]:
    turns = []
    for line in text.strip().splitlines():
        m = re.match(r"\s*(HOST|REPORTER)\s*:\s*(.+)", line, re.I)
        if m:
            turns.append(Turn(m.group(1).lower(), m.group(2).strip()))
        elif line.strip() and turns:
            turns[-1] = Turn(turns[-1].speaker, f"{turns[-1].text} {line.strip()}")
    return tuple(turns)


def parse_story_reply(text: str) -> tuple[str, str, str]:
    m = re.search(r"HEADLINE:\s*(.+?)\s*\n\s*SUMMARY:\s*(.+?)\s*\n\s*SCRIPT:\s*\n(.+)", text, re.S)
    if not m:
        raise ValueError("reply is not in HEADLINE/SUMMARY/SCRIPT format")
    return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()


def problems(chapter: Chapter, seconds: int) -> list[str]:
    found = []
    spoken = " ".join(t.text for t in chapter.turns)
    if not spoken.strip():
        return ["empty script"]
    if LABEL.search(spoken) or any(LABEL.match(t.text) for t in chapter.turns):
        found.append("speaker label in spoken text")
    if STAGE.search(TAG.sub("", spoken)):
        found.append("stage direction or markup")
    words = len(TAG.sub("", spoken).split())
    target = seconds * WORDS_PER_SECOND
    if not (1 - LENGTH_TOLERANCE) * target <= words <= (1 + LENGTH_TOLERANCE) * target:
        found.append(f"length {words} words, target {round(target)}")
    if not any(a in spoken.lower() for a in ATTRIBUTION):
        found.append("no attribution")
    return found


def messages_for(kind: str, story: Judged, sources: list[Post], seconds: int) -> list[dict]:
    target = round(seconds * WORDS_PER_SECOND)
    posts = [story.post, *[s for s in sources if s.id != story.post.id]]
    lines = [f"Write the {'lead story' if kind == 'lead' else 'story'} script, about {target} words ({seconds} seconds)."]
    if story.primary_source < 0.5:
        lines.append("The central claim has no linked primary source: hedge clearly.")
    if kind == "lead":
        lines.append("Two voices. Write each line starting with HOST: or REPORTER:. The host introduces in one or two "
                     "sentences, the reporter tells the story, the host closes in one sentence.")
    for p in posts:
        lines.append(f"\nPOST from {p.source} by {p.author or 'unknown'} at {p.posted_at}\nTITLE: {p.title}\n"
                     f"LINK: {p.url}\nTEXT: {p.text[:2000]}")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def _write_story(gw, model: str, kind: str, index: int, story: Judged, sources: list[Post], seconds: int):
    title = "Lead story" if kind == "lead" else f"Story {index + 1}"
    last = "no reply"
    for _ in range(2):  # one retry
        try:
            reply = gw.json("POST", "ollama", "/api/chat", {
                "model": model, "messages": messages_for(kind, story, sources, seconds),
                "stream": False, "think": False, "options": {"temperature": 0.4}})["message"]["content"]
            headline, summary, script = parse_story_reply(reply)
        except GatewayError as e:
            return None, f"{title} dropped: writer error {e.status}"
        except (ValueError, KeyError, TypeError) as e:
            last = str(e)
            continue
        turns = parse_turns(script) if kind == "lead" else (Turn("host", script),)
        chapter = Chapter(0, kind, title, story.post.id, turns, headline, summary)
        issues = problems(chapter, seconds)
        if not issues:
            return chapter, None
        last = "; ".join(issues)
    return None, f"{title} dropped after retry: {last}"


def write_all(gw, rundown: Rundown, prefs: Prefs, hour_local: datetime, read_today: int, not_aired_today: int,
              sources: dict[str, list[Post]], concurrency: int = 3) -> tuple[list[Chapter], list[str]]:
    ids = prefs.station.id_lines_newscast
    jobs = [("lead" if i == 0 else "story", i, s) for i, s in enumerate(rundown.stories)]

    def run(job):
        kind, i, story = job
        return _write_story(gw, prefs.writer.model, kind, i, story, sources.get(story.post.id, []),
                            rundown.seconds[story.post.id])

    with ThreadPoolExecutor(max_workers=concurrency) as pool:  # Ollama pay-as-you-go: 3 concurrent
        results = list(pool.map(run, jobs))
    notes = [note for _, note in results if note]
    chapters = [open_chapter(hour_local, ids[hour_local.hour % len(ids)])]
    chapters += [ch for ch, _ in results if ch]
    if rundown.overheard:
        chapters.append(overheard_chapter(rundown.overheard))
    chapters.append(signoff_chapter(read_today, not_aired_today, ids[(hour_local.hour + 1) % len(ids)], rundown.short))
    return [Chapter(i, c.kind, c.title, c.story_id, c.turns, c.headline, c.summary) for i, c in enumerate(chapters)], notes
