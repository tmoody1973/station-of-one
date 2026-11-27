"""Rhythm Lab plan, Task 3: tracks Tarik played back to back."""
import sqlite3
from pathlib import Path

from station.radio.pairs import import_pairs, pair_bonus

PLAYS = Path("tests/fixtures/rhythm_lab/rhythm_lab_plays.csv")


def test_pairs_only_within_a_block():
    db = sqlite3.connect(":memory:")
    assert import_pairs(db, PLAYS) == 2
    pairs = dict(((a, b), n) for a, b, n in db.execute("SELECT a, b, count FROM library_pairs"))
    # A→B twice (S1, S2; the duplicate file doesn't count). B→C: new block. C→D: new hour. D→E: yes.
    # E→F and F→G: F aired inside a guest mix, so neither pair is Tarik's sequencing.
    assert pairs == {("RLTA", "RLTB"): 2, ("RLTD", "RLTE"): 1}
    assert import_pairs(db, PLAYS) == 2   # idempotent: counts are rebuilt, not doubled
    assert db.execute("SELECT count FROM library_pairs WHERE a = 'RLTA'").fetchone()[0] == 2


def test_pair_bonus_capped():
    db = sqlite3.connect(":memory:")
    import_pairs(db, PLAYS)
    db.execute("INSERT OR REPLACE INTO library_pairs VALUES ('RLTX', 'RLTY', 7)")
    assert pair_bonus(db, "RLTA", "RLTB") == 0.2
    assert pair_bonus(db, "lib:RLTA", "lib:RLTB") == 0.2      # the scheduler's song ids
    assert pair_bonus(db, "RLTX", "RLTY") == 0.3                # capped
    assert pair_bonus(db, "RLTB", "RLTA") == 0.0                # order matters
    assert pair_bonus(db, None, "RLTB") == 0.0                  # first song of the hour


def test_a_station_without_a_library_gets_no_bonus():  # ONE Jazz has no plays file
    from station.radio.model import open_radio
    db = sqlite3.connect(":memory:")
    open_radio(db)
    assert pair_bonus(db, "c1", "c2") == 0.0
