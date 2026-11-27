from station.steps.article import article_messages, article_problems, parse_article, word_cap, write_article
from station.store import Post
from tests.fakes import FakeGateway, ok


def post(id="p1", text="Posters say a thing happened. " * 6, source="Reddit r/milwaukee") -> Post:
    return Post(id, source, "mke", "story", "user7", "A title", "https://ex.com/a", text, "2026-11-27T15:00:00Z", {}, "public")


def story_dict() -> dict:
    return {"id": "p1", "beat_id": "mke", "headline": "A headline", "summary": "A summary.",
            "sources": [{"post_id": "p1", "url": "https://ex.com/a", "author": "user7", "source_name": "Reddit r/milwaukee"}]}


def chat(text: str):
    return ok({"message": {"content": text}})


def test_word_cap_scales_with_sources():  # Review Focus 1
    assert word_cap([post(text="word " * 30)]) == 120
    assert word_cap([post(text="word " * 150)]) == 300
    assert word_cap([post(text="word " * 900)]) == 350


def test_parse_article_splits_paragraphs_and_strips_markdown():
    assert parse_article("# Title\n\nFirst para.\n\n- second para\n\n**Third.**") == ["First para.", "second para", "Third."]


def test_problems_flags_unattributed_paragraph_length_and_quotes():
    good = ["Posters on Reddit say X.", "According to the post, Y.", "It is not yet clear whether Z."]
    assert article_problems(good, 120) == []
    assert any("attribution" in p for p in article_problems(["X happened.", "It is unclear."], 120))
    assert any("length" in p for p in article_problems(["Posters say " + "w " * 200], 120))
    assert any("quote" in p for p in article_problems(['Posters say "a" and "b".', "Unclear."], 120))


def test_messages_carry_only_the_story_sources():
    msgs = article_messages(story_dict(), [post(id="p1", text="alpha"), post(id="p2", text="beta")])
    user = msgs[-1]["content"]
    assert "alpha" in user and "beta" in user and "Never add facts" in user


def test_write_article_returns_paragraphs():
    gw = FakeGateway({("POST", "ollama", "/api/chat"): [chat("Posters on Reddit say X.\n\nIt is not yet clear why.")]})
    paragraphs, note = write_article(gw, "m", story_dict(), [post()])
    assert paragraphs == ["Posters on Reddit say X.", "It is not yet clear why."] and note is None


def test_write_article_retries_once_then_gives_up():
    gw = FakeGateway({("POST", "ollama", "/api/chat"): [chat("X happened.\n\nY happened.\n\nUnclear."),
                                                         chat("X happened.\n\nY happened.\n\nUnclear.")]})
    paragraphs, note = write_article(gw, "m", story_dict(), [post()])
    assert paragraphs is None and "article dropped" in note
    assert len(gw.calls) == 2


def test_write_article_writer_error_is_a_note():
    gw = FakeGateway({("POST", "ollama", "/api/chat"): [ok({"error": "busy"}, status=503)]})
    paragraphs, note = write_article(gw, "m", story_dict(), [post()])
    assert paragraphs is None and "503" in note


def test_title_only_sources_skip_the_writer():  # review I3: Google News posts have no text
    gw = FakeGateway({})
    paragraphs, note = write_article(gw, "m", story_dict(), [post(text="")])
    assert paragraphs is None and "too little source text" in note and gw.calls == []
