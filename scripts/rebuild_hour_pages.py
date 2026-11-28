"""Rebuild past hours' pages (hour page + story pages) in today's site frame and republish them.
Tarik, Nov 27 8:51 pm: pages built before the site shell had no menu, strip or player. Content is unchanged;
the front page is never touched. Run on the Sprite:
  .venv/bin/python scripts/rebuild_hour_pages.py --dry-run     # render only, print counts
  .venv/bin/python scripts/rebuild_hour_pages.py               # render and publish"""
import argparse
from pathlib import Path

from station.build import LOCK
from station.config import load_prefs
from station.gateway import Gateway
from station.steps.page import all_newscasts, hour_pages, table_episodes
from station.table.build import render_table, table_path
from station.steps.publish import cache_control, put_object

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--runs", default="data/runs")
args = ap.parse_args()
if LOCK.exists() and not args.dry_run:
    raise SystemExit("a build holds the lock; not publishing")
prefs, gw, total = load_prefs(), Gateway(), 0
for n in sorted(all_newscasts(Path(args.runs)), key=lambda n: n["id"]):
    try:
        pages = hour_pages(Path(args.runs) / n["id"], prefs, Path(args.runs))
    except (KeyError, TypeError, ValueError, OSError) as e:
        print(f"{n['id']}: skipped ({type(e).__name__}: {e})")
        continue
    for key, html in pages.items():
        if not args.dry_run:
            put_object(gw, prefs.hosting.bucket, key, html.encode(), "text/html; charset=utf-8", cache_control(key))
    total += len(pages)
    print(f"{n['id']}: {len(pages)} pages")
for ep in table_episodes(Path("data/table")):  # The Table's pages too (Tarik, Nov 28: the Nov 26 page had the old look)
    if not args.dry_run:
        put_object(gw, prefs.hosting.bucket, table_path(ep["day"]), render_table(ep, prefs).encode(), "text/html; charset=utf-8",
                   cache_control(table_path(ep["day"])))
    total += 1
    print(f"table {ep['day']}: 1 page")
print(("would publish" if args.dry_run else "published"), total, "pages")
