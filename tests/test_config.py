from pathlib import Path

import pytest

from station.config import load_prefs
from station.runs import read_json, write_json

PREFS = Path("config/preferences.json")


def test_loads_thresholds():
    p = load_prefs(PREFS)
    assert p.thresholds.air_min_probability == 0.4
    assert p.thresholds.private_harm_max_probability == 0.2
    assert (p.thresholds.min_stories, p.thresholds.max_stories) == (3, 5)


def test_voices():
    v = load_prefs(PREFS).voices
    assert (v.host, v.reporter) == ("Kore", "Charon")
    assert v.style == "brisk, warm, conversational news read"


def test_beats_and_sources():
    p = load_prefs(PREFS)
    ai = next(b for b in p.beats if b.id == "ai-dev")
    assert ai.used_in == "newscast"
    assert any(s.type == "hackernews" for s in ai.sources)
    assert p.station.timezone == "America/Chicago"
    assert p.writer.model == "gemma4:31b"
    assert p.station.id_lines_newscast[0] == "WONE, 1.0 FM. One station, one listener."


def test_rejects_missing_threshold(tmp_path):  # fail fast at the boundary
    bad = tmp_path / "p.json"
    bad.write_text('{"thresholds": {}}')
    with pytest.raises(ValueError, match="air_min_probability"):
        load_prefs(bad)


def test_write_json_is_atomic(tmp_path):
    write_json(tmp_path, "x.json", {"a": 1})
    assert read_json(tmp_path, "x.json") == {"a": 1}
    assert not list(tmp_path.glob("*.tmp"))
