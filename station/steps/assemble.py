"""Step 7, assemble: join chapters with the sting, normalize loudness, embed chapters.

ffmpeg flags proven in check 4 (ffmpeg 8.0.1 on the Sprite): concat demuxer, hand-written
FFMETADATA (chapter_per_file is not in 8.0.1), loudnorm I=-16 TP=-1.5 LRA=11, mono 64k MP3
with ID3v2.3 so CHAP/CTOC frames are written. Also builds newscast.json for the pages.
"""
from __future__ import annotations

import subprocess
import wave
from datetime import datetime
from pathlib import Path

from station.config import Prefs
from station.steps.rundown import Rundown
from station.steps.write import Chapter
from station.store import Post

LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


def escape_meta(value: str) -> str:
    out = value.replace("\\", "\\\\")
    for ch in ("=", ";", "#", "\n"):
        out = out.replace(ch, "\\" + ch)
    return out


def chapter_metadata(chapters: list[tuple[str, int, int]], title: str) -> str:
    lines = [";FFMETADATA1", f"title={escape_meta(title)}"]
    for name, start, end in chapters:
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}", f"title={escape_meta(name)}"]
    return "\n".join(lines) + "\n"


def durations_ms(wavs: list[Path]) -> list[int]:
    out = []
    for p in wavs:
        with wave.open(str(p)) as w:
            out.append(round(w.getnframes() / w.getframerate() * 1000))
    return out


def chapter_timings(chapters: list[Chapter], durations: dict[int, int], sting_ms: int) -> list[dict]:
    """Start/end per voiced chapter; the sting folds into the first and last chapter."""
    voiced = [c for c in chapters if c.index in durations]
    timings, t = [], 0
    for pos, c in enumerate(voiced):
        length = durations[c.index] + (sting_ms if pos == 0 else 0) + (sting_ms if pos == len(voiced) - 1 else 0)
        timings.append({"index": c.index, "title": c.title, "kind": c.kind, "story_id": c.story_id,
                        "start_ms": t, "end_ms": t + length})
        t += length
    return timings


def prepare_sting(sting: Path, work: Path) -> Path:
    """Convert the sting to 24 kHz mono 16-bit if it isn't already (concat needs matching inputs)."""
    with wave.open(str(sting)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2):
            return sting
    out = work / "sting_24k.wav"
    _ffmpeg(["-i", str(sting), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(out)])
    return out


def _ffmpeg(args: list[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-800:]}")


def assemble_audio(run: Path, wavs: list[Path], timings: list[dict], title: str) -> Path:
    listing = run / "concat.txt"
    listing.write_text("ffconcat version 1.0\n" + "".join(f"file '{p.resolve()}'\n" for p in wavs))
    meta = run / "chapters.ffmeta"
    meta.write_text(chapter_metadata([(c["title"], c["start_ms"], c["end_ms"]) for c in timings], title))
    out = run / "newscast.mp3"
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(meta),
             "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1", "-af", LOUDNORM,
             "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", "-id3v2_version", "3", str(out)])
    return out


def _source(p: Post) -> dict:
    return {"post_id": p.id, "url": p.url, "author": p.author, "source_name": p.source, "posted_at": p.posted_at}


def newscast_record(run_id: str, hour_local: datetime, prefs: Prefs, chapters: list[Chapter], timings: list[dict],
                    rundown: Rundown, sources: dict[str, list[Post]], counts: dict, duration_ms: int) -> dict:
    judged = {s.post.id: s for s in rundown.stories}
    starts = {t["story_id"]: t["start_ms"] for t in timings if t["story_id"]}
    voiced = {t["index"] for t in timings}
    stories = []
    for c in chapters:
        if c.kind not in ("lead", "story") or c.index not in voiced or c.story_id not in judged:
            continue
        s = judged[c.story_id]
        stories.append({"id": s.post.id, "beat_id": s.post.beat, "part": c.kind, "headline": c.headline,
                        "summary": c.summary, "score_matter_week": s.matter_week,
                        "seconds": rundown.seconds.get(s.post.id), "chapter_start_ms": starts.get(s.post.id, 0),
                        "sources": [_source(p) for p in sources.get(s.post.id, [s.post])]})
    overheard = None
    if rundown.overheard and any(c.kind == "overheard" and c.index in voiced for c in chapters):
        p = rundown.overheard.post
        overheard = {"post_id": p.id, "source": p.source, "author": p.author, "url": p.url, "text": p.text[:300]}
    return {
        "id": run_id, "hour_local": hour_local.isoformat(), "show": prefs.station.show_name,
        "station": prefs.station.call_sign, "frequency": prefs.station.frequency, "short": rundown.short,
        "counts": counts, "stories": stories,
        "almost": [{"post_id": a.post.id, "title": a.post.title, "url": a.post.url,
                    "score_matter_week": a.matter_week} for a in rundown.almost],
        "overheard": overheard, "chapters": timings,
        "audio": {"file": "newscast.mp3", "duration_ms": duration_ms}, "voices_synthetic": True,
    }
