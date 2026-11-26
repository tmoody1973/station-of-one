"""CLI: one subcommand per pipeline step, each reading and writing files in a run folder.

    python -m station scrape --run data/runs/2026-11-27T09
"""
from __future__ import annotations

import argparse
import os
import sys
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from station.config import load_prefs
from station.gateway import Gateway
from station.runlog import RunLog
from station.runs import read_json, write_json
from station.store import open_db


def _db():
    """Open the station database; callers close it with contextlib.closing."""
    return open_db(Path(os.environ.get("STATION_DB", "data/station.db")))


def cmd_scrape(run: Path) -> None:
    from station.steps import scrape as scrape_mod

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("scrape", "Apify") as rec:
        with closing(_db()) as db:
            result = scrape_mod.scrape(Gateway(), load_prefs(), db, datetime.now(UTC))
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
        with closing(_db()) as db:
            aired = aired_posts_since(db, datetime.now(UTC) - timedelta(hours=24))
        clusters, candidates = cluster(posts, aired)
        write_json(run, "clusters.json", {"clusters": [asdict(c) for c in clusters], "candidates": candidates})
        rec.counts.update(posts=len(posts), clusters=len(clusters), candidates=len(candidates))


def cmd_judge(run: Path) -> None:
    from station.steps import judge as judge_mod

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("judge", "TypeSafe Jev") as rec:
        by_id = {p.id: p for p in load_posts(run)}
        clusters = read_json(run, "clusters.json")
        to_judge = [by_id[c["primary_id"]] for c in clusters["clusters"] if c["primary_id"] in by_id]
        skipped = len(clusters["clusters"]) - len(to_judge)
        with closing(_db()) as db:
            judged = judge_mod.judge_all(Gateway(), db, to_judge, [tuple(c) for c in clusters["candidates"]])
        write_json(run, "judged.json", [j.to_dict() for j in judged])
        rec.counts.update(posts_judged=len(judged), decisions=sum(len(j.answers) for j in judged),
                          input_tokens=sum(j.input_tokens for j in judged), skipped_aired=skipped)
        if len(judged) < len(to_judge):
            rec.notes.append(f"{len(to_judge) - len(judged)} posts failed at Jev and were skipped")


def cmd_rundown(run: Path) -> None:
    from station.steps import judge as judge_mod
    from station.steps.rundown import select

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("rundown", "Code") as rec:
        judged = [judge_mod.Judged.from_dict(d) for d in read_json(run, "judged.json")]
        t = load_prefs().thresholds
        first = select(judged, t, first_of_day=False)
        seconds = judge_mod.judge_seconds(Gateway(), [s.post for s in first.stories[1:]])
        rundown = select(judged, t, first_of_day=False, seconds=seconds)
        write_json(run, "rundown.json", rundown.to_dict())
        rec.counts.update(stories=len(rundown.stories), dropped=len(rundown.dropped_ids), short=rundown.short,
                          overheard=rundown.overheard is not None)


def hour_of(run: Path, tz: str) -> datetime:
    """Run folders are named <YYYY-MM-DDTHH>; anything else means 'now' (hand-run test folders)."""
    from zoneinfo import ZoneInfo

    try:
        return datetime.strptime(run.name, "%Y-%m-%dT%H").replace(tzinfo=ZoneInfo(tz))
    except ValueError:
        return datetime.now(ZoneInfo(tz)).replace(minute=0, second=0, microsecond=0)


def today_counts(prefs, stories_this_hour: int) -> tuple[int, int]:
    """(posts read since local midnight, posts read today that did not make air)."""
    from station.store import aired_count_since, local_midnight_utc, posts_read_since

    midnight = local_midnight_utc(datetime.now(UTC), prefs.station.timezone)
    with closing(_db()) as db:
        read_today = posts_read_since(db, midnight)
        aired = aired_count_since(db, midnight) + stories_this_hour
    return read_today, max(read_today - aired, 0)


def load_sources(run: Path, story_ids: list[str]) -> dict:
    by_id = {p.id: p for p in load_posts(run)}
    members = {c["primary_id"]: c["member_ids"] for c in read_json(run, "clusters.json")["clusters"]}
    return {sid: [by_id[m] for m in members.get(sid, [sid]) if m in by_id] for sid in story_ids}


