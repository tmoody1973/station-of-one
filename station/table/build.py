"""Table steps 6-9: voice, assemble, page, publish + archive. Reuses the newscast's TTS call, sting,
ffmpeg join, chapters, page environment, bucket upload and Box archive. Any part failing to voice
stops the episode: nothing half-made is published (plan Review Focus 5)."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from station.config import Prefs, TableVoices
from station.steps import assemble as asm
from station.steps.page import _duration, env
from station.steps.publish import CONTENT_TYPES, cache_control, put_object
from station.steps.voice import _voice, synthesize_request
from station.table.script import STATION_ID, TablePart

ARCHIVE_FILES = ["topic.json", "claims.json", "rulings.json", "script.json", "table.json", "newscast.mp3"]


def tts_request(part: TablePart, tv: TableVoices) -> dict:
    style = {"Anchor": tv.anchor_style, "Uncle": tv.uncle_style}
    contents = [{"text": t.text, "speech_metadata": {"speaker": t.speaker, "style": style[t.speaker]}} for t in part.turns]
    return {"contents": [{"role": "user", "parts": contents}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
                {"speaker": "Anchor", "voiceConfig": _voice(tv.anchor)}, {"speaker": "Uncle", "voiceConfig": _voice(tv.uncle)}]}}}}


def voice_parts(gw, parts: list[TablePart], tv: TableVoices, run: Path) -> dict[int, Path]:
    def one(p: TablePart) -> tuple[int, Path]:
        out = run / "audio" / f"part_{p.index:02d}.wav"
        synthesize_request(gw, tts_request(p, tv), out)  # raises on failure: no half episode
        return p.index, out

    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(pool.map(one, parts))


def assemble_table(run: Path, parts: list[TablePart], wavs: dict[int, Path], sting: Path) -> list[dict]:
    sting = asm.prepare_sting(sting, run)
    sting_ms = asm.durations_ms([sting])[0]
    durations = dict(zip([p.index for p in parts], asm.durations_ms([wavs[p.index] for p in parts])))
    timings = asm.chapter_timings(parts, durations, sting_ms)
    asm.assemble_audio(run, [sting, *[wavs[p.index] for p in parts], sting], timings, "The Table")
    return timings


def episode_record(day: str, topic: dict, drafted: dict, ruled: dict, timings: list[dict], mp3: Path) -> dict:
    urls = {c["id"]: c["url"] for c in topic["comments"]}
    p_true = {r["claim_index"]: r["p_true"] for r in ruled["rulings"]}
    rounds = []
    for part in ("opening", "round1", "round2", "round3"):
        claims = [{"side": c["side"], "text": c["text"], "p_true": p_true.get(i),
                   "sources": [{"id": s, "url": urls.get(s, "")} for s in c["source_ids"]]}
                  for i, c in enumerate(drafted["claims"]) if c["part"] == part]
        rounds.append({"part": part, "title": "Opening claims" if part == "opening" else f"Round {part[-1]}", "claims": claims})
    story = topic["story"]
    return {"id": f"table-{day}", "day": day, "question": drafted["question"], "positions": drafted.get("positions", {}),
            "thread": {"title": story["title"], "source": story["source"], "url": story["url"]},
            "rounds": rounds, "verdict": ruled["verdict"], "record": ruled["record"],
            "chapters": [{"title": t["title"], "start_ms": t["start_ms"], "end_ms": t["end_ms"]} for t in timings],
            "audio": {"duration_ms": timings[-1]["end_ms"] if timings else 0, "bytes": mp3.stat().st_size,
                      "key": f"audio/table-{asm.audio_key(day, mp3).removeprefix('audio/')}"},
            "voices_synthetic": True}


def table_path(day: str) -> str:
    return f"table/{day}/index.html"


def render_table(ep: dict, prefs: Prefs) -> str:
    winner = {"anchor": "The Anchor takes it.", "uncle": "The Uncle takes it.", "draw": "It's a draw."}[ep["verdict"]["winner"]]
    return env().get_template("table.html").render(ep=ep, station=prefs.station, winner=winner, station_id=STATION_ID,
                                                   duration=_duration(ep["audio"]["duration_ms"]),
                                                   chapters_json=json.dumps(ep["chapters"]))


def publish_table(gw, run: Path, prefs: Prefs) -> list[str]:
    ep = json.loads((run / "table.json").read_text())
    files = [(ep["audio"]["key"], run / "newscast.mp3"), (f"data/{ep['id']}.json", run / "table.json"),
             (table_path(ep["day"]), run / "site" / table_path(ep["day"]))]  # audio first, page last
    for key, path in files:
        put_object(gw, prefs.hosting.bucket, key, path.read_bytes(), CONTENT_TYPES[path.suffix], cache_control(key))
    return [k for k, _ in files]
