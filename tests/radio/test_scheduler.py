"""Plan B1, Task 5: the scheduler fills each hour's clock from the rotation."""
import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from station.radio.model import load_station, open_radio
from station.radio.scheduler import schedule_hour

CHI = ZoneInfo("America/Chicago")
NOON = datetime(2026, 11, 27, 12, 0, tzinfo=CHI)


def station_db():
    db = sqlite3.connect(":memory:")
    open_radio(db)
    return db


def add(db, cid, cat, artist=None, minutes=4.0, energy=2, vocal=1, played_hours_ago=None, added_days_ago=30,
        released="2020-01-01", station="uk-jazz"):
    db.execute("INSERT INTO candidates (id, kind, artist, title, status, song_id, matched_artist, matched_title, release_date, duration_ms) "
               "VALUES (?, 'track', ?, ?, 'resolved', ?, ?, ?, ?, ?)",
               (cid, artist or f"Artist {cid}", cid, f"s-{cid}", artist or f"Artist {cid}", cid, released, int(minutes * 60000)))
    played = (NOON - timedelta(hours=played_hours_ago)).isoformat() if played_hours_ago is not None else None
    db.execute("INSERT INTO rotation (station_id, candidate_id, category, energy, vocal, added_at, last_played_at, source_note) "
               "VALUES (?,?,?,?,?,?,?,?)", (station, cid, cat, energy, vocal, (NOON - timedelta(days=added_days_ago)).isoformat(), played,
                                            "First aired on Rhythm Lab Radio, Nov 2014"))


def stock(db, per_cat=10, minutes=4.0):
    for cat in "ABCRG":
        for i in range(per_cat):
            add(db, f"{cat}{i}", cat, minutes=minutes, released="2025-06-01" if i % 2 else "1999-01-01", vocal=i % 2)
    for i in range(4):
        add(db, f"N{i}", "C", minutes=minutes, added_days_ago=2)   # new C: what N slots draw


def music(items):
    return [it for it in items if it.kind == "song"]


def at(items, minute, second=0):
    return NOON.astimezone(UTC) + timedelta(minutes=minute, seconds=second)


def test_fills_clock_in_order():
    db = station_db()
    stock(db)
    items = schedule_hour(load_station("uk-jazz"), db, NOON)
    kinds = [it.kind for it in items]
    assert kinds[0] == "id" and "news" not in kinds and kinds[-1] == "backsell"   # no newscast length: no news item
    first_half = [it.category for it in music(items) if it.starts_at < at(items, 30).isoformat()]
    second_half = [it.category for it in music(items) if it.starts_at >= at(items, 30).isoformat()]
    assert first_half[:6] == ["A", "G", "C", "B", "R", "A"] and second_half[:5] == ["G", "N", "B", "R", "C"]   # the clock, in order
    assert [it.candidate_id for it in music(items) if it.starts_at >= at(items, 30).isoformat()][1].startswith("N")  # N: new C
    rows = db.execute("SELECT COUNT(*) FROM queue WHERE station_id = 'uk-jazz'").fetchone()[0]
    assert rows == len(items)
    played = db.execute("SELECT plays, last_played_at FROM rotation WHERE candidate_id = ?", (music(items)[0].candidate_id,)).fetchone()
    assert played[0] == 1 and played[1] == music(items)[0].starts_at


def test_rest_times_respected():
    db = station_db()
    stock(db)
    db.execute("UPDATE rotation SET last_played_at = ? WHERE category = 'A'", ((NOON - timedelta(hours=1)).isoformat(),))
    add(db, "Afresh", "A")
    items = schedule_hour(load_station("uk-jazz"), db, NOON)
    a_songs = [it.candidate_id for it in music(items) if it.category == "A"]
    assert a_songs == ["Afresh"]       # the only rested A song; the second A slot falls back to another category


def test_empty_category_falls_back():  # Review Focus 1
    db = station_db()
    for cat in "ABRG":
        for i in range(10):
            add(db, f"{cat}{i}", cat)
    items = schedule_hour(load_station("uk-jazz"), db, NOON)
    assert len(music(items)) >= 11 and all(it.candidate_id for it in music(items))
    assert "C" not in {it.category for it in music(items)}


