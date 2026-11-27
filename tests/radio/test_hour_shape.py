"""Rhythm Lab plan, Task 4: the show's hour shape and seasons, as soft rules in the scheduler."""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from station.radio.model import load_station
from station.radio.scheduler import schedule_hour
from tests.radio.test_scheduler import add, music, station_db

CHI = ZoneInfo("America/Chicago")
RL = "rhythm-lab"


def at_local(y, m, d, h=12):
    return datetime(y, m, d, h, 0, tzinfo=CHI)


def put(db, cid, cat, **kw):
    opener, closer, tags = kw.pop("opener", 0), kw.pop("closer", 0), kw.pop("tags", "")
    add(db, cid, cat, station=RL, **kw)
    db.execute("UPDATE rotation SET opener = ?, closer = ?, tags = ? WHERE candidate_id = ?", (opener, closer, tags, cid))


def library(db, per_cat=20):
    for cat in "PMRGN":
        for i in range(per_cat):
            put(db, f"{cat}{i:02d}", cat, energy=[1, 2, 3][i % 3], vocal=i % 2)


def energy(db, cid):
    return db.execute("SELECT energy FROM rotation WHERE candidate_id = ?", (cid,)).fetchone()[0]


def test_first_half_lower_energy():
    db = station_db()
    library(db)
    hour = at_local(2026, 11, 20)
    items = music(schedule_hour(load_station(RL), db, hour, news_ms=165000))
    half = (hour + timedelta(minutes=30)).astimezone(UTC).isoformat()
    first = [energy(db, it.candidate_id) for it in items if it.starts_at < half]
    second = [energy(db, it.candidate_id) for it in items if it.starts_at >= half]
    assert max(first) <= 2 and min(second) >= 2


def test_opener_after_news():
    db = station_db()
    library(db)
    put(db, "P_open", "P", energy=2, opener=1)
    put(db, "P_close", "P", energy=2, closer=1)
    items = schedule_hour(load_station(RL), db, at_local(2026, 11, 20), news_ms=165000)
    songs = music(items)
    assert [it.kind for it in items[:2]] == ["id", "news"] and songs[0].candidate_id == "P_open"
    last = songs[-1]
    assert db.execute("SELECT closer FROM rotation WHERE candidate_id = ?", (last.candidate_id,)).fetchone()[0] == 1 \
        or last.category != "P"   # the closer is in P; the last slot prefers it when P is where that slot draws


def test_holiday_window():  # Review Focus 4
    for day, expect in ((at_local(2026, 12, 10), True), (at_local(2027, 1, 5), False), (at_local(2026, 11, 20), False)):
        db = station_db()
        library(db)
        put(db, "Gzz_xmas", "G", energy=2, tags="holiday")   # sorts last: only the holiday slot would pick it first
        items = schedule_hour(load_station(RL), db, day, news_ms=165000)
        half = (day + timedelta(minutes=30)).astimezone(UTC).isoformat()
        after = [it.candidate_id for it in music(items) if it.starts_at >= half]
        assert (after[0] == "Gzz_xmas") is expect, day


def test_soft_rules_relax_in_order():
    db = station_db()
    library(db)
    put(db, "P_open_loud", "P", energy=3, opener=1)     # opener, but outside the first half's energy band
    items = music(schedule_hour(load_station(RL), db, at_local(2026, 11, 20), news_ms=165000))
    assert items[0].candidate_id == "P_open_loud"        # the opener holds longer than the energy band


def test_pairing_never_beats_hard_rules():  # Review Focus 1 (moved from Task 3)
    db = station_db()
    library(db)
    put(db, "P_first", "P", artist="Same Artist", energy=2, opener=1)
    put(db, "G_pair", "G", artist="Same Artist", energy=2)
    db.execute("INSERT INTO library_pairs VALUES ('P_first', 'G_pair', 9)")
    put(db, "G_pair_ok", "G", artist="Other Artist", energy=2)
    db.execute("INSERT INTO library_pairs VALUES ('P_first', 'G_pair_ok', 9)")
    songs = [it.candidate_id for it in music(schedule_hour(load_station(RL), db, at_local(2026, 11, 20), news_ms=165000))]
    assert songs[0] == "P_first" and songs[1] == "G_pair_ok" and "G_pair" not in songs
