import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    """Real payloads captured from the Nov 26 spikes (usernames anonymized)."""
    return json.loads((FIXTURES / name).read_text())
