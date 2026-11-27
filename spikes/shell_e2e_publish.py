"""Publish a test copy of the site to _checks/shell-e2e/ for the shell's end-to-end tests (run on the Sprite
from a checkout of the branch). Pages are rendered from real data; links between pages and /shell.js point
into the test folder; audio and images stay at the bucket root, where the real files are."""
import json
import re
import sys
from pathlib import Path

from station.config import load_prefs
from station.gateway import Gateway
from station.radio.model import load_station
from station.radio.page import render_sampler
from station.radio.program import Block
from station.steps import page as pg
from station.steps.publish import put_object
from station.steps.stations import stations_json

PREFIX = "/_checks/shell-e2e"
run = Path(sys.argv[1])
prefs, gw = load_prefs(), Gateway()
n = json.loads((run / "newscast.json").read_text())
extras = json.loads((run / "stories.json").read_text()) if (run / "stories.json").exists() else None
pages = {"index.html": pg.render_front(n, [n], prefs, extras=extras), "settings/index.html": pg.render_settings(prefs, {})}
story_key = pg.story_path(n["id"], 0, n["stories"][0]["headline"])
pages[story_key] = pg.render_story(n, n["stories"][0], (extras or {}).get(n["stories"][0]["id"]), prefs)
latest = json.loads(Path("data/radio/uk-jazz/latest.json").read_text())
b = latest["block"]
pages["radio/uk-jazz/index.html"] = render_sampler(load_station("uk-jazz"), Block(b["station_id"], b["block_id"], b["built_at"], b["tracks"]),
                                                   latest["counts"], prefs)
pages["old/index.html"] = '<!doctype html><title>an older page</title><main><p>an older page, built before the shell</p><audio src="/x.mp3"></audio></main>'
pages["broken/index.html"] = '<!doctype html><title>no main here</title><p>deliberately has no main element</p>'


def localize(html: str) -> str:
    html = re.sub(r'href="/([^"]*\.html(?:#[^"]*)?)"', rf'href="{PREFIX}/\1"', html)
    html = html.replace('data-src="/data/stations.json"', f'data-src="{PREFIX}/data/stations.json"')
    return html.replace('src="/shell.js"', f'src="{PREFIX}/shell.js"')


for key, html in pages.items():
    put_object(gw, prefs.hosting.bucket, f"_checks/shell-e2e/{key}", localize(html).encode(), "text/html; charset=utf-8", "max-age=0")
    print(f"{PREFIX}/{key}")
put_object(gw, prefs.hosting.bucket, "_checks/shell-e2e/shell.js", Path("templates/shell.js").read_bytes(), "text/javascript", "max-age=0")
strip = stations_json(prefs, n)
for st in strip["stations"]:
    st["page"] = PREFIX + st["page"]
put_object(gw, prefs.hosting.bucket, "_checks/shell-e2e/data/stations.json", json.dumps(strip).encode(), "application/json", "max-age=0")
print("story page:", f"{PREFIX}/{story_key}")
