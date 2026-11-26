import json
import subprocess
import wave
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from station.config import load_prefs
from station.steps.assemble import (
    assemble_audio, chapter_metadata, chapter_timings, durations_ms, escape_meta, newscast_record,
)
from station.steps.rundown import Rundown
from station.steps.write import Chapter, Turn
from tests.test_rundown import j
from tests.conftest import ffmpeg_works
from tests.test_voice import wav_bytes

CHS = [Chapter(0, "open", "Open", None, (Turn("host", "o"),)),
       Chapter(1, "lead", "Lead story", "a", (Turn("host", "l"),), "Lead headline", "One. Two."),
       Chapter(2, "story", "Story 2", "b", (Turn("host", "s"),), "Second headline", "Three. Four."),
       Chapter(3, "signoff", "Sign-off", None, (Turn("host", "z"),))]


def test_chapter_title_escaping():  # Review Focus 1
    assert escape_meta('Q&A = "yes"; #1') == 'Q&A \\= "yes"\; \\#1'
    assert escape_meta("back\\slash\nline") == "back\\\\slash\\\nline"


def test_chapter_metadata_format():
    text = chapter_metadata([("Open", 0, 1000), ("Story; 2", 1000, 2500)], "The Hourly Scroll")
    assert text.startswith(";FFMETADATA1\ntitle=The Hourly Scroll\n")
    assert "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1000\nEND=2500\ntitle=Story\; 2\n" in text


def test_chapter_times_are_cumulative_with_sting_in_open_and_signoff():
    t = chapter_timings(CHS, {0: 8000, 1: 26000, 2: 11000, 3: 8000}, sting_ms=2000)
    assert [(c["title"], c["start_ms"], c["end_ms"]) for c in t] == [
        ("Open", 0, 10000), ("Lead story", 10000, 36000), ("Story 2", 36000, 47000), ("Sign-off", 47000, 57000)]


def test_failed_chapter_skipped_in_timings():
    t = chapter_timings(CHS, {0: 8000, 1: 26000, 3: 8000}, sting_ms=2000)
    assert [c["title"] for c in t] == ["Open", "Lead story", "Sign-off"] and t[-1]["end_ms"] == 46000


def test_durations_ms(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(wav_bytes(1.5))
    assert durations_ms([p]) == [1500]


def test_newscast_json_matches_contract():
    rd = Rundown((j("a", 0.62), j("b", 0.5)), {"a": 90, "b": 30}, None, ("x",), (j("c", 0.39),), False, False)
    timings = chapter_timings(CHS, {0: 8000, 1: 26000, 2: 11000, 3: 8000}, 2000)
    rec = newscast_record("2026-11-27T09", datetime(2026, 11, 27, 9, tzinfo=ZoneInfo("America/Chicago")), load_prefs(),
                          CHS, timings, rd, sources={"a": [j("a", 0.62).post]},
                          counts={"posts_read_hour": 164, "posts_read_today": 2140, "stories_aired": 2,
                                  "posts_not_aired_today": 2138}, duration_ms=57000)
    assert set(rec) >= {"id", "hour_local", "show", "station", "frequency", "short", "counts", "stories", "almost",
                        "overheard", "chapters", "audio", "voices_synthetic"}
    assert rec["voices_synthetic"] is True and rec["audio"] == {"file": "newscast.mp3", "duration_ms": 57000}
    lead = rec["stories"][0]
    assert (lead["id"], lead["part"], lead["headline"], lead["score_matter_week"], lead["seconds"]) == (
        "a", "lead", "Lead headline", 0.62, 90)
    assert lead["sources"][0]["url"] == "https://ex.com/a" and lead["chapter_start_ms"] == 10000
    assert [a["post_id"] for a in rec["almost"]] == ["c"]  # dropped post "x" never listed


@pytest.mark.ffmpeg
@pytest.mark.skipif(not ffmpeg_works(), reason="needs a working ffmpeg (run on the Sprite)")
def test_mp3_has_chapters(tmp_path):
    wavs = []
    for i, secs in enumerate((1.0, 2.0, 1.5)):
        p = tmp_path / f"ch_{i:02d}.wav"
        p.write_bytes(wav_bytes(secs))
        wavs.append(p)
    sting = tmp_path / "sting.wav"
    sting.write_bytes(wav_bytes(0.5))
    chs = [CHS[0], CHS[1], CHS[3]]
    timings = chapter_timings(chs, {0: 1000, 1: 2000, 3: 1500}, sting_ms=500)
    out = assemble_audio(tmp_path, [sting, *wavs, sting], timings, "Test")
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", str(out)],
                                      capture_output=True, text=True, check=True).stdout)
    assert [c["tags"]["title"] for c in probe["chapters"]] == ["Open", "Lead story", "Sign-off"]
    assert out.read_bytes()[:3] == b"ID3"
