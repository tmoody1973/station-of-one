"""Step 9, publish: copy the hour's public files to the Tigris bucket through the connector gateway.

Proven 2026-11-26: PUT <gateway>/<bucket>/<key> keeps Content-Type and Cache-Control, and the public
host answers byte ranges with HTTP 206 (the player's seeking needs that). Media first, front page last,
so the front page never links to audio that isn't up yet; the first failed upload stops the step and
the previous front page stays online.
"""
from __future__ import annotations

import json
from pathlib import Path

from station.gateway import GatewayError

CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".mp3": "audio/mpeg", ".json": "application/json",
                 ".js": "text/javascript", ".mp4": "video/mp4", ".png": "image/png",
                 ".xml": "application/rss+xml; charset=utf-8"}
IMMUTABLE = {".mp3", ".png"}  # MP3 keys carry a content fingerprint; the cover never changes


def cache_control(key: str) -> str:
    if Path(key).suffix == ".mp4":
        return "max-age=300"  # the daily video may be re-rendered under the same name
    return "public, max-age=31536000, immutable" if Path(key).suffix in IMMUTABLE else "max-age=60"


def put_object(gw, bucket: str, key: str, data: bytes, content_type: str, cache: str) -> None:
    r = gw.request("PUT", "tigris", f"/{bucket}/{key}", data,
                   headers={"Content-Type": content_type, "Cache-Control": cache})
    if r.status >= 300:
        raise GatewayError("tigris", r.status, r.body.decode(errors="replace")[:300])


def _files(run: Path) -> list[tuple[str, Path]]:
    nid = run.name
    site = run / "site"
    pages = sorted((str(p.relative_to(site)), p) for p in site.rglob("*") if p.is_file())
    front = [kp for kp in pages if kp[0] == "index.html"]
    rest = [kp for kp in pages if kp[0] != "index.html"]
    key = json.loads((run / "newscast.json").read_text()).get("audio", {}).get("key") or f"audio/{nid}.mp3"
    return [(key, run / "newscast.mp3"), (f"data/{nid}.json", run / "newscast.json"), *rest, *front]


def publish(gw, run: Path, bucket: str) -> list[str]:
    keys = []
    for key, path in _files(run):
        put_object(gw, bucket, key, path.read_bytes(), CONTENT_TYPES[path.suffix], cache_control(key))
        keys.append(key)
    return keys
