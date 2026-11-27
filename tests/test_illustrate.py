import base64

import pytest

from station.steps.illustrate import MODEL, illustrate, illustration_prompt, illustration_request
from station.steps.publish import CONTENT_TYPES, cache_control
from tests.fakes import FakeGateway, ok

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
PATH = f"/v1beta/models/{MODEL}:generateContent"


def _reply(parts):
    return FakeGateway({("POST", "gemini", PATH): [ok({"candidates": [{"content": {"parts": parts}}]})]})


def test_prompt_forbids_people_text_and_photos():
    p = illustration_prompt("Pete Warden on local AI", "AI and developer tools").lower()
    for rule in ("no people", "no faces", "no text", "no letters", "no logos", "not a photograph", "bauhaus"):
        assert rule in p
    assert "pete warden on local ai" in p


def test_request_asks_for_one_16x9_image():
    r = illustration_request("x")
    assert r["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert r["generationConfig"]["imageConfig"] == {"aspectRatio": "16:9", "imageSize": "1K"}


def test_illustrate_saves_fingerprinted_file(tmp_path):
    gw = _reply([{"text": "here"}, {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(PNG).decode()}}])
    path = illustrate(gw, "H", "Beat", tmp_path, "2026-11-27T10-ab12cd34")
    assert path.name.startswith("2026-11-27T10-ab12cd34-") and path.suffix == ".png"
    assert path.read_bytes() == PNG


def test_illustrate_jpeg_gets_jpg_extension(tmp_path):
    gw = _reply([{"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(b"\xff\xd8\xff" + b"0" * 9).decode()}}])
    assert illustrate(gw, "H", "Beat", tmp_path, "s").suffix == ".jpg"


def test_illustrate_raises_without_image(tmp_path):
    with pytest.raises(ValueError):
        illustrate(_reply([{"text": "I cannot draw that"}]), "H", "Beat", tmp_path, "s")


def test_jpg_is_served_as_immutable_image():
    assert CONTENT_TYPES[".jpg"] == "image/jpeg"
    assert "immutable" in cache_control("art/x-1234abcd.jpg")
