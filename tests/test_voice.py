import base64
import io
import wave

import pytest

from station.config import Voices
from station.gateway import Response
from station.steps.voice import synthesize, tts_request, voice_all
from station.steps.write import Chapter, Turn
from tests.fakes import FakeGateway, ok

VOICES = Voices(host="Kore", reporter="Charon", style="brisk, warm, conversational news read")
LEAD = Chapter(1, "lead", "Lead story", "hn:1", (Turn("host", "Our lead."), Turn("reporter", "Mozilla says..."),
                                                 Turn("host", "That's the lead.")))
STORY = Chapter(2, "story", "Story 2", "hn:2", (Turn("host", "Posters say..."),))


def wav_bytes(seconds=0.5, rate=24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


def gemini_reply(data: bytes) -> Response:  # check 2 response shape
    return ok({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/wav",
                                                                      "data": base64.b64encode(data).decode()}}]}}]})


def test_lead_request_is_two_speaker():
    req = tts_request(LEAD, VOICES)
    cfg = req["generationConfig"]
    assert cfg["responseModalities"] == ["AUDIO"]
    speakers = cfg["speechConfig"]["multiSpeakerVoiceConfig"]["speakerVoiceConfigs"]
    assert speakers == [{"speaker": "Host", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
                        {"speaker": "Reporter", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Charon"}}}]
    assert [p["speech_metadata"]["speaker"] for p in req["contents"][0]["parts"]] == ["Host", "Reporter", "Host"]


def test_story_request_is_single_speaker_kore():
    req = tts_request(STORY, VOICES)
    assert req["generationConfig"]["speechConfig"] == {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}
    assert req["contents"][0]["parts"][0]["text"] == "Posters say..."


def test_style_on_every_part():
    for ch in (LEAD, STORY):
        assert all(p["speech_metadata"]["style"] == VOICES.style for p in tts_request(ch, VOICES)["contents"][0]["parts"])


def test_writes_wav_without_rewrapping(tmp_path):
    data = wav_bytes(0.5)
    gw = FakeGateway({("POST", "gemini", "/v1beta/models/gemini-3.8-flash-tts:generateContent"): [gemini_reply(data)]})
    secs = synthesize(gw, STORY, VOICES, tmp_path / "ch_02.wav")
    assert (tmp_path / "ch_02.wav").read_bytes() == data and secs == pytest.approx(0.5)


def test_rejects_non_riff_audio(tmp_path):
    gw = FakeGateway({("POST", "gemini", "/v1beta/models/"): [gemini_reply(b"\x00\x01raw-pcm")]})
    with pytest.raises(ValueError, match="RIFF"):
        synthesize(gw, STORY, VOICES, tmp_path / "x.wav")


def test_voice_all_collects_failures(tmp_path):
    gw = FakeGateway({("POST", "gemini", "/v1beta/models/"): [gemini_reply(wav_bytes()), Response(400, {}, b"bad")]})
    result = voice_all(gw, [LEAD, STORY], VOICES, tmp_path, concurrency=1)
    assert list(result.paths) == [1] and result.paths[1].name == "ch_01.wav"
    assert result.failed == [2] and "Story 2" in result.notes[0]
