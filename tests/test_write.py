from datetime import datetime
from zoneinfo import ZoneInfo

from station.config import load_prefs
from station.gateway import Response
from station.steps.rundown import Rundown
from station.steps.write import (
    Chapter, Turn, open_chapter, overheard_chapter, parse_story_reply, parse_turns, problems,
    signoff_text, write_all,
)
from tests.fakes import FakeGateway, ok
from tests.test_rundown import j

CHI = ZoneInfo("America/Chicago")
ID1 = "WONE, 1.0 FM. One station, one listener."


def test_open_says_local_hour():  # Review Focus 5
    ch = open_chapter(datetime(2026, 11, 27, 21, 0, tzinfo=CHI), ID1)
    text = " ".join(t.text for t in ch.turns)
    assert "nine o'clock" in text and "here's the last hour on your internet" in text.lower() and ID1 in text
    assert ch.kind == "open" and ch.turns[0].speaker == "host"


def test_open_noon_and_midnight_words():
    assert "twelve o'clock" in open_chapter(datetime(2026, 11, 27, 12, 0, tzinfo=CHI), ID1).turns[0].text


def test_signoff_counts():
    assert "I've read 2,140 posts today so you didn't. 2,119 didn't make air." in signoff_text(2140, 2119)


def test_short_newscast_line():  # Review Focus 3
    assert "quiet hour" in signoff_text(40, 39, short=True).lower()


def test_parse_turns_strips_labels():
    assert parse_turns("HOST: Here's our lead.\nREPORTER: Mozilla says...") == (
        Turn("host", "Here's our lead."), Turn("reporter", "Mozilla says..."))


def test_parse_story_reply():
    h, s, script = parse_story_reply("HEADLINE: Firefox ESR 115 nears its end\nSUMMARY: One. Two.\nSCRIPT:\nPosters say it ends.")
    assert (h, s, script) == ("Firefox ESR 115 nears its end", "One. Two.", "Posters say it ends.")


def test_problems_flags_label_bracket_and_length():
    bad = Chapter(1, "story", "x", "s", (Turn("host", "Host: (calmly) hi"),))
    assert problems(bad, 40)
    words = " ".join(["word"] * 110) + " according to Hacker News."
    assert problems(Chapter(1, "story", "x", "s", (Turn("host", words),)), 40) == []


def test_problems_flags_missing_attribution():
    words = " ".join(["word"] * 110)
    assert any("attribut" in p for p in problems(Chapter(1, "story", "x", "s", (Turn("host", words),)), 40))


def test_overheard_template_quotes_one_short_line_with_author():
    c = j("c1", 0.5, kind="comment", part="overheard", overheard_p=0.8)
    c = type(c)(c.post.__class__(**{**c.post.__dict__, "text": "First sentence here. Second sentence is not quoted.",
                                    "author": "user7", "source": "Reddit r/milwaukee"}), c.answers, c.model)
    ch = overheard_chapter(c)
    text = ch.turns[0].text
    assert "user7" in text and "Reddit r/milwaukee" in text and '"First sentence here."' in text
    assert "Second sentence" not in text


REPLY = ("HEADLINE: A headline\nSUMMARY: Sentence one. Sentence two.\nSCRIPT:\n"
         + " ".join(["word"] * 100) + " according to posters on Hacker News.")
LEAD_REPLY = ("HEADLINE: Lead headline\nSUMMARY: One. Two.\nSCRIPT:\nHOST: Our lead, according to Hacker News.\n"
              "REPORTER: " + " ".join(["word"] * 200) + " posters say.\nHOST: That's the lead.")


def rundown_of(*items):
    secs = {x.post.id: (90 if i == 0 else 40) for i, x in enumerate(items)}
    return Rundown(tuple(items), secs, None, (), (), len(items) < 3, False)


def test_write_all_orders_chapters_and_keeps_headlines():
    gw = FakeGateway({("POST", "ollama", "/api/chat"): [ok({"message": {"content": LEAD_REPLY}}),
                                                       ok({"message": {"content": REPLY}})]})
    chapters, notes = write_all(gw, rundown_of(j("a", 0.6), j("b", 0.5)), load_prefs(),
                                datetime(2026, 11, 27, 9, 0, tzinfo=CHI), read_today=100, not_aired_today=98,
                                sources={}, concurrency=1)
    assert [c.kind for c in chapters] == ["open", "lead", "story", "signoff"]
    assert chapters[1].headline == "Lead headline" and [t.speaker for t in chapters[1].turns] == ["host", "reporter", "host"]
    body = gw.calls[0][3]
    assert body["stream"] is False and body["think"] is False and body["model"] == "gemma4:31b"


def test_write_all_retries_once_then_drops_chapter():
    bad = ok({"message": {"content": "HEADLINE: h\nSUMMARY: s\nSCRIPT:\nHOST: (laughs) nope"}})
    gw = FakeGateway({("POST", "ollama", "/api/chat"): [ok({"message": {"content": LEAD_REPLY}}), bad, bad]})
    chapters, notes = write_all(gw, rundown_of(j("a", 0.6), j("b", 0.5)), load_prefs(),
                                datetime(2026, 11, 27, 9, 0, tzinfo=CHI), read_today=10, not_aired_today=8,
                                sources={}, concurrency=1)
    assert [c.kind for c in chapters] == ["open", "lead", "signoff"] and any("dropped" in n for n in notes)


def test_ollama_error_drops_chapter_not_build():
    gw = FakeGateway({("POST", "ollama", "/api/chat"): [Response(503, {}, b"down")]})
    chapters, notes = write_all(gw, rundown_of(j("a", 0.6)), load_prefs(), datetime(2026, 11, 27, 9, 0, tzinfo=CHI),
                                read_today=10, not_aired_today=9, sources={}, concurrency=1)
    assert [c.kind for c in chapters] == ["open", "signoff"] and notes
