"""Each build's MP3 gets a content-fingerprinted name, so a rebuilt hour never serves a cached old copy
(found Nov 26: the CDN served the 1:14 pm 2 pm audio after the 1:32 pm rebuild)."""
import json

from station.config import load_prefs
from station.steps.assemble import audio_key
from station.steps.page import audio_path, render_feed, render_front
from station.steps.publish import publish
from tests.test_page import newscast
from tests.test_publish import RecordingGateway, make_run

PREFS = load_prefs()


def test_new_audio_gets_new_key(tmp_path):
    a, b = tmp_path / "a.mp3", tmp_path / "b.mp3"
    a.write_bytes(b"first build")
    b.write_bytes(b"rebuild")
    ka, kb = audio_key("2026-11-26T14", a), audio_key("2026-11-26T14", b)
    assert ka.startswith("audio/2026-11-26T14-") and ka.endswith(".mp3") and ka != kb
    assert ka == audio_key("2026-11-26T14", a)  # same bytes, same key


def test_pages_and_feed_use_the_key():
    n = newscast()
    n["audio"]["key"] = "audio/2026-11-26T17-abc12345.mp3"
    assert audio_path(n) == "/audio/2026-11-26T17-abc12345.mp3"
    assert 'src="/audio/2026-11-26T17-abc12345.mp3"' in render_front(n, [n], PREFS)
    assert "/audio/2026-11-26T17-abc12345.mp3" in render_feed(n, PREFS, 1)


def test_hours_without_a_key_keep_the_plain_name():
    assert audio_path(newscast()) == "/audio/2026-11-26T17.mp3"


def test_publish_uploads_under_the_key(tmp_path):
    run = make_run(tmp_path)
    (run / "newscast.json").write_text(json.dumps({"id": run.name, "audio": {"key": "audio/x-abc.mp3"}}))
    assert "audio/x-abc.mp3" in publish(RecordingGateway(), run, "b")
