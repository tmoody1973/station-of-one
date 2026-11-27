"""Tarik's show notes (Rhythm Lab plan, Task 5): private raw material for Plan B2's voice breaks, which rewrite
and cite and never read them verbatim. They live only in the Sprite's database; no page or JSON reads this table."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def import_notes(db: sqlite3.Connection, notes_json: Path) -> int:
    db.execute("CREATE TABLE IF NOT EXISTS artist_notes (artist TEXT, date TEXT, source TEXT, note TEXT)")
    db.execute("DELETE FROM artist_notes")  # rebuilt from the export each time
    rows = [(a["artist"], n.get("date"), n.get("source"), n.get("note"))
            for a in json.loads(Path(notes_json).read_text(encoding="utf-8-sig")) for n in a.get("notes") or []]
    db.executemany("INSERT INTO artist_notes VALUES (?,?,?,?)", rows)
    db.commit()
    return len(rows)
