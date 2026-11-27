"""Import a curator's library into the Sprite's private database and match it on Apple Music.
Run on the Sprite:  .venv/bin/python scripts/library_match.py data/library/rhythm_lab [min_plays]
Progress goes to data/library/match.log. The library files and the database never go into the repo."""
import sys
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

from station.gateway import Gateway
from station.radio.library import import_tracks, match_library
from station.radio.model import load_station
from station.store import open_db

folder = Path(sys.argv[1])
min_plays = int(sys.argv[2]) if len(sys.argv) > 2 else 2
conn = load_station("uk-jazz").apple_connection  # the Apple Music custom_api connector
log = open(folder.parent / "match.log", "a", buffering=1)
start = time.time()
with closing(open_db()) as db:
    n = import_tracks(db, folder / "rhythm_lab_tracks.csv")
    log.write(f"{datetime.now():%H:%M:%S} imported {n} tracks\n")
    counts = match_library(Gateway(), conn, "us", db, min_plays=min_plays, workers=4,
                           progress=lambda i, total, c: log.write(f"{datetime.now():%H:%M:%S} {i}/{total} {c} "
                                                                  f"{time.time() - start:.0f}s\n"))
log.write(f"{datetime.now():%H:%M:%S} done {counts} in {time.time() - start:.0f}s\n")
