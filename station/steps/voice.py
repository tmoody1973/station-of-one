"""Step 6, voice: Gemini TTS, one call per chapter; the lead is one two-speaker call.

Shapes proven in check 2: generateContent (the Interactions API is refused by the connector),
per-turn speech_metadata, prebuilt voices, reply is a complete 24 kHz mono 16-bit WAV.
"""
from __future__ import annotations

import base64
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from station.config import Voices
from station.gateway import GatewayError
from station.steps.write import Chapter

MODEL = "gemini-3.8-flash-tts"
PATH = f"/v1beta/models/{MODEL}:generateContent"
SPEAKER = {"host": "Host", "reporter": "Reporter"}


def _voice(name: str) -> dict:
    return {"prebuiltVoiceConfig": {"voiceName": name}}


def tts_request(chapter: Chapter, voices: Voices) -> dict:
    two = {t.speaker for t in chapter.turns} == {"host", "reporter"}
    parts = []
    for t in chapter.turns:
        meta = {"style": voices.style}
        if two:
            meta = {"speaker": SPEAKER[t.speaker], **meta}
        parts.append({"text": t.text, "speech_metadata": meta})
    if two:
        speech = {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
            {"speaker": "Host", "voiceConfig": _voice(voices.host)},
            {"speaker": "Reporter", "voiceConfig": _voice(voices.reporter)}]}}
    else:
        speaker = chapter.turns[0].speaker if chapter.turns else "host"
        speech = {"voiceConfig": _voice(voices.reporter if speaker == "reporter" else voices.host)}
    return {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech}}


def synthesize(gw, chapter: Chapter, voices: Voices, out: Path) -> float:
    resp = gw.json("POST", "gemini", PATH, tts_request(chapter, voices), timeout=180)
    data = base64.b64decode(resp["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    if data[:4] != b"RIFF":
        raise ValueError(f"expected a RIFF WAV from Gemini, got {data[:4]!r}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    with wave.open(str(out)) as w:
        return w.getnframes() / w.getframerate()


@dataclass
class VoiceResult:
    paths: dict[int, Path] = field(default_factory=dict)
    seconds: dict[int, float] = field(default_factory=dict)
    failed: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def voice_all(gw, chapters: list[Chapter], voices: Voices, run: Path, concurrency: int = 4) -> VoiceResult:
    def one(ch: Chapter):
        out = run / "audio" / f"ch_{ch.index:02d}.wav"
        try:
            return ch, out, synthesize(gw, ch, voices, out), None
        except (GatewayError, ValueError, KeyError) as e:
            return ch, None, 0.0, f"{ch.title} not voiced: {e}"

    result = VoiceResult()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for ch, out, secs, err in pool.map(one, chapters):
            if err:
                result.failed.append(ch.index)
                result.notes.append(err)
            else:
                result.paths[ch.index] = out
                result.seconds[ch.index] = secs
    return result
