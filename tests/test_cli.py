import json

from station.__main__ import main


def test_scrape_cli_writes_posts_json(tmp_path, monkeypatch):
    from station.steps import scrape as scrape_mod
    from station.store import Post

    fake_post = Post("hn:1", "Hacker News", "ai-dev", "story", "u", "T", "https://x", "", "2026-11-27T14:00:00Z", {}, "public")
    monkeypatch.setattr(scrape_mod, "scrape", lambda gw, prefs, db, now: scrape_mod.ScrapeResult([fake_post], {"new_posts": 1}, []))
    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "run"
    assert main(["scrape", "--run", str(run)]) == 0
    assert json.loads((run / "posts.json").read_text())[0]["id"] == "hn:1"
    step = json.loads((run / "run_log.json").read_text())["steps"][0]
    assert (step["name"], step["tool"], step["counts"]["new_posts"]) == ("scrape", "Apify", 1)


def test_dedupe_cli_writes_clusters(tmp_path, monkeypatch):
    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "run"
    run.mkdir()
    post = {"id": "hn:1", "source": "Hacker News", "beat": "ai-dev", "kind": "story", "author": "u", "title": "T",
            "url": "https://ex.com/a", "text": "", "posted_at": "2026-11-27T14:00:00Z", "engagement": {}, "visibility": "public"}
    (run / "posts.json").write_text(json.dumps([post, {**post, "id": "rss:1", "url": "https://ex.com/a?utm_source=x"}]))
    from station.steps import dedupe as dedupe_mod

    asked = []
    monkeypatch.setattr(dedupe_mod, "pinecone_pairs",
                        lambda gw, stories: asked.extend(s.id for s in stories) or ([("old:9", "hn:1")], []))
    monkeypatch.setattr("station.__main__.Gateway", lambda: None)
    assert main(["dedupe", "--run", str(run)]) == 0
    out = json.loads((run / "clusters.json").read_text())
    assert out["clusters"] == [{"primary_id": "hn:1", "member_ids": ["hn:1", "rss:1"]}]
    assert out["candidates"] == [["old:9", "hn:1"]] and asked == ["hn:1"]
    assert json.loads((run / "run_log.json").read_text())["steps"][-1]["counts"] == {
        "posts": 2, "clusters": 1, "candidates": 1, "pinecone_pairs": 1}


def test_judge_cli_judges_cluster_primaries_only(tmp_path, monkeypatch):
    from station.steps import judge as judge_mod

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "run"
    run.mkdir()
    base = {"source": "HN", "beat": "ai-dev", "kind": "story", "author": "u", "title": "T", "text": "",
            "posted_at": "2026-11-27T14:00:00Z", "engagement": {}, "visibility": "public"}
    (run / "posts.json").write_text(json.dumps([{**base, "id": "hn:1", "url": "https://a"},
                                                {**base, "id": "rss:1", "url": "https://a"},
                                                {**base, "id": "rss:2", "url": "https://b"}]))
    (run / "clusters.json").write_text(json.dumps({"clusters": [
        {"primary_id": "hn:1", "member_ids": ["hn:1", "rss:1"]},
        {"primary_id": "hn:old", "member_ids": ["hn:old", "rss:2"]}], "candidates": []}))
    seen = []

    def fake_judge_all(gw, db, posts, candidates, concurrency=8, known=()):
        seen.extend(p.id for p in posts)
        return [judge_mod.Judged(posts[0], {"matter_week": {"type": "noul", "noul": 0.5}}, "jev-1.14.0", (), 600)]

    monkeypatch.setattr(judge_mod, "judge_all", fake_judge_all)
    assert main(["judge", "--run", str(run)]) == 0
    assert seen == ["hn:1"]  # rss:1 is merged; hn:old already aired
    assert json.loads((run / "judged.json").read_text())[0]["post"]["id"] == "hn:1"
    counts = json.loads((run / "run_log.json").read_text())["steps"][-1]["counts"]
    assert counts == {"posts_judged": 1, "decisions": 1, "input_tokens": 600, "skipped_aired": 1}


