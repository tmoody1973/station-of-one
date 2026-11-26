import json

import pytest

from station.config import load_prefs
from station.gateway import GatewayError, Response
from station.steps.publish import CONTENT_TYPES, cache_control, publish, put_object


class RecordingGateway:
    """Records every PUT with its headers; answers with `status`."""

    def __init__(self, status=200):
        self.status, self.puts = status, []

    def request(self, method, provider, path, body=None, headers=None, timeout=120):
        self.puts.append((method, provider, path, body, headers))
        return Response(self.status, {}, b"" if self.status < 300 else b"<Error>AccessDenied</Error>")


def make_run(tmp_path):
    run = tmp_path / "2026-11-26T17"
    for rel in ["site/index.html", "site/h/2026-11-26/1700/index.html", "site/player.js",
                "site/control-room/index.html", "site/settings/index.html"]:
        (run / rel).parent.mkdir(parents=True, exist_ok=True)
        (run / rel).write_text("<p>x</p>")
    (run / "newscast.mp3").write_bytes(b"ID3fake")
    (run / "newscast.json").write_text(json.dumps({"id": "2026-11-26T17"}))
    return run


def test_content_types():
    assert CONTENT_TYPES[".html"] == "text/html; charset=utf-8" and CONTENT_TYPES[".mp3"] == "audio/mpeg"
    gw = RecordingGateway()
    put_object(gw, "b", "audio/x.mp3", b"ID3", CONTENT_TYPES[".mp3"], cache_control("audio/x.mp3"))
    method, provider, path, body, headers = gw.puts[0]
    assert (method, provider, path, body) == ("PUT", "tigris", "/b/audio/x.mp3", b"ID3")
    assert headers == {"Content-Type": "audio/mpeg", "Cache-Control": "public, max-age=31536000, immutable"}


def test_hour_pages_and_index_keys(tmp_path):
    gw = RecordingGateway()
    keys = publish(gw, make_run(tmp_path), "b")
    assert set(keys) == {"index.html", "h/2026-11-26/1700/index.html", "player.js", "control-room/index.html",
                         "settings/index.html", "audio/2026-11-26T17.mp3", "data/2026-11-26T17.json"}
    assert keys[-1] == "index.html"  # front page last, so it never links to audio that isn't up yet
    assert keys.index("audio/2026-11-26T17.mp3") < keys.index("h/2026-11-26/1700/index.html")


def test_index_short_cache():
    assert cache_control("index.html") == "max-age=60"
    assert cache_control("h/2026-11-26/1700/index.html") == "max-age=60"  # lists today's newscasts, changes hourly
    assert cache_control("data/2026-11-26T17.json") == "max-age=60"
    assert cache_control("audio/2026-11-26T17.mp3") == "public, max-age=31536000, immutable"


def test_failed_put_raises_and_stops(tmp_path):
    gw = RecordingGateway(status=403)
    with pytest.raises(GatewayError):
        publish(gw, make_run(tmp_path), "b")
    assert len(gw.puts) == 1  # stops at the first failure; the old front page stays up


def test_prefs_name_the_bucket():
    h = load_prefs().hosting
    assert h.bucket == "patient-mountain-3400" and h.public_base == "https://patient-mountain-3400.fly.storage.tigris.dev"
