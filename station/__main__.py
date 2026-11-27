"""CLI: one subcommand per pipeline step, each reading and writing files in a run folder.

    python -m station scrape --run data/runs/2026-11-27T09
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
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


def _recent_posts() -> list:
    """Earlier-hour stories new posts may duplicate: aired in 24 h, or judged and still eligible (3 h)."""
    from datetime import timedelta

    from station.store import aired_posts_since, recent_unaired_judged

    now = datetime.now(UTC)
    with closing(_db()) as db:
        aired = aired_posts_since(db, now - timedelta(hours=24))
        eligible = [p for p, _, _ in recent_unaired_judged(db, now - timedelta(hours=LOOKBACK_HOURS))]
    return list({p.id: p for p in [*aired, *eligible]}.values())


def cmd_dedupe(run: Path) -> None:
    from datetime import timedelta

    from station.steps import dedupe as dedupe_mod
    from station.store import aired_posts_since

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("dedupe", "Code + Pinecone") as rec:
        posts = load_posts(run)
        by_id = {p.id: p for p in posts}
        with closing(_db()) as db:
            aired = aired_posts_since(db, datetime.now(UTC) - timedelta(hours=24))
        clusters, candidates = dedupe_mod.cluster(posts, aired, recent=_recent_posts())
        aired_ids = {a.id for a in aired}
        new_stories = [by_id[c.primary_id] for c in clusters
                       if c.primary_id in by_id and c.primary_id not in aired_ids and by_id[c.primary_id].kind == "story"]
        pine, notes = dedupe_mod.pinecone_pairs(Gateway(), new_stories)
        candidates = list(dict.fromkeys([*candidates, *pine]))
        write_json(run, "clusters.json", {"clusters": [asdict(c) for c in clusters], "candidates": candidates})
        rec.counts.update(posts=len(posts), clusters=len(clusters), candidates=len(candidates), pinecone_pairs=len(pine))
        rec.notes.extend(notes)


def cmd_judge(run: Path) -> None:
    from station.steps import judge as judge_mod

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("judge", "TypeSafe Jev") as rec:
        by_id = {p.id: p for p in load_posts(run)}
        clusters = read_json(run, "clusters.json")
        to_judge = [by_id[c["primary_id"]] for c in clusters["clusters"] if c["primary_id"] in by_id]
        skipped = len(clusters["clusters"]) - len(to_judge)
        with closing(_db()) as db:
            judged = judge_mod.judge_all(Gateway(), db, to_judge, [tuple(c) for c in clusters["candidates"]],
                                         known=_recent_posts())
        write_json(run, "judged.json", [j.to_dict() for j in judged])
        rec.counts.update(posts_judged=len(judged), decisions=sum(len(j.answers) for j in judged),
                          input_tokens=sum(j.input_tokens for j in judged), skipped_aired=skipped)
        if len(judged) < len(to_judge):
            rec.notes.append(f"{len(to_judge) - len(judged)} posts failed at Jev and were skipped")


LOOKBACK_HOURS = 3  # Tarik, Nov 26: unaired stories from recent hours compete again


def cmd_rundown(run: Path) -> None:
    from datetime import timedelta

    from station.steps import judge as judge_mod
    from station.steps.rundown import select
    from station.store import recent_unaired_judged

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("rundown", "Code") as rec:
        judged = [judge_mod.Judged.from_dict(d) for d in read_json(run, "judged.json")]
        have = {j.post.id for j in judged}
        with closing(_db()) as db:  # judged in the last few hours, not aired: they compete again
            recent = recent_unaired_judged(db, datetime.now(UTC) - timedelta(hours=LOOKBACK_HOURS))
        carried = [judge_mod.Judged(p, answers, model) for p, answers, model in recent
                   if p.id not in have and set(judge_mod.PER_POST_QUESTIONS) <= set(answers)]
        judged = judged + carried
        t = load_prefs().thresholds
        corr = (run / "corrections.json").exists() and read_json(run, "corrections.json").get("called", 0) > 0
        first = select(judged, t, first_of_day=False, corrections=corr)
        seconds = judge_mod.judge_seconds(Gateway(), [s.post for s in first.stories[1:]])
        rundown = select(judged, t, first_of_day=False, seconds=seconds, corrections=corr)
        write_json(run, "rundown.json", rundown.to_dict())
        rec.counts.update(stories=len(rundown.stories), dropped=len(rundown.dropped_ids), short=rundown.short,
                          overheard=rundown.overheard is not None, carried_over=len(carried))


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


def load_sources(run: Path, stories: list) -> dict:
    """Each story's cluster members from this run; a story carried over from an earlier hour
    (not in this run's posts.json) falls back to its own post."""
    by_id = {p.id: p for p in load_posts(run)}
    members = {c["primary_id"]: c["member_ids"] for c in read_json(run, "clusters.json")["clusters"]}
    out = {}
    for story in stories:
        found = [by_id[m] for m in members.get(story.id, [story.id]) if m in by_id]
        out[story.id] = found or [story]
    return out


def cmd_write(run: Path) -> None:
    from station.steps import write as write_mod
    from station.steps.rundown import Rundown
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("write", "Ollama Cloud") as rec:
        prefs = load_prefs()
        rundown = Rundown.from_dict(read_json(run, "rundown.json"))
        sources = load_sources(run, [s.post for s in rundown.stories])
        read_today, not_aired = today_counts(prefs, len(rundown.stories))
        corr = None
        if rundown.corrections:
            from station.steps.corrections import corrections_chapter

            corr = corrections_chapter(read_json(run, "corrections.json"))
        chapters, notes = write_mod.write_all(Gateway(), rundown, prefs, hour_of(run, prefs.station.timezone),
                                              read_today, not_aired, sources, corrections_chapter=corr)
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
                                     load_sources(run, [s.post for s in rundown.stories]), counts, duration)
        write_json(run, "chapters.json", timings)
        if (run / "newscast.mp3").exists():
            record["audio"]["key"] = asm.audio_key(run.name, run / "newscast.mp3")
        write_json(run, "newscast.json", record)
        from station.store import record_aired

        with closing(_db()) as db:  # the lookback must not re-air these next hour
            record_aired(db, run.name, [(x["id"], x["part"], x["score_matter_week"]) for x in record["stories"]],
                         datetime.now(UTC).isoformat())
        rec.counts.update(chapters=len(timings), duration_s=round(duration / 1000, 1))