def test_rundown_cli(tmp_path, monkeypatch):
    from station.steps import judge as judge_mod
    from tests.test_rundown import j

    run = tmp_path / "run"
    run.mkdir()
    (run / "judged.json").write_text(json.dumps([j("a", 0.6).to_dict(), j("b", 0.5).to_dict(), j("x", 0.6, harm=0.4).to_dict()]))
    asked = []
    monkeypatch.setattr(judge_mod, "judge_seconds", lambda gw, stories: asked.extend(s.id for s in stories) or {"b": 33})
    assert main(["rundown", "--run", str(run)]) == 0
    out = json.loads((run / "rundown.json").read_text())
    assert [s["post"]["id"] for s in out["stories"]] == ["a", "b"] and out["seconds"] == {"a": 90, "b": 33}
    assert asked == ["b"] and out["short"] is True and out["dropped_ids"] == ["x"]
    counts = json.loads((run / "run_log.json").read_text())["steps"][-1]["counts"]
    assert counts == {"stories": 2, "dropped": 1, "short": True, "overheard": False, "carried_over": 0}


def test_write_cli_uses_cluster_sources_and_counts(tmp_path, monkeypatch):
    from station.steps import write as write_mod
    from station.steps.rundown import Rundown
    from tests.test_rundown import j

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "2026-11-27T09"
    run.mkdir()
    lead = j("hn:1", 0.6)
    (run / "rundown.json").write_text(json.dumps(Rundown((lead,), {"hn:1": 90}, None, (), (), True, False).to_dict()))
    base = {"source": "Ex", "beat": "ai-dev", "kind": "story", "author": "u", "title": "T", "text": "", "url": "https://a",
            "posted_at": "2026-11-27T14:00:00Z", "engagement": {}, "visibility": "public"}
    (run / "posts.json").write_text(json.dumps([{**base, "id": "hn:1"}, {**base, "id": "rss:9"}]))
    (run / "clusters.json").write_text(json.dumps({"clusters": [{"primary_id": "hn:1", "member_ids": ["hn:1", "rss:9"]}],
                                                   "candidates": []}))
    captured = {}

    def fake_write_all(gw, rundown, prefs, hour_local, read_today, not_aired_today, sources, concurrency=3, corrections_chapter=None):
        captured.update(hour=hour_local.hour, sources={k: [p.id for p in v] for k, v in sources.items()})
        return [write_mod.Chapter(0, "open", "Open", None, (write_mod.Turn("host", "hi"),))], ["note"]

    monkeypatch.setattr(write_mod, "write_all", fake_write_all)
    assert main(["write", "--run", str(run)]) == 0
    assert captured == {"hour": 9, "sources": {"hn:1": ["hn:1", "rss:9"]}}
    assert json.loads((run / "scripts.json").read_text())[0]["kind"] == "open"
    step = json.loads((run / "run_log.json").read_text())["steps"][-1]
    assert (step["tool"], step["counts"]["chapters"], step["notes"]) == ("Ollama Cloud", 1, ["note"])


def _scripts(run):
    from station.steps.write import Chapter, Turn
    chs = [Chapter(0, "open", "Open", None, (Turn("host", "o"),)), Chapter(1, "story", "Story 2", "hn:2", (Turn("host", "s"),)),
           Chapter(2, "signoff", "Sign-off", None, (Turn("host", "b"),))]
    (run / "scripts.json").write_text(json.dumps([c.to_dict() for c in chs]))


