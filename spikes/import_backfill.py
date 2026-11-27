"""One-off: bring check 6's backfill (Nov 19 posts scored Nov 26) into the station database so Corrections
has real calls to grade. The stories that would have aired under the rundown rules are recorded as aired
by a newscast named "backfill-2026-11-19" (labeled as backfill on air and on the page).
Run on the Sprite: uv run python spikes/import_backfill.py ~/spikes/check6/backfill.db [2026-11-19]"""
import json
import sqlite3
import sys
from contextlib import closing

from station.config import load_prefs
from station.steps.judge import PER_POST_QUESTIONS, Judged
from station.steps.rundown import select
from station.store import Post, open_db, record_aired, upsert_posts

src = sqlite3.connect(sys.argv[1])
DAY = sys.argv[2] if len(sys.argv) > 2 else "2026-11-19"
NEWSCAST = f"backfill-{DAY}"
posts = {r[0]: Post(r[0], r[1], r[2], "story", r[3], r[4], r[5], r[6] or "", r[9], {"points": r[7], "comments": r[8]}, "public")
         for r in src.execute("SELECT id, source, beat, author, title, url, text, points, comments, created_at FROM posts")}
answers: dict[str, dict] = {}
models: dict[str, str] = {}
decisions = src.execute("SELECT post_id, question_id, answer_type, value, probability, confidence, raw, model, asked_at FROM decisions").fetchall()
for d in decisions:
    answers.setdefault(d[0], {})[d[1]] = json.loads(d[6])
    models[d[0]] = d[7]
judged = [Judged(posts[pid], a, models[pid]) for pid, a in answers.items() if set(PER_POST_QUESTIONS) <= set(a)]
rundown = select(judged, load_prefs().thresholds, first_of_day=False)
with closing(open_db()) as db:
    new = upsert_posts(db, posts.values())
    db.executemany("UPDATE posts SET scraped_at = ? WHERE id = ?", [(p.posted_at, p.id) for p in posts.values()])  # not today's reads
    db.executemany("INSERT OR IGNORE INTO decisions VALUES (?,?,?,?,?,?,?,?,?)", decisions)
    db.commit()
    already = db.execute("SELECT COUNT(*) FROM aired WHERE newscast_id = ?", (NEWSCAST,)).fetchone()[0]
    if not already:
        record_aired(db, NEWSCAST, [(s.post.id, "lead" if i == 0 else "story", s.matter_week)
                                                 for i, s in enumerate(rundown.stories)], f"{DAY}T18:00:00+00:00")  # noon Central
print(f"posts {len(posts)} (new {len(new)}), decisions {len(decisions)}, would have aired {len(rundown.stories)}:")
for s in rundown.stories:
    print(f"  {s.matter_week:.2f}  {s.post.title[:70]}")
