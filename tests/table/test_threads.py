from station.store import Post, upsert_posts
from station.table.threads import threads

TZ = "America/Chicago"


def p(pid, kind, title, source="Hacker News", points=0):
    return Post(pid, source, "ai-dev", kind, "someone", title, f"https://ex.com/{pid}", f"text {pid}",
                "2026-11-26T15:00:00Z", {"points": points}, "public")


def add(db, posts, scraped_at="2026-11-26T18:00:00+00:00"):
    upsert_posts(db, posts)
    db.executemany("UPDATE posts SET scraped_at = ? WHERE id = ?", [(scraped_at, x.id) for x in posts])
    db.commit()


def test_groups_comments_under_their_story(make_db):
    db = make_db()
    add(db, [p("hn:1", "story", "Tabs or spaces"), p("hn:2", "story", "Vim vs Emacs"),
             *[p(f"hn:1{i}", "comment", "Comment on: Tabs or spaces") for i in range(7)],
             *[p(f"hn:2{i}", "comment", "Comment on: Vim vs Emacs") for i in range(6)],
             p("reddit:9", "comment", "Comment on: Tabs or spaces", source="Reddit r/x")])  # other source: not ours
    got = {t.story.id: sorted(c.id for c in t.comments) for t in threads(db, "2026-11-26", TZ)}
    assert got == {"hn:1": sorted(f"hn:1{i}" for i in range(7)), "hn:2": sorted(f"hn:2{i}" for i in range(6))}


def test_skips_threads_with_too_few_comments(make_db):
    db = make_db()
    add(db, [p("hn:1", "story", "Quiet"), *[p(f"hn:1{i}", "comment", "Comment on: Quiet") for i in range(5)]])
    assert threads(db, "2026-11-26", TZ) == []


def test_only_that_local_day(make_db):
    db = make_db()
    add(db, [p("hn:1", "story", "Late"), *[p(f"hn:1{i}", "comment", "Comment on: Late") for i in range(6)]],
        scraped_at="2026-11-27T05:59:00+00:00")  # 11:59 pm Central on the 26th
    add(db, [p("hn:2", "story", "Next"), *[p(f"hn:2{i}", "comment", "Comment on: Next") for i in range(6)]],
        scraped_at="2026-11-27T06:01:00+00:00")  # 12:01 am Central on the 27th
    assert [t.story.id for t in threads(db, "2026-11-26", TZ)] == ["hn:1"]


def test_caps_comments_highest_engagement_first(make_db):
    db = make_db()
    add(db, [p("hn:1", "story", "Big"), *[p(f"hn:1{i:02d}", "comment", "Comment on: Big", points=i) for i in range(50)]])
    (t,) = threads(db, "2026-11-26", TZ)
    assert len(t.comments) == 40 and t.comments[0].id == "hn:149"