def test_voice_cli_tolerates_failed_story(tmp_path, monkeypatch):
    import pytest
    from station.steps import voice as voice_mod

    run = tmp_path / "run"
    run.mkdir()
    _scripts(run)
    monkeypatch.setattr(voice_mod, "voice_all", lambda gw, chs, voices, run_: voice_mod.VoiceResult(
        {0: run_ / "audio/ch_00.wav", 2: run_ / "audio/ch_02.wav"}, {0: 4.0, 2: 6.0}, [1], ["Story 2 not voiced: x"]))
    assert main(["voice", "--run", str(run)]) == 0
    out = json.loads((run / "voice.json").read_text())
    assert out["failed"] == [1] and out["seconds"] == {"0": 4.0, "2": 6.0}
    step = json.loads((run / "run_log.json").read_text())["steps"][-1]
    assert step["counts"] == {"chapters_voiced": 2, "failed": 1, "audio_seconds": 10.0} and step["notes"]

    monkeypatch.setattr(voice_mod, "voice_all", lambda gw, chs, voices, run_: voice_mod.VoiceResult(
        {1: run_ / "a"}, {1: 3.0}, [0, 2], ["open failed"]))
    with pytest.raises(RuntimeError, match="open"):
        main(["voice", "--run", str(run)])


def test_assemble_cli_writes_newscast_and_chapters(tmp_path, monkeypatch):
    from station.steps import assemble as asm
    from station.steps.rundown import Rundown
    from tests.test_rundown import j
    from tests.test_voice import wav_bytes

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "2026-11-27T09"
    (run / "audio").mkdir(parents=True)
    _scripts(run)
    for i, secs in ((0, 1.0), (2, 2.0)):
        (run / "audio" / f"ch_{i:02d}.wav").write_bytes(wav_bytes(secs))
    (run / "voice.json").write_text(json.dumps({"paths": {"0": str(run / "audio/ch_00.wav"), "2": str(run / "audio/ch_02.wav")},
                                                "seconds": {}, "failed": [1]}))
    (run / "rundown.json").write_text(json.dumps(Rundown((j("hn:2", 0.5),), {"hn:2": 90}, None, (), (), True, False).to_dict()))
    (run / "posts.json").write_text("[]")
    (run / "clusters.json").write_text(json.dumps({"clusters": [], "candidates": []}))
    joined = {}

    def fake_audio(run_, wavs, timings, title):
        joined.update(n=len(wavs), titles=[t["title"] for t in timings])
        (run_ / "newscast.mp3").write_bytes(b"ID3")
        return run_ / "newscast.mp3"

    monkeypatch.setattr(asm, "assemble_audio", fake_audio)
    assert main(["assemble", "--run", str(run)]) == 0
    assert joined == {"n": 4, "titles": ["Open", "Sign-off"]}  # sting + 2 chapters + sting; failed story skipped
    rec = json.loads((run / "newscast.json").read_text())
    assert rec["id"] == "2026-11-27T09" and rec["chapters"][-1]["end_ms"] == 3000 + 2 * 2000
    assert rec["stories"] == [] and rec["counts"]["posts_read_hour"] == 0
    assert json.loads((run / "chapters.json").read_text()) == rec["chapters"]


def test_build_cli_passes_hour(monkeypatch):
    from datetime import datetime

    from station import build as build_mod

    from station import manager

    got = {}
    monkeypatch.setattr(build_mod, "build", lambda hour, **kw: got.update(hour=hour, **kw))
    assert main(["build", "--hour", "2026-11-27T09"]) == 0
    assert got["hour"].strftime("%Y-%m-%dT%H %Z") == "2026-11-27T09 CST"
    assert got["on_failure"] is manager.on_failure  # failures go to the station manager


def test_step_without_run_is_an_error():
    import pytest

    with pytest.raises(SystemExit):
        main(["scrape"])


