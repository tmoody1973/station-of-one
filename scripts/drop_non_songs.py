"""Take spoken tracks matched by mistake (commentary, interviews, skits) out of every station's rotation.
Run on the Sprite:  .venv/bin/python scripts/drop_non_songs.py --dry-run   then without --dry-run."""
import argparse
import sqlite3

from station.radio.library import drop_non_songs

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--db", default="data/station.db")
args = ap.parse_args()
hits = drop_non_songs(sqlite3.connect(args.db), dry_run=args.dry_run)
for station, artist, title in hits:
    print(f"{station}: {artist} - {title}")
print(("would remove" if args.dry_run else "removed"), len(hits), "rotation rows")
