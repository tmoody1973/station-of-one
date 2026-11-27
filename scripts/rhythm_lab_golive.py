"""Load the Rhythm Lab library into its station (Rhythm Lab plan, go-live). Run on the Sprite.

  .venv/bin/python scripts/rhythm_lab_golive.py --db /tmp/rehearsal.db   # rehearse on a copy first
  .venv/bin/python scripts/rhythm_lab_golive.py                          # data/station.db

Safe to run again: rotation keeps plays and the meeting's moves; pairs and notes are rebuilt from the export.
The notes stay in the private database; nothing here publishes anything."""
import argparse
import sqlite3
from pathlib import Path

from station.radio.library import seed_rotation
from station.radio.model import load_station, open_radio
from station.radio.notes import import_notes
from station.radio.pairs import import_pairs

LIB = Path("data/library/rhythm_lab")
ap = argparse.ArgumentParser()
ap.add_argument("--db", default="data/station.db")
db = sqlite3.connect(ap.parse_args().db)
open_radio(db)
print("rotation:", seed_rotation(db, load_station("rhythm-lab")))
print("pairs:", import_pairs(db, LIB / "rhythm_lab_plays.csv"))
print("notes (private):", import_notes(db, LIB / "rhythm_lab_artist_notes.json"))
print("energy:", dict(db.execute("SELECT energy, COUNT(*) FROM rotation WHERE station_id = 'rhythm-lab' GROUP BY 1")))
print("openers/closers:", db.execute("SELECT SUM(opener), SUM(closer) FROM rotation WHERE station_id = 'rhythm-lab'").fetchone())
print("holiday-tagged:", db.execute("SELECT COUNT(*) FROM rotation WHERE station_id = 'rhythm-lab' AND tags LIKE '%holiday%'").fetchone()[0])
