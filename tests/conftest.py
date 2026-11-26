import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    """Real payloads captured from the Nov 26 spikes (usernames anonymized)."""
    return json.loads((FIXTURES / name).read_text())


def ffmpeg_works() -> bool:
    """True only if ffmpeg and ffprobe actually run (the dev laptop's Homebrew build is broken)."""
    import subprocess

    try:
        return all(subprocess.run([b, "-version"], capture_output=True).returncode == 0 for b in ("ffmpeg", "ffprobe"))
    except OSError:
        return False


@pytest.fixture
def make_db(tmp_path):
    """Open test databases and close them after the test (no ResourceWarning noise)."""
    from station.store import open_db

    opened = []

    def make(name: str = "s.db"):
        db = open_db(tmp_path / name)
        opened.append(db)
        return db

    yield make
    for db in opened:
        db.close()