def test_separation_relaxes_soft_rules_first():  # Review Focus 2
    db = station_db()
    for i in range(12):
        add(db, f"x{i}", "ABCRG"[i % 5], artist=["One", "Two", "Three"][i % 3], vocal=1, released="2025-01-01")
    items = schedule_hour(load_station("uk-jazz"), db, NOON)
    artists = [db.execute("SELECT matched_artist FROM candidates WHERE id = ?", (it.candidate_id,)).fetchone()[0] for it in music(items)]
    assert sorted(artists) == ["One", "Three", "Two"]          # each once: soft rules gave way, artist separation didn't
    assert next(it for it in items if it.kind == "id_tease").starts_at == at(items, 30).isoformat()


def test_fixed_points_start_on_time():  # Review Focus 3
    db = station_db()
    stock(db, minutes=4.0)
    for i in range(3):
        add(db, f"long{i}", "A", minutes=10.0, played_hours_ago=None)
    db.execute("UPDATE rotation SET last_played_at = ? WHERE candidate_id LIKE 'A%'", ((NOON - timedelta(hours=1)).isoformat(),))
    items = schedule_hour(load_station("uk-jazz"), db, NOON)
    assert next(it for it in items if it.kind == "id_tease").starts_at == at(items, 30).isoformat()   # fixed points: :00 and :30
    last = items[-1]
    assert last.kind == "backsell" and datetime.fromisoformat(last.starts_at) + timedelta(milliseconds=last.duration_ms) == at(items, 60)
    for it in items:
        end = datetime.fromisoformat(it.starts_at) + timedelta(milliseconds=it.duration_ms)
        start = datetime.fromisoformat(it.starts_at)
        for fixed in (30, 60):
            point = at(items, fixed)
            assert not (start < point < end), (it.kind, it.candidate_id, fixed)


def test_clock_by_local_hour():  # Review Focus 5: daylight saving
    db = station_db()
    stock(db, per_cat=30)
    st = load_station("uk-jazz")
    first = datetime(2026, 11, 1, 1, 0, tzinfo=CHI)              # 1 am CDT
    second = datetime(2026, 11, 1, 1, 0, fold=1, tzinfo=CHI)     # 1 am CST, an hour later
    a, b = schedule_hour(st, db, first), schedule_hour(st, db, second)
    assert a[0].kind == "id" and a[1].kind == "song"            # overnight clock: no news
    assert a[0].starts_at != b[0].starts_at and len(a) == len(b)
    assert db.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == len(a) + len(b)
    assert schedule_hour(st, db, NOON, news_ms=165000)[1].kind == "news"         # day clock


def test_energy_never_jumps_two():
    db = station_db()
    for cat in "ABCRG":
        for i in range(12):
            add(db, f"{cat}{i}", cat, energy=[1, 3, 2][i % 3])
    items = music(schedule_hour(load_station("uk-jazz"), db, NOON))
    energy = [db.execute("SELECT energy FROM rotation WHERE candidate_id = ?", (it.candidate_id,)).fetchone()[0] for it in items]
    assert all(abs(a - b) <= 1 for a, b in zip(energy, energy[1:])) and len(items) >= 11


def test_an_hour_already_scheduled_is_left_alone():
    db = station_db()
    stock(db)
    st = load_station("uk-jazz")
    first = schedule_hour(st, db, NOON)
    assert schedule_hour(st, db, NOON) == first
    assert db.execute("SELECT MAX(plays) FROM rotation").fetchone()[0] == 1


def test_no_dead_air_after_the_news():  # the :05 segment follows the newscast; only :00 and :30 are fixed
    db = station_db()
    stock(db)
    items = schedule_hour(load_station("uk-jazz"), db, NOON, news_ms=165000)
    news = items[1]
    assert news.kind == "news" and news.duration_ms == 165000
    assert items[2].kind == "song" and items[2].starts_at == at(items, 0, 173).isoformat()


def test_short_songs_fill_the_hour():  # a 9-minute "break" is dead air: extra songs from the block's categories fill it
    db = station_db()
    stock(db, per_cat=20)
    items = schedule_hour(load_station("uk-jazz"), db, NOON, news_ms=165000)
    breaks = [it.duration_ms for it in items if it.kind == "break"]
    assert breaks and max(breaks) <= 25000 + 240000
    assert items[-1].kind == "backsell" and len(music(items)) > 11