def cmd_page(run: Path) -> None:
    from datetime import timedelta

    from station.steps.page import page

    from station.store import counts_by_beat, local_midnight_utc

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("page", "Code") as rec:
        prefs = load_prefs()
        runs_root = Path(os.environ.get("STATION_RUNS", str(run.parent)))
        today = local_midnight_utc(datetime.now(UTC), prefs.station.timezone)
        with closing(_db()) as db:
            yesterday = counts_by_beat(db, today - timedelta(days=1), today)
        written = page(run, prefs, runs_root=runs_root, beat_counts=yesterday, control_room=False)
        rec.counts.update(pages=len(written) + (run / "rundown.json").exists())
    # After the step's log entry is saved, so the control room shows this step and the full build time.
    from station.steps.page import write_control_room

    if (run / "rundown.json").exists():
        write_control_room(run, prefs, read_json(run, "newscast.json"))


def cmd_publish(run: Path) -> None:
    from station.steps.publish import publish

    prefs = load_prefs()
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("publish", "Tigris") as rec:
        keys = publish(Gateway(), run, prefs.hosting.bucket)
        rec.counts.update(files=len(keys), url=f"{prefs.hosting.public_base}/index.html")


def cmd_archive(run: Path) -> None:
    from station.steps.archive import archive

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("archive", "Box") as rec:
        file_id = archive(Gateway(), run)
        rec.counts.update(bytes=(run / f"{run.name}.zip").stat().st_size, box_file_id=file_id)


def cmd_finish(run: Path) -> None:
    from station.steps.finish import finish

    prefs = load_prefs()
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("finish", "Sprite") as rec:
        rec.notes.extend(finish(run, prefs, Gateway()))


