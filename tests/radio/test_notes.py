"""Rhythm Lab plan, Task 5: Tarik's show notes stay private; the public line is "First aired on ..."."""
import json
from datetime import date

from station.config import load_prefs
from station.radio.library import library_track, seed_rotation
from station.radio.model import load_station
from station.radio.notes import import_notes
from station.radio.page import render_sampler
from station.radio.program import Block
from tests.radio.test_library_rotation import lib

SECRET_URL = "https://docs.google.com/document/d/SECRET123/edit"
SECRET_NOTE = "PRIVATE PREP NOTE pasted from a press release"


def notes_file(tmp_path):
    p = tmp_path / "notes.json"
    p.write_text(json.dumps([{"artist": "Flying Lotus", "in_library": True,
                              "notes": [{"date": "2014-11-21", "source": SECRET_URL, "note": SECRET_NOTE},
                                        {"date": "2019-05-03", "source": "5-3-19 playlist", "note": "Second note"}]},
                             {"artist": "Nobody", "in_library": False, "notes": []}]))
    return p


def test_notes_imported_privately(tmp_path):
    db = lib({"track_id": "t1"})
    assert import_notes(db, notes_file(tmp_path)) == 2
    rows = db.execute("SELECT artist, date, source, note FROM artist_notes ORDER BY date").fetchall()
    assert rows[0] == ("Flying Lotus", "2014-11-21", SECRET_URL, SECRET_NOTE)
    assert import_notes(db, notes_file(tmp_path)) == 2 and db.execute("SELECT COUNT(*) FROM artist_notes").fetchone()[0] == 2


def test_no_private_fields_published(tmp_path):  # Review Focus 2
    db = lib({"track_id": "t1"})
    import_notes(db, notes_file(tmp_path))
    seed_rotation(db, load_station("rhythm-lab"))
    t = library_track(db, "lib:t1", date(2026, 11, 27))
    assert t["note"] == "First aired on Rhythm Lab Radio, Nov 2014" and t["source_url"] == ""
    html = render_sampler(load_station("rhythm-lab"), Block("rhythm-lab", "b", "2026-11-27T18:00:00+00:00", [t]), {}, load_prefs())
    public = html + json.dumps(t)
    for leak in ("docs.google.com", "SECRET123", "drive_url", SECRET_NOTE, "Second note", "playlist"):
        assert leak not in public, leak
    assert "First aired on Rhythm Lab Radio, Nov 2014" in html and 'href=""' not in html