def test_rundown_cli_adds_recent_unaired_from_db(tmp_path, monkeypatch, make_db):
    from datetime import UTC, datetime

    from station.steps import judge as judge_mod
    from station.store import record_decision, upsert_posts
    from tests.test_rundown import j

    db_path = tmp_path / "s.db"
    monkeypatch.setenv("STATION_DB", str(db_path))
    earlier = j("hn:earlier", 0.7)
    db = make_db("s.db")
    upsert_posts(db, [earlier.post])
    now = datetime.now(UTC).isoformat()
    for qid, ans in earlier.answers.items():
        record_decision(db, earlier.post.id, qid, ans, "jev-1.14.0", now)
    run = tmp_path / "run"
    run.mkdir()
    (run / "judged.json").write_text(json.dumps([j("hn:new", 0.5).to_dict()]))
    monkeypatch.setattr(judge_mod, "judge_seconds", lambda gw, stories: {})
    assert main(["rundown", "--run", str(run)]) == 0
    out = json.loads((run / "rundown.json").read_text())
    assert [s["post"]["id"] for s in out["stories"]] == ["hn:earlier", "hn:new"]
    assert json.loads((run / "run_log.json").read_text())["steps"][-1]["counts"]["carried_over"] == 1


def test_load_sources_falls_back_to_story_post(tmp_path):
    from station.__main__ import load_sources
    from tests.test_rundown import j

    run = tmp_path / "run"
    run.mkdir()
    (run / "posts.json").write_text("[]")
    (run / "clusters.json").write_text(json.dumps({"clusters": [], "candidates": []}))
    old = j("hn:old", 0.6).post
    assert load_sources(run, [old]) == {"hn:old": [old]}


def test_assemble_records_aired_stories(tmp_path, monkeypatch, make_db):
    """Without this, the 3-hour lookback re-airs the same stories every hour (seen live, Nov 26)."""
    from station.steps import assemble as asm
    from station.steps.rundown import Rundown
    from station.steps.write import Chapter, Turn
    from tests.test_rundown import j
    from tests.test_voice import wav_bytes

    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "2026-11-27T09"
    (run / "audio").mkdir(parents=True)
    chs = [Chapter(0, "open", "Open", None, (Turn("host", "o"),)),
           Chapter(1, "lead", "Lead story", "hn:2", (Turn("host", "l"),), "H", "S"),
           Chapter(2, "signoff", "Sign-off", None, (Turn("host", "b"),))]
    (run / "scripts.json").write_text(json.dumps([c.to_dict() for c in chs]))
    for i in range(3):
        (run / "audio" / f"ch_{i:02d}.wav").write_bytes(wav_bytes(1.0))
    (run / "voice.json").write_text(json.dumps({"paths": {str(i): str(run / f"audio/ch_{i:02d}.wav") for i in range(3)},
                                                "seconds": {}, "failed": []}))
    (run / "rundown.json").write_text(json.dumps(Rundown((j("hn:2", 0.6),), {"hn:2": 90}, None, (), (), True, False).to_dict()))
    (run / "posts.json").write_text("[]")
    (run / "clusters.json").write_text(json.dumps({"clusters": [], "candidates": []}))
    monkeypatch.setattr(asm, "assemble_audio", lambda run_, wavs, timings, title: run_ / "newscast.mp3")
    assert main(["assemble", "--run", str(run)]) == 0
    db = make_db("s.db")
    assert db.execute("SELECT post_id, newscast_id, part FROM aired").fetchall() == [("hn:2", "2026-11-27T09", "lead")]


def test_page_cli_writes_site(tmp_path, monkeypatch):
    from tests.test_page import newscast

    monkeypatch.setenv("STATION_RUNS", str(tmp_path / "runs"))
    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "runs" / "2026-11-26T17"
    run.mkdir(parents=True)
    (run / "newscast.json").write_text(json.dumps(newscast()))
    assert main(["page", "--run", str(run)]) == 0
    assert (run / "site/index.html").exists() and (run / "site/h/2026-11-26/1700/index.html").exists()
    assert (run / "site/settings/index.html").exists()
    assert json.loads((run / "run_log.json").read_text())["steps"][-1]["counts"] == {"pages": 6}  # + data/stations.json for the station strip


