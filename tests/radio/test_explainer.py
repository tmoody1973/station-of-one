"""Plan B1, Task 6b: the "How the station is programmed" page, built from the running config."""
import re
from dataclasses import replace

from station.config import load_prefs
from station.radio.model import Category, Rotation, load_station
from station.radio.page import EXPLAINER_PATH, render_explainer, render_sampler
from station.radio.program import Block


def page(st=None, counts=None, last=None):
    st = st or load_station("rhythm-lab")
    return render_explainer(st, counts or {c.code: 0 for c in st.rotation.categories}, last, load_prefs())


def test_explainer_numbers_come_from_config():
    st = load_station("rhythm-lab")
    cats = tuple(replace(c, rest_hours=33) if c.code == "M" else c for c in st.rotation.categories)
    html = page(replace(st, rotation=Rotation(cats)), counts={"P": 156, "M": 888, "R": 660, "G": 809, "N": 0})
    row = re.search(r'<tr data-cat="M">.*?</tr>', html, re.S).group(0)
    assert "33" in row and "888" in row and "Rotation" in row
    assert "0.6" in html and "25%" in html and "0.8" in html          # meeting thresholds, churn cap, match bar from the code
    assert "never picks the next song" in html


def test_clock_drawing_matches_slots():
    st = load_station("rhythm-lab")
    html = page(st)
    for clock in st.clocks:
        svg = re.search(rf'<svg[^>]*data-clock="{clock.name}".*?</svg>', html, re.S).group(0)
        drawn = re.findall(r'data-slot="([^"]+)"', svg)
        assert drawn == [s for _, slots in clock.segments for s in slots], clock.name


def test_explainer_escaped_and_linked_from_sampler():
    st = replace(load_station("rhythm-lab"), brief="Beats <b>and</b> soul")
    html = page(st, last="2026-11-30T12:00:00+00:00")
    assert "Beats &lt;b&gt;and&lt;/b&gt; soul" in html and "<b>and</b>" not in html
    assert f"/radio/{st.id}/meeting/index.html" in html
    assert EXPLAINER_PATH == "radio/how-it-works/index.html"
    sampler = render_sampler(st, Block(st.id, "b", "2026-11-27T18:00:00+00:00", []), {}, load_prefs())
    assert f'/radio/{st.id}/how-it-works/index.html' in sampler          # its own explainer (jazz plan Task 6)


def test_burnout_described_only_where_it_runs():  # Rhythm Lab's core gold never burns out
    assert "steps down" not in page(load_station("rhythm-lab"))
    jazz = load_station("uk-jazz")
    assert "steps down" in page(jazz, counts={c.code: 0 for c in jazz.rotation.categories})
