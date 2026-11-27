"""Bauhaus story illustrations (plan 2026-11-27-story-pages, Task 4; decision 006).

For a story with no publisher photo, Gemini draws an abstract composition in the site's primaries.
Never people, faces, text or logos, never photographic: the page labels it as a machine illustration.
Check 15 (Nov 27): gemini-3.1-flash-image returns one JPEG, 1376x768, ~800 KB, ~8 s, $0.034-0.067.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

MODEL = "gemini-3.1-flash-image"
PATH = f"/v1beta/models/{MODEL}:generateContent"
EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg"}


def illustration_prompt(headline: str, beat_name: str) -> str:
    return ("An abstract Bauhaus composition on a cream paper background, using only primary red, yellow, blue "
            "and black: bold circles, squares, triangles and bars, flat colour, strong geometry, loosely suggesting "
            f"the theme of this {beat_name} news headline: '{headline}'. "
            "Rules: no people, no faces, no hands, no text, no letters, no numbers, no logos; "
            "flat graphic art, not a photograph.")


def illustration_request(prompt: str) -> dict:
    return {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": "16:9", "imageSize": "1K"}}}


def illustrate(gw, headline: str, beat_name: str, out_dir: Path, stem: str) -> Path:
    resp = gw.json("POST", "gemini", PATH, illustration_request(illustration_prompt(headline, beat_name)), timeout=120)
    parts = ((resp.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    image = next((p["inlineData"] for p in parts if "inlineData" in p), None)
    if not image or image.get("mimeType") not in EXTENSIONS:
        raise ValueError(f"Gemini returned no usable image for {stem}")
    data = base64.b64decode(image["data"])
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stem}-{hashlib.sha1(data).hexdigest()[:8]}{EXTENSIONS[image['mimeType']]}"
    path.write_bytes(data)
    return path
