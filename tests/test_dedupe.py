from station.steps.dedupe import Cluster, cluster, normalize_url, title_key
from station.store import Post


def p(pid, url, title="Some story", points=0, comments=0, kind="story", source="Hacker News"):
    return Post(pid, source, "ai-dev", kind, "u", title, url, "", "2026-11-27T14:00:00Z",
                {"points": points, "comments": comments}, "public")


def test_normalize_url_drops_tracking_and_noise():
    a = normalize_url("https://www.Example.com/news/story/?utm_source=x&id=7#top")
    assert a == normalize_url("http://example.com/news/story?id=7&utm_medium=y")
    assert a == "example.com/news/story?id=7"


def test_same_url_with_utm_merges():
    clusters, pairs = cluster([p("rss:1", "https://ex.com/a?utm_source=rss"), p("hn:2", "https://ex.com/a")], [])
    assert clusters == [Cluster("hn:2", ("hn:2", "rss:1"))] and pairs == []


def test_hn_discussion_and_article_merge_by_linked_url():
    hn = p("hn:9", "https://blog.ex.com/post", points=200, comments=50)
    feed = p("rss:blog", "https://blog.ex.com/post/", source="Ex Blog")
    clusters, _ = cluster([feed, hn], [])
    assert len(clusters) == 1 and clusters[0].primary_id == "hn:9"


def test_same_title_different_url_is_candidate_not_merge():
    a = p("hn:1", "https://a.com/x", title="OpenAI ships a thing!")
    b = p("reddit:2", "https://b.com/y", title="openai ships a thing")
    clusters, pairs = cluster([a, b], [])
    assert len(clusters) == 2 and pairs == [("hn:1", "reddit:2")]


def test_title_key():
    assert title_key("The  OpenAI ships: a Thing!") == "openai ships thing"


def test_primary_is_highest_engagement():
    low, high = p("rss:1", "https://ex.com/a"), p("reddit:3", "https://ex.com/a", points=40, comments=9)
    assert cluster([low, high], [])[0][0].primary_id == "reddit:3"


def test_already_aired_url_clusters_under_aired_post():
    aired = p("hn:old", "https://ex.com/a")
    clusters, _ = cluster([p("rss:new", "https://ex.com/a")], [aired])
    assert clusters == [Cluster("hn:old", ("hn:old", "rss:new"))]


def test_comments_pass_through_as_singletons():
    c = p("reddit:c1", "https://www.reddit.com/r/x/comments/1/comment/c1/", kind="comment")
    clusters, pairs = cluster([c], [])
    assert clusters == [Cluster("reddit:c1", ("reddit:c1",))] and pairs == []