def test_an_hour_without_songs_is_refilled():  # review I3: scheduled before the library was loaded
    db = station_db()
    st = load_station("uk-jazz")
    empty = schedule_hour(st, db, NOON)
    assert not music(empty)
    stock(db)
    again = schedule_hour(st, db, NOON)
    assert len(music(again)) >= 11
    assert db.execute("SELECT COUNT(*) FROM queue WHERE kind = 'id' AND starts_at = ?", (again[0].starts_at,)).fetchone()[0] == 1


# --- ONE Jazz: style slots (jazz station plan, Task 3) ---
JAZZ_STYLES = ["contemporary", "uk_jazz", "spiritual_avant", "jazz_funk_fusion", "heritage", "vocal", "latin_brazilian_afro"]


def jazz_song(db, cid, style, artist, minutes=4.5, tags="", cat="P"):
    add(db, cid, cat, artist=artist, minutes=minutes, station="jazz")
    db.execute("UPDATE rotation SET style = ?, tags = ? WHERE candidate_id = ?", (style, tags, cid))


def jazz_library(db, per_style=50, skip=()):
    n = 0
    for style in JAZZ_STYLES:
        if style in skip:
            continue
        for i in range(per_style):
            jazz_song(db, f"{style}-{i}", style, f"Artist {n % 70}")
            n += 1


def styles_of(db, items):
    return [db.execute("SELECT style FROM rotation WHERE candidate_id = ?", (it.candidate_id,)).fetchone()[0] for it in music(items)]


def test_style_slot_draws_that_style():
    db = station_db()
    jazz_library(db)
    items = schedule_hour(load_station("jazz"), db, datetime(2026, 11, 27, 12, 0, tzinfo=CHI), news_ms=165000)   # workday
    from tests.radio.test_model import TARIK_JAZZ_CLOCKS
    got = styles_of(db, items)
    slots = TARIK_JAZZ_CLOCKS["workday"][1]
    assert got[:len(slots)] == slots[:len(got)] and len(got) >= 9      # the clock's 11 in order; leftover time may add one more


def test_style_slot_falls_back():  # jazz plan Review Focus 1
    db = station_db()
    jazz_library(db, skip=("latin_brazilian_afro",))
    items = schedule_hour(load_station("jazz"), db, datetime(2026, 11, 27, 7, 0, tzinfo=CHI), news_ms=165000)      # rise: slot 2 is Latin
    assert styles_of(db, items)[1] == "jazz_funk_fusion"          # Latin's first fallback
    assert all(it.candidate_id for it in music(items))


def test_jazz_rules_hold_over_a_day():  # jazz plan Review Focus 2
    db = station_db()
    jazz_library(db)
    st = load_station("jazz")
    day = []
    for h in range(24):
        hour = datetime(2026, 11, 27, 0, 0, tzinfo=CHI) + timedelta(hours=h)
        items = schedule_hour(st, db, hour, news_ms=165000 if 7 <= h <= 19 else 0)
        kinds = [it.kind for it in items]
        if kinds.count("song") >= 9:
            first, second = [i for i, k in enumerate(kinds) if k == "break"][:2]
            assert kinds[:first].count("song") == 4 and kinds[first:second].count("song") == 4, h
        day += music(items)
    ids = [it.candidate_id for it in day]
    assert len(ids) == len(set(ids))                               # no track twice (72 h rest) in a day
    by_artist = {}
    for it in day:
        artist = db.execute("SELECT matched_artist FROM candidates WHERE id = ?", (it.candidate_id,)).fetchone()[0]
        when = datetime.fromisoformat(it.starts_at)
        assert all(when - prev >= timedelta(hours=4) for prev in by_artist.get(artist, [])), artist
        by_artist.setdefault(artist, []).append(when)


def test_holiday_only_outside_window():  # jazz plan Review Focus 4
    for day, allowed in ((datetime(2026, 12, 10, 12, 0, tzinfo=CHI), True), (datetime(2026, 12, 27, 12, 0, tzinfo=CHI), False)):
        db = station_db()
        jazz_library(db, per_style=3)
        for i in range(20):
            jazz_song(db, f"xmas-{i}", "contemporary", f"Holiday {i}", tags="holiday_only")
        ids = [it.candidate_id for it in music(schedule_hour(load_station("jazz"), db, day, news_ms=165000))]
        assert any(i.startswith("xmas") for i in ids) is allowed, day
