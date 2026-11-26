"""CLI: one subcommand per pipeline step, each reading and writing files in a run folder.

    python -m station scrape --run data/runs/2026-11-27T09
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from station.config import load_prefs
from station.gateway import Gateway
from station.runlog import RunLog
from station.runs import read_json, write_json
from station.store import open_db


def _db():
    return open_db(Path(os.environ.get("STATION_DB", "data/station.db")))


def cmd_scrape(run: Path) -> None:
    from station.steps import scrape as scrape_mod

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("scrape", "Apify") as rec:
        result = scrape_mod.scrape(Gateway(), load_prefs(), _db(), datetime.now(UTC))
        write_json(run, "posts.json", [asdict(p) for p in result.posts])
        rec.counts.update(result.counts)
        rec.notes.extend(result.notes)


def load_posts(run: Path) -> list:
    from station.store import Post

    return [Post(**d) for d in read_json(run, "posts.json")]


def cmd_dedupe(run: Path) -> None:
    from datetime import timedelta

    from station.steps.dedupe import cluster
    from station.store import aired_posts_since

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("dedupe", "Code (link match)") as rec:  # Task 16 adds Pinecone
        posts = load_posts(run)
        aired = aired_posts_since(_db(), datetime.now(UTC) - timedelta(hours=24))
        clusters, candidates = cluster(posts, aired)
        write_json(run, "clusters.json", {"clusters": [asdict(c) for c in clusters], "candidates": candidates})
        rec.counts.update(posts=len(posts), clusters=len(clusters), candidates=len(candidates))


COMMANDS = {"scrape": cmd_scrape, "dedupe": cmd_dedupe}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="station")
    parser.add_argument("step", choices=sorted(COMMANDS))
    parser.add_argument("--run", required=True, type=Path, help="run folder, e.g. data/runs/2026-11-27T09")
    args = parser.parse_args(argv)
    args.run.mkdir(parents=True, exist_ok=True)
    COMMANDS[args.step](args.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