def cmd_video(run: Path) -> None:
    from station.steps.video import make_video

    prefs = load_prefs()
    runs_root = Path(os.environ.get("STATION_RUNS", str(run.parent)))
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("video", "Deepgram + Remotion") as rec:
        made = make_video(run.name[:10], Gateway(), prefs, runs_root)
        from station.store import record_decision

        asked_at = datetime.now(UTC).isoformat()
        with closing(_db()) as db:  # every Jev answer is logged with its probability
            for story_id, answer in made["hot_topic_answers"].items():
                record_decision(db, story_id, "hot_topic", answer, made["jev_model"], asked_at)
        rec.counts.update(story=made["headline"], newscast=made["newscast"], seconds=made["durationMs"] / 1000,
                          words=len(made["captions"]), key=made["key"], bytes=made["bytes"],
                          hot_topics_skipped=len(made["skipped"]))


def cmd_table_topic(run: Path) -> None:
    from station.table import topic as topic_mod
    from station.table.threads import threads
    from station.store import record_decision

    prefs = load_prefs()
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("topic", "TypeSafe Jev") as rec:
        with closing(_db()) as db:
            ts = threads(db, run.name, prefs.station.timezone)
            scored, model = topic_mod.score_threads(Gateway(), ts) if ts else ([], None)
            asked_at = datetime.now(UTC).isoformat()
            for s in scored:  # every Jev answer is logged with its probability
                for key, qid in (("dispute", "table_dispute"), ("low_stakes", "table_low_stakes"), ("hot_topic", "hot_topic"),
                                 ("private_harm", "table_private_harm")):
                    record_decision(db, s["story_id"], qid, {"type": "noul", "noul": s[key]}, model, asked_at)
        chosen = topic_mod.pick_topic(scored, harm_max=prefs.thresholds.private_harm_max_probability)
        if not ts:
            out = {"none": True, "reason": "no thread with 6 or more comments"}
        elif chosen is None:
            out = {"none": True, "reason": "no thread was both a real dispute and low-stakes"}
        else:
            t = next(t for t in ts if t.story.id == chosen["story_id"])
            out = {"story": asdict(t.story), "comments": [asdict(c) for c in t.comments], "scores": chosen,
                   "model": model, "considered": len(scored)}
        write_json(run, "topic.json", out)
        rec.counts.update(threads=len(ts), scored=len(scored), picked=out.get("story", {}).get("title"))
        if out.get("none"):
            rec.notes.append(f"No episode today: {out['reason']}.")


def cmd_table_argue(run: Path) -> None:
    from station.table.argue import draft

    topic = read_json(run, "topic.json")
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("argue", "Ollama Cloud") as rec:
        if topic.get("none"):
            rec.notes.append("No episode today.")
            return
        question, claims, (pa, pu) = draft(Gateway(), load_prefs().writer.model, topic["story"], topic["comments"])
        write_json(run, "claims.json", {"question": question, "positions": {"anchor": pa, "uncle": pu},
                                        "claims": [asdict(c) for c in claims]})
        rec.counts.update(claims=len(claims), words=sum(len(c.text.split()) for c in claims))


def cmd_table_referee(run: Path) -> None:
    from station.store import record_decision, season_record
    from station.table.argue import Claim
    from station.table.referee import referee, verdict

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("referee", "TypeSafe Jev") as rec:
        if not (run / "claims.json").exists():
            rec.notes.append("No episode today.")
            return
        topic, drafted = read_json(run, "topic.json"), read_json(run, "claims.json")
        claims = [Claim(c["side"], c["part"], c["text"], tuple(c["source_ids"])) for c in drafted["claims"]]
        rulings, model = referee(Gateway(), drafted["question"], claims, topic["comments"])
        v = verdict(rulings)  # code decides the winner, before any script exists
        asked_at = datetime.now(UTC).isoformat()
        with closing(_db()) as db:
            for r in rulings:  # every Jev answer is logged with its probability
                record_decision(db, f"table:{run.name}:{r.claim_index}", "table_true", {"type": "noul", "noul": r.p_true}, model, asked_at)
                record_decision(db, f"table:{run.name}:{r.claim_index}", "table_answered", {"type": "noul", "noul": r.answered}, model, asked_at)
            record = season_record(db, exclude_day=run.name)  # stored only once published (cmd_table_publish)
        record = {**record, v["winner"]: record[v["winner"]] + 1}
        write_json(run, "rulings.json", {"rulings": [asdict(r) for r in rulings], "verdict": v, "record": record, "model": model})
        rec.counts.update(rulings=len(rulings), anchor=v["anchor"], uncle=v["uncle"], winner=v["winner"])


