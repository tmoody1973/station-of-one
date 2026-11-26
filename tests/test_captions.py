import json

from station.config import load_prefs
from station.gateway import Response
from station.steps.captions import to_captions, words
from station.steps.publish import cache_control
from station.steps.video import END_MS, INTRO_MS, pick, props
from tests.test_page import newscast

PREFS = load_prefs()
DEEPGRAM = {"metadata": {"duration": 36.5}, "results": {"channels": [{"alternatives": [{"transcript": "A museum.", "words": [
    {"word": "a", "start": 0.0, "end": 0.16, "confidence": 0.95, "punctuated_word": "A"},
    {"word": "museum", "start": 0.16, "end": 0.56, "confidence": 0.99, "punctuated_word": "museum."}]}]}]}}


class DG:
    def __init__(self):
        self.calls = []

    def request(self, method, provider, path, body=None, headers=None, timeout=120):
        self.calls.append((method, provider, path, body, headers))
        return Response(200, {}, json.dumps(DEEPGRAM).encode())


def test_words_parsed_in_seconds(tmp_path):
    clip = tmp_path / "c.mp3"
    clip.write_bytes(b"ID3")
    gw = DG()
    w = words(gw, clip)
    assert w == [{"word": "A", "start": 0.0, "end": 0.16}, {"word": "museum.", "start": 0.16, "end": 0.56}]
    method, provider, path, body, headers = gw.calls[0]
    assert (method, provider, path, body) == ("POST", "deepgram", "/v1/listen?model=nova-3&smart_format=true", b"ID3")
    assert headers["Content-Type"] == "audio/mpeg"
    assert to_captions(w) == [
        {"text": "A", "startMs": 0, "endMs": 160, "timestampMs": 80, "confidence": None},
        {"text": " museum.", "startMs": 160, "endMs": 560, "timestampMs": 360, "confidence": None}]


def day(*specs):
    """specs: (hour, [(story_id, score, chapter_seconds)])"""
    out = []
    for hour, stories in specs:
        n = newscast(hour)
        n["stories"] = [{"id": sid, "headline": f"H {sid}", "beat_id": "arts-culture", "score_matter_week": sc}
                        for sid, sc, _ in stories]
        t, n["chapters"] = 0, []
        for sid, _, secs in stories:
            n["chapters"].append({"kind": "story", "story_id": sid, "start_ms": t, "end_ms": t + secs * 1000})
            t += secs * 1000
        out.append(n)
    return out


def test_clip_length_between_30_and_45():
    n, story, start, end = pick(day(("2026-11-26T14", [("short", 0.9, 20), ("long", 0.7, 60)])))
    assert story["id"] == "long" and 30_000 <= (end - start) + INTRO_MS + END_MS <= 45_000
    n, story, start, end = pick(day(("2026-11-26T14", [("just", 0.7, 24)])))
    assert (end - start) + INTRO_MS + END_MS == 30_000


def test_picks_highest_score_across_the_day():
    _, story, _, _ = pick(day(("2026-11-26T12", [("a", 0.55, 40)]), ("2026-11-26T15", [("b", 0.81, 35)])))
    assert story["id"] == "b"
    assert pick(day(("2026-11-26T12", [("tiny", 0.9, 10)]))) is None


def test_props_contain_captions_and_end_card_url():
    n, story, start, end = pick(day(("2026-11-26T14", [("long", 0.7, 60)])))
    p = props(n, story, to_captions([{"word": "Hi", "start": 0.0, "end": 0.3}]), end - start, PREFS)
    assert p["captions"][0]["text"] == "Hi" and p["headline"] == "H long"
    assert p["url"].endswith("/index.html") and not p["url"].startswith("http")
    assert p["durationMs"] == p["introMs"] + p["clipMs"] + p["endMs"] and p["beatColor"].startswith("#")
    assert p["postsRead"] == n["counts"]["posts_read_today"]


def test_video_cache_is_short():  # a re-render must not be hidden by a year-long cache
    assert cache_control("video/2026-11-26.mp4") == "max-age=300"
