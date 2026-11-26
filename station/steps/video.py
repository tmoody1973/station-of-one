"""Daily vertical video (spec §10, simple version): the day's top aired story, its real audio,
word-timed captions, a count-up of posts read and an end card. Rendered by Remotion in video/."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from station.config import Prefs
from station.steps.captions import to_captions, words
from station.steps.publish import cache_control, put_object

INTRO_MS, END_MS = 2500, 3500
MIN_CLIP_MS, MAX_CLIP_MS = 24_000, 39_000  # total stays 30-45 s
VIDEO_DIR = Path(__file__).resolve().parents[2] / "video"


def pick(newscasts: list[dict]) -> tuple[dict, dict, int, int] | None:
    """Highest score_matter_week aired story whose chapter is long enough; returns (newscast, story, start, end)."""
    best = None
    for n in newscasts:
        chapters = {c.get("story_id"): c for c in n.get("chapters", []) if c.get("story_id")}
        for s in n.get("stories", []):
            c = chapters.get(s["id"])
            if c and c["end_ms"] - c["start_ms"] >= MIN_CLIP_MS and (best is None or s["score_matter_week"] > best[1]["score_matter_week"]):
                best = (n, s, c["start_ms"], min(c["end_ms"], c["start_ms"] + MAX_CLIP_MS))
    return best


def props(newscast: dict, story: dict, captions: list[dict], clip_ms: int, prefs: Prefs) -> dict:
    beat = next((b for b in prefs.beats if b.id == story.get("beat_id")), None)
    host = prefs.hosting.public_base.removeprefix("https://").removeprefix("http://")
    return {"headline": story["headline"], "beat": beat.name if beat else "", "beatColor": beat.color if beat else "#C8102E",
            "postsRead": newscast["counts"]["posts_read_today"], "captions": captions, "clipMs": clip_ms,
            "introMs": INTRO_MS, "endMs": END_MS, "durationMs": INTRO_MS + clip_ms + END_MS,
            "show": prefs.station.show_name, "station": f"{prefs.station.call_sign} {prefs.station.frequency}",
            "url": f"{host}/index.html"}


def story_clip(mp3: Path, start_ms: int, end_ms: int, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start_ms}ms", "-to", f"{end_ms}ms", "-i", str(mp3),
                    "-c:a", "libmp3lame", "-b:a", "128k", str(out)], check=True)
    return out


def render(day: str, video_dir: Path = VIDEO_DIR) -> Path:
    out = video_dir / "out" / f"{day}.mp4"
    subprocess.run(["npx", "remotion", "render", "Reel", str(out), "--props=public/props.json"],
                   cwd=video_dir, check=True, capture_output=True, text=True, timeout=600)
    return out


def make_video(day: str, gw, prefs: Prefs, runs_root: Path, video_dir: Path = VIDEO_DIR) -> dict:
    """Pick, cut, caption, render and upload the day's video. Returns the props used (for the run log)."""
    newscasts = [json.loads(f.read_text()) for f in sorted(runs_root.glob(f"{day}T??/newscast.json"))]
    chosen = pick(newscasts)
    if chosen is None:
        raise ValueError(f"no aired story on {day} has a chapter of at least {MIN_CLIP_MS // 1000} s")
    n, story, start, end = chosen
    clip = story_clip(runs_root / n["id"] / "newscast.mp3", start, end, video_dir / "public" / "clip.mp3")
    p = props(n, story, to_captions(words(gw, clip)), end - start, prefs)
    (video_dir / "public" / "props.json").write_text(json.dumps(p))
    out = render(day, video_dir)
    key = f"video/{day}.mp4"
    put_object(gw, prefs.hosting.bucket, key, out.read_bytes(), "video/mp4", cache_control(key))
    return {**p, "newscast": n["id"], "story_id": story["id"], "key": key, "bytes": out.stat().st_size}