def cmd_table_script(run: Path) -> None:
    from station.table.argue import Claim
    from station.table.referee import Ruling
    from station.table.script import parts, write_script

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("script", "Ollama Cloud") as rec:
        if not (run / "rulings.json").exists():
            rec.notes.append("No episode today.")
            return
        topic, drafted, ruled = read_json(run, "topic.json"), read_json(run, "claims.json"), read_json(run, "rulings.json")
        claims = [Claim(c["side"], c["part"], c["text"], tuple(c["source_ids"])) for c in drafted["claims"]]
        rulings = [Ruling(**r) for r in ruled["rulings"]]
        script = write_script(Gateway(), load_prefs().writer.model, topic["story"], drafted["question"], claims)
        ps = parts(script, claims, rulings, ruled["verdict"], ruled["record"], topic["story"], drafted["question"])
        fallback = not script["lines"]
        write_json(run, "script.json", {"parts": [asdict(p) for p in ps], "fallback": fallback})
        rec.counts.update(parts=len(ps), words=sum(len(t.text.split()) for p in ps for t in p.turns))
        if fallback:
            rec.notes.append("Writer's delivery failed checks twice; the checked claim text was used: "
                             + "; ".join(script.get("issues", [])))


def _table_parts(run: Path) -> list:
    from station.steps.write import Turn
    from station.table.script import TablePart

    return [TablePart(p["index"], p["kind"], p["title"], tuple(Turn(**t) for t in p["turns"]))
            for p in read_json(run, "script.json")["parts"]]


def cmd_table_voice(run: Path) -> None:
    from station.table.build import voice_parts

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("voice", "Gemini TTS") as rec:
        wavs = voice_parts(Gateway(), _table_parts(run), load_prefs().table_voices, run)
        write_json(run, "voice.json", {"paths": {str(i): str(p) for i, p in wavs.items()}})
        rec.counts.update(parts_voiced=len(wavs))


def cmd_table_assemble(run: Path) -> None:
    from station.table.build import assemble_table, episode_record

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("assemble", "ffmpeg") as rec:
        wavs = {int(i): Path(p) for i, p in read_json(run, "voice.json")["paths"].items()}
        timings = assemble_table(run, _table_parts(run), wavs, STING)
        ep = episode_record(run.name, read_json(run, "topic.json"), read_json(run, "claims.json"),
                            read_json(run, "rulings.json"), timings, run / "newscast.mp3")
        write_json(run, "table.json", ep)
        rec.counts.update(chapters=len(timings), duration_s=round(ep["audio"]["duration_ms"] / 1000, 1))


def cmd_table_page(run: Path) -> None:
    from station.table.build import render_table, table_path

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("page", "Code") as rec:
        out = run / "site" / table_path(run.name)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_table(read_json(run, "table.json"), load_prefs()))
        rec.counts.update(pages=1)


def cmd_table_publish(run: Path) -> None:
    from station.steps import archive as arc
    from station.store import record_episode
    from station.table import build as tb

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("publish", "Tigris + Box") as rec:
        gw = Gateway()
        keys = tb.publish_table(gw, run, load_prefs())
        ruled, topic, drafted = read_json(run, "rulings.json"), read_json(run, "topic.json"), read_json(run, "claims.json")
        v = ruled["verdict"]
        with closing(_db()) as db:  # the season record counts only episodes that went out
            record_episode(db, run.name, drafted["question"], v["anchor"], v["uncle"], v["winner"], topic["story"]["id"])
        try:
            rec.counts.update(box_file_id=arc.archive(gw, run, tb.ARCHIVE_FILES))
        except Exception as e:  # a Box hiccup must not re-run and replace a public episode
            rec.notes.append(f"Box archive failed ({type(e).__name__}: {e}); the episode is public.")
        rec.counts.update(files=len(keys))
        (run / "published").write_text(datetime.now(UTC).isoformat())  # listed on the front page and feed only now


