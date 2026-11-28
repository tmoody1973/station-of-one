"""ONE Jazz go-live (jazz station plan): match the core jazz tracks not yet on Apple Music, then load the jazz rotation.
Run on the Sprite. Rehearse first on a copy:  .venv/bin/python scripts/jazz_golive.py --db /tmp/rehearsal.db
The jazz file (data/library/jazz_library.csv) and the library stay private; nothing here publishes anything."""
import argparse
import sqlite3
from dataclasses import replace
from pathlib import Path

from station.gateway import Gateway
from station.radio.jazz import jazz_tracks, seed_jazz_rotation
from station.radio.library import match_library
from station.radio.model import load_station, open_radio

JAZZ = Path("data/library/jazz_library.csv")
ap = argparse.ArgumentParser()
ap.add_argument("--db", default="data/station.db")
ap.add_argument("--station", default="jazz")
ap.add_argument("--no-match", action="store_true", help="skip the Apple Music lookups")
a = ap.parse_args()
db = sqlite3.connect(a.db)
open_radio(db)
try:
    station = load_station(a.station)
except FileNotFoundError:  # before the jazz config exists (Task 2): borrow Rhythm Lab's connection and storefront
    station = replace(load_station("rhythm-lab"), id=a.station)
if not a.no_match:
    counts = match_library(Gateway(), station.apple_connection, station.storefront, db, min_plays=1, only=set(jazz_tracks(JAZZ)),
                           progress=lambda i, n, c: print(f"  {i}/{n} {c}", flush=True))
    print("matched:", counts)
for style, cats in sorted(seed_jazz_rotation(db, station, JAZZ).items()):
    print(f"{style:22s} {cats}  total {sum(cats.values())}")