def test_page_cli_control_room_reflects_saved_log(tmp_path, monkeypatch):
    """Control room is rendered after the page step's own log entry is saved (it showed 0:00 / stale rows)."""
    from station.steps.rundown import Rundown
    from tests.test_page import newscast
    from tests.test_rundown import j

    monkeypatch.setenv("STATION_RUNS", str(tmp_path / "runs"))
    monkeypatch.setenv("STATION_DB", str(tmp_path / "s.db"))
    run = tmp_path / "runs" / "2026-11-26T17"
    run.mkdir(parents=True)
    (run / "newscast.json").write_text(json.dumps(newscast()))
    (run / "rundown.json").write_text(json.dumps(Rundown((j("a", 0.6),), {"a": 90}, None, (), (), True, False).to_dict()))
    (run / "run_log.json").write_text(json.dumps({"run_id": "x", "started_at": "2026-11-26T22:48:02+00:00", "total_seconds": 0,
        "steps": [{"name": "scrape", "tool": "Apify", "status": "done", "seconds": 90.0, "counts": {}, "notes": []}]}))
    assert main(["page", "--run", str(run)]) == 0
    html = (run / "site/control-room/index.html").read_text()
    assert html.count("Build the page") == 1 and "build 1:30" in html


def test_build_cli_skips_outside_broadcast_hours(monkeypatch, capsys):
    from datetime import datetime as real_dt

    import station.__main__ as cli
    from station import build as build_mod

    class Late(real_dt):
        @classmethod
        def now(cls, tz=None):
            return real_dt(2026, 11, 27, 21, 48, tzinfo=tz)  # 9:48 pm Central -> 10 pm newscast

    monkeypatch.setattr(cli, "datetime", Late)
    monkeypatch.setattr(build_mod, "build", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("built")))
    assert main(["build"]) == 0
    assert "outside broadcast hours" in capsys.readouterr().out


def test_build_adds_video_after_the_last_newscast(monkeypatch):
    from station import build as build_mod

    got = []
    monkeypatch.setattr(build_mod, "build", lambda hour, **kw: got.append((hour.hour, kw.get("steps"))))
    main(["build", "--hour", "2026-11-27T19"])
    main(["build", "--hour", "2026-11-27T18"])
    assert got == [(19, [*[s for s in build_mod.STEPS if s != "radio"], "video", "radio"]), (18, None)]


def test_video_day_uses_that_days_last_run(tmp_path, monkeypatch):
    import station.__main__ as cli

    monkeypatch.setenv("STATION_RUNS", str(tmp_path))
    for h in ("2026-11-26T12", "2026-11-26T19", "2026-11-27T07"):
        (tmp_path / h).mkdir()
    seen = []
    monkeypatch.setitem(cli.COMMANDS, "video", lambda run: seen.append(run.name))
    assert main(["video", "--day", "2026-11-26"]) == 0 and seen == ["2026-11-26T19"]


def test_radio_runs_last_and_never_stops_the_build(monkeypatch, tmp_path):  # review I1
    from station import build as build_mod
    import station.__main__ as cli
    import station.radio.run as run_mod

    got = []
    monkeypatch.setattr(build_mod, "build", lambda hour, **kw: got.append(kw.get("steps")))
    main(["build", "--hour", "2026-11-27T19"])
    main(["build", "--hour", "2026-11-27T07"])
    assert got[0][-2:] == ["video", "radio"] and got[1][-3:] == ["table", "picks", "radio"]

    def boom(*a, **k):
        raise KeyError("brief")
    monkeypatch.setattr(run_mod, "run_station", boom)
    run = tmp_path / "2026-11-27T12"
    run.mkdir()
    cli.cmd_radio(run)
    import json
    step = [s for s in json.loads((run / "run_log.json").read_text())["steps"] if s["name"] == "radio"][0]
    assert step["status"] == "done" and any("KeyError" in n for n in step["notes"])