TABLE_STEPS = ["table-topic", "table-argue", "table-referee", "table-script", "table-voice", "table-assemble",
               "table-page", "table-publish"]


def run_table(day: str) -> Path:
    """The whole Table episode for `day`. Any failure raises before publish (no half episode)."""
    run = Path(os.environ.get("STATION_TABLE", "data/table")) / day
    run.mkdir(parents=True, exist_ok=True)
    (run / "published").unlink(missing_ok=True)  # a rebuild is unlisted until it is published again
    for step in TABLE_STEPS:
        COMMANDS[step](run)
        if step == "table-topic" and (run / "topic.json").exists() and read_json(run, "topic.json").get("none"):
            break  # no qualifying thread today: no episode, noted in the run log
    return run


def cmd_table(run: Path) -> None:
    """Build step after the first newscast of the day: The Table from yesterday's threads."""
    from datetime import date, timedelta

    run_table((date.fromisoformat(run.name[:10]) - timedelta(days=1)).isoformat())


def cmd_corrections(run: Path) -> None:
    from station.steps import corrections as cor
    from station.store import record_decision

    prefs = load_prefs()
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("corrections", "Pinecone + TypeSafe Jev") as rec:
        day = run.name[:10]
        with closing(_db()) as db:
            calls = cor.due_calls(db, day, prefs.station.timezone)
            gw = Gateway() if calls else None
            since = datetime.now(UTC) - timedelta(hours=48)
            items, model = cor.grade(gw, [(c, cor.followups(gw, c, db, since)) for c in calls]) if calls else ([], None)
            asked_at = datetime.now(UTC).isoformat()
            for it in items:  # every Jev answer is logged with its probability
                record_decision(db, it["post_id"], "still_discussed", {"type": "noul", "noul": it["p_still"]}, model, asked_at)
        report = cor.summarize(day, items, any(c.newscast_id.startswith("backfill") for c in calls), model)
        write_json(run, "corrections.json", report)
        rec.counts.update(called=report["called"], held=report["held"], faded=report["faded"])


def cmd_story(run: Path) -> None:
    from station.steps.story import make_stories

    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("story", "Ollama + Apify + Gemini") as rec:
        with closing(_db()) as db:
            _, counts = make_stories(Gateway(), run, load_prefs(), db)
        rec.notes.extend(counts.pop("notes"))
        rec.counts.update(counts)


def run_picks(day: str) -> dict:
    from station.picks.step import make_picks

    with closing(_db()) as db:
        return make_picks(Gateway(), load_prefs(), db, day, Path(os.environ.get("STATION_PICKS", "data/picks")))


def cmd_picks(run: Path) -> None:
    """Build step after the first newscast of the day (with Corrections and The Table)."""
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("picks", "Apify + TypeSafe Jev") as rec:
        out = run_picks(run.name[:10])
        rec.notes.extend(out["notes"])
        rec.counts.update(candidates=out["candidates"], picks=len(out["picks"]))


def cmd_radio(run: Path, station_id: str | None = None) -> None:
    """Build step after finish: update every music station (or one, by hand), each a note on failure."""
    from station.radio.model import STATIONS_ROOT
    from station.radio.run import run_station

    ids = [station_id] if station_id else sorted(p.stem for p in STATIONS_ROOT.glob("*.json"))

    def run_all() -> tuple[dict, list[str]]:
        totals: dict = {}
        notes: list[str] = []
        for sid in ids:  # a station that fails is a note; it never stops the build (review I1)
            try:
                with closing(_db()) as db:
                    out = run_station(Gateway(), sid, db, datetime.now(UTC), load_prefs())
            except Exception as e:  # noqa: BLE001
                notes.append(f"{sid}: {type(e).__name__}: {str(e)[:160]}")
                continue
            notes += [f"{sid}: {n}" for n in out.pop("notes", [])]
            totals[sid] = out
        return totals, notes

    if run is None:
        totals, notes = run_all()
        print(json.dumps({"stations": totals, "notes": notes}, indent=1))
        return
    log = RunLog.open(run / "run_log.json", run_id=run.name)
    with log.step("radio", "Apify + Ollama + Jev + Apple Music") as rec:
        totals, notes = run_all()
        rec.notes.extend(notes)
        rec.counts.update({k: sum(t.get(k, 0) for t in totals.values()) for k in ("items", "extracted", "resolved", "seeds", "scheduled")})