def cmd_write(run: Path) -> None:
    from station.steps import write as write_mod
    from station.steps.rundown import Rundown
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("write", "Ollama Cloud") as rec:
        prefs = load_prefs()
        rundown = Rundown.from_dict(read_json(run, "rundown.json"))
        sources = load_sources(run, [s.post.id for s in rundown.stories])
        read_today, not_aired = today_counts(prefs, len(rundown.stories))
        chapters, notes = write_mod.write_all(Gateway(), rundown, prefs, hour_of(run, prefs.station.timezone),
                                              read_today, not_aired, sources)
        write_json(run, "scripts.json", [c.to_dict() for c in chapters])
        rec.counts.update(chapters=len(chapters), words=sum(len(t.text.split()) for c in chapters for t in c.turns),
                          read_today=read_today, not_aired_today=not_aired)
        rec.notes.extend(notes)


def cmd_voice(run: Path) -> None:
    from station.steps import voice as voice_mod
    from station.steps.write import Chapter

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("voice", "Gemini TTS") as rec:
        chapters = [Chapter.from_dict(d) for d in read_json(run, "scripts.json")]
        result = voice_mod.voice_all(Gateway(), chapters, load_prefs().voices, run)
        write_json(run, "voice.json", {"paths": {i: str(p) for i, p in result.paths.items()},
                                       "seconds": result.seconds, "failed": result.failed})
        rec.counts.update(chapters_voiced=len(result.paths), failed=len(result.failed),
                          audio_seconds=round(sum(result.seconds.values()), 1))
        rec.notes.extend(result.notes)
        required = {c.index: c.kind for c in chapters if c.kind in ("open", "signoff")}
        missing = [required[i] for i in result.failed if i in required]
        if missing:
            raise RuntimeError(f"required chapters not voiced: {', '.join(missing)}")


STING = Path("assets/sting.wav")


def cmd_assemble(run: Path) -> None:
    from station.steps import assemble as asm
    from station.steps.rundown import Rundown
    from station.steps.write import Chapter

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("assemble", "ffmpeg") as rec:
        prefs = load_prefs()
        chapters = [Chapter.from_dict(d) for d in read_json(run, "scripts.json")]
        paths = {int(i): Path(p) for i, p in read_json(run, "voice.json")["paths"].items()}
        voiced = [c for c in chapters if c.index in paths]
        sting = asm.prepare_sting(STING, run)
        sting_ms = asm.durations_ms([sting])[0]
        durations = dict(zip([c.index for c in voiced], asm.durations_ms([paths[c.index] for c in voiced])))
        timings = asm.chapter_timings(chapters, durations, sting_ms)
        asm.assemble_audio(run, [sting, *[paths[c.index] for c in voiced], sting], timings, prefs.station.show_name)
        rundown = Rundown.from_dict(read_json(run, "rundown.json"))
        read_today, not_aired = today_counts(prefs, len(rundown.stories))
        counts = {"posts_read_hour": len(read_json(run, "posts.json")), "posts_read_today": read_today,
                  "stories_aired": len(rundown.stories), "posts_not_aired_today": not_aired}
        duration = timings[-1]["end_ms"] if timings else 0
        record = asm.newscast_record(run.name, hour_of(run, prefs.station.timezone), prefs, chapters, timings, rundown,
                                     load_sources(run, [s.post.id for s in rundown.stories]), counts, duration)
        write_json(run, "chapters.json", timings)
        write_json(run, "newscast.json", record)
        rec.counts.update(chapters=len(timings), duration_s=round(duration / 1000, 1))


COMMANDS = {"scrape": cmd_scrape, "dedupe": cmd_dedupe, "judge": cmd_judge, "rundown": cmd_rundown,
            "write": cmd_write, "voice": cmd_voice, "assemble": cmd_assemble}


def cmd_build(hour: str | None) -> None:
    from zoneinfo import ZoneInfo

    from station import build as build_mod

    tz = load_prefs().station.timezone
    when = (datetime.strptime(hour, "%Y-%m-%dT%H").replace(tzinfo=ZoneInfo(tz)) if hour
            else build_mod.target_hour(datetime.now(ZoneInfo(tz))))
    result = build_mod.build(when)
    print(f"build {when:%Y-%m-%dT%H}: {'skipped, another build holds the lock' if result is None else result}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="station")
    parser.add_argument("step", choices=sorted([*COMMANDS, "build"]))
    parser.add_argument("--run", type=Path, help="run folder for one step, e.g. data/runs/2026-11-27T09")
    parser.add_argument("--hour", help="build: newscast hour YYYY-MM-DDTHH (local); default = next top of the hour")
    args = parser.parse_args(argv)
    if args.step == "build":
        cmd_build(args.hour)
        return 0
    if args.run is None:
        parser.error(f"{args.step} needs --run")
    args.run.mkdir(parents=True, exist_ok=True)
    COMMANDS[args.step](args.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
