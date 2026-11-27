"""Write the private held report for the Rhythm Lab library (Rhythm Lab plan, Task 1).
Run on the Sprite: .venv/bin/python scripts/library_report.py  ->  data/library/held.csv (never committed)."""
import sqlite3
from pathlib import Path

from station.radio.library import held_report

OUT = Path("data/library/held.csv")
print(held_report(sqlite3.connect("data/station.db"), OUT), "tracks ->", OUT)