COMMANDS = {"scrape": cmd_scrape, "dedupe": cmd_dedupe, "judge": cmd_judge, "rundown": cmd_rundown,
            "write": cmd_write, "voice": cmd_voice, "assemble": cmd_assemble, "page": cmd_page,
            "publish": cmd_publish, "archive": cmd_archive, "finish": cmd_finish, "video": cmd_video, "story": cmd_story, "picks": cmd_picks, "radio": cmd_radio,
            "table-topic": cmd_table_topic, "table-argue": cmd_table_argue,
            "table-referee": cmd_table_referee, "table-script": cmd_table_script, "table-voice": cmd_table_voice,
            "table-assemble": cmd_table_assemble, "table-page": cmd_table_page, "table-publish": cmd_table_publish,
            "table": cmd_table, "corrections": cmd_corrections}


def cmd_build(hour: str | None) -> None:
    from zoneinfo import ZoneInfo

    from station import build as build_mod

    tz = load_prefs().station.timezone
    when = (datetime.strptime(hour, "%Y-%m-%dT%H").replace(tzinfo=ZoneInfo(tz)) if hour
            else build_mod.target_hour(datetime.now(ZoneInfo(tz))))
    from station import manager
    from station.steps.finish import in_broadcast_hours

    if not hour and not in_broadcast_hours(datetime.now(ZoneInfo(tz)), load_prefs()):
        print(f"build {when:%Y-%m-%dT%H}: outside broadcast hours, nothing to do")
        return
    last_hour = int(load_prefs().station.last_newscast.split(":")[0])
    first_hour = int(load_prefs().station.first_newscast.split(":")[0])
    news = [s for s in build_mod.STEPS if s != "radio"]  # the music stations always run last (review I1)
    extra = ({"steps": [*news, "video", "radio"]} if when.hour == last_hour  # daily video after the last newscast
             else {"steps": [*[s for st in news for s in (["corrections", st] if st == "rundown" else [st])],
                             "table", "picks", "radio"]} if when.hour == first_hour  # Corrections, The Table, music picks
             else {})
    result = build_mod.build(when, on_failure=manager.on_failure, **extra)
    print(f"build {when:%Y-%m-%dT%H}: {'skipped, another build holds the lock' if result is None else result}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="station")
    parser.add_argument("step", choices=sorted([*COMMANDS, "build"]))
    parser.add_argument("--run", type=Path, help="run folder for one step, e.g. data/runs/2026-11-27T09")
    parser.add_argument("--hour", help="build: newscast hour YYYY-MM-DDTHH (local); default = next top of the hour")
    parser.add_argument("--day", help="video: YYYY-MM-DD; uses that day's last run folder")
    parser.add_argument("--station", help="radio: one music station id (config/stations/<id>.json)")
    args = parser.parse_args(argv)
    if args.step == "table" and args.day:
        run_table(args.day)
        return 0
    if args.step == "radio" and args.run is None:
        cmd_radio(None, args.station)
        return 0
    if args.step == "picks" and args.day:
        print(json.dumps(run_picks(args.day), indent=1))
        return 0
    if args.step == "video" and args.day and args.run is None:
        runs = sorted(Path(os.environ.get("STATION_RUNS", "data/runs")).glob(f"{args.day}T??"))
        if not runs:
            parser.error(f"no runs for {args.day}")
        args.run = runs[-1]
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
