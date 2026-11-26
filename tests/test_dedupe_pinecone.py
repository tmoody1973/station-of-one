import json

from station.gateway import GatewayError, Response
from station.steps.dedupe import PINECONE_VERSION, cluster, pinecone_pairs, similar, upsert_texts
from station.steps.judge import judge_all
from station.store import Post
from tests.fakes import FakeGateway
from tests.test_judge import FIVE, jev


def story(pid, title, url=None):
    return Post(pid, "S", "arts-culture", "story", None, title, url or f"https://ex.com/{pid}", "Body text.",
                "2026-11-26T22:00:00Z", {}, "public")


class PineFake:
    def __init__(self, hits=None, fail=False):
        self.hits, self.fail, self.calls = hits or [], fail, []

    def request(self, method, provider, path, body=None, headers=None, timeout=120):
        self.calls.append((method, provider, path, body, headers))
        if self.fail:
            raise GatewayError("pinecone", 503, "down")
        if path.endswith("/search"):
            return Response(200, {}, json.dumps({"result": {"hits": [{"_id": i, "_score": s} for i, s in self.hits]}}).encode())
        return Response(201, {}, b"{}")


def test_high_similarity_becomes_candidate():
    gw = PineFake(hits=[("old:1", 0.67), ("new:2", 0.99), ("other:3", 0.2)])
    pairs, notes = pinecone_pairs(gw, [story("new:2", "Hoor Al Qasimi to curate 2028 Venice Biennale")])
    assert pairs == [("old:1", "new:2")] and notes == []  # itself and the 0.2 match are ignored
    upsert = [c for c in gw.calls if c[2].endswith("/upsert")][0]
    assert json.loads(upsert[3].decode().splitlines()[0])["_id"] == "new:2"  # stored after searching


def test_sends_version_header():
    gw = PineFake()
    similar(gw, "station-one", "posts", "text")
    upsert_texts(gw, "station-one", "posts", [("a", "text")])
    assert all(c[4]["X-Pinecone-Api-Version"] == PINECONE_VERSION for c in gw.calls)
    assert gw.calls[0][2] == "/indexes/station-one/records/namespaces/posts/search"


def test_pinecone_failure_falls_back_to_link_matching():
    pairs, notes = pinecone_pairs(PineFake(fail=True), [story("new:2", "x")])
    assert pairs == [] and "link matching" in notes[0]


def test_cross_hour_title_overlap_pairs():
    old = story("old:1", "Hoor Al Qasimi named curator of the 2028 Venice Biennale", "https://a.com/x")
    new = story("new:2", "Hoor Al Qasimi to curate the 2028 Venice Biennale", "https://b.com/y")
    _, pairs = cluster([new], [], recent=[old])
    assert pairs == [("old:1", "new:2")]


def test_judge_asks_about_earlier_hour_post(make_db):
    old, new = story("old:1", "Venice Biennale curator named"), story("new:2", "Venice Biennale curator")
    answers = {**FIVE, "same_story_0": {"type": "noul", "noul": 0.93}}
    gw = FakeGateway({("POST", "typesafe", "/v1/systemone"): [jev(answers)]})
    (j,) = judge_all(gw, make_db(), [new], candidates=[("old:1", "new:2")], known=[old])
    assert gw.calls[0][3]["state"]["earlier_posts"][0]["title"] == old.title and j.same_as == "old:1"


def test_posts_with_no_text_are_skipped():  # Pinecone rejects a whole batch with one empty record
    empty = Post("e:1", "S", "ai-dev", "story", None, "", "https://ex.com/e", "", "2026-11-26T22:00:00Z", {}, "public")
    gw = PineFake()
    pairs, notes = pinecone_pairs(gw, [empty, story("new:2", "Real title")])
    assert notes == [] and len([c for c in gw.calls if c[2].endswith("/search")]) == 1
    upserted = [json.loads(x)["_id"] for c in gw.calls if c[2].endswith("/upsert") for x in c[3].decode().splitlines()]
    assert upserted == ["new:2"]
