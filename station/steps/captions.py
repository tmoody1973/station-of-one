"""Word timings for the daily video's captions, from Deepgram through the connector gateway.

Proven Nov 26: POST /v1/listen?model=nova-3&smart_format=true with the MP3 bytes → HTTP 200 in 0.3 s;
results.channels[0].alternatives[0].words[] = {word, start, end, confidence, punctuated_word} (seconds).
"""
from __future__ import annotations

import json
from pathlib import Path

from station.gateway import GatewayError


def words(gw, clip: Path) -> list[dict]:
    r = gw.request("POST", "deepgram", "/v1/listen?model=nova-3&smart_format=true", clip.read_bytes(),
                   headers={"Content-Type": "audio/mpeg"}, timeout=120)
    if r.status >= 300:
        raise GatewayError("deepgram", r.status, r.body.decode(errors="replace")[:300])
    alt = json.loads(r.body)["results"]["channels"][0]["alternatives"][0]
    return [{"word": w.get("punctuated_word") or w["word"], "start": w["start"], "end": w["end"]} for w in alt["words"]]


def to_captions(ws: list[dict]) -> list[dict]:
    """Remotion's Caption shape; every word after the first carries its leading space."""
    return [{"text": ("" if i == 0 else " ") + w["word"], "startMs": round(w["start"] * 1000),
             "endMs": round(w["end"] * 1000), "timestampMs": round((w["start"] + w["end"]) * 500), "confidence": None}
            for i, w in enumerate(ws)]
