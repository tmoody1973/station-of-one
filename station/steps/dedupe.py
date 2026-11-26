"""Step 2, dedupe: merge posts about the same link; propose same-story pairs for Jev Q5.

Candidate pairs come from title overlap (this run, and this run against recent hours) and from
Pinecone similarity against every earlier post. Pinecone failing leaves link matching (the
spec's cut-order fallback). Only Jev's same-story answer merges anything.

Proven Nov 26: the connector speaks Pinecone's 2026-04 API (a 2026-07 create body was refused
with "missing field spec"), so the index is an integrated index (llama-text-embed-v2, field
"text") used through the Records API: POST /indexes/<name>/records/namespaces/<ns>/upsert
(NDJSON) and .../search. Same story from another outlet scored 0.67, unrelated <= 0.12.
"""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit

from station.store import Post

TRACKING_PARAMS = {"ref", "ref_src", "fbclid", "gclid"}
PINECONE_VERSION = "2026-04"
INDEX = "station-one"
NAMESPACE = "posts"
SIMILAR_MIN = 0.50  # same story, other outlet: 0.67; unrelated: <= 0.12 (Nov 26 probe)
STOPWORDS = {"a", "an", "the"}


@dataclass(frozen=True)
class Cluster:
    primary_id: str
    member_ids: tuple[str, ...]


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = sorted((k, v) for k, v in parse_qsl(parts.query)
                   if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS)
    path = parts.path.rstrip("/")
    return host + path + (f"?{urlencode(query)}" if query else "")


def title_key(title: str) -> str:
    words = re.sub(r"[^\w\s]", " ", title.lower()).split()
    return " ".join(w for w in words if w not in STOPWORDS)


def _engagement(p: Post) -> float:
    return sum(v for v in p.engagement.values() if isinstance(v, (int, float)))


def cluster(posts: list[Post], recent_aired: list[Post],
            recent: list[Post] = ()) -> tuple[list[Cluster], list[tuple[str, str]]]:
    """Group stories by normalized URL. Returns (clusters, same-title candidate pairs for Jev Q5).
    `recent`: stories from earlier hours (aired or still eligible) to compare new stories against."""
    aired_by_url = {normalize_url(a.url): a for a in recent_aired if a.url}
    groups: dict[str, list[Post]] = {}
    order: list[str] = []
    for p in posts:
        key = f"comment:{p.id}" if p.kind == "comment" or not p.url else normalize_url(p.url)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)

    clusters: list[Cluster] = []
    primaries: list[Post] = []
    for key in order:
        members = groups[key]
        aired = aired_by_url.get(key)
        if aired is not None:
            rest = sorted(m.id for m in members if m.id != aired.id)
            clusters.append(Cluster(aired.id, (aired.id, *rest)))
            continue
        primary = min(members, key=lambda m: (-_engagement(m), m.id))
        clusters.append(Cluster(primary.id, (primary.id, *sorted(m.id for m in members if m.id != primary.id))))
        if primary.kind == "story":
            primaries.append(primary)

    pairs: list[tuple[str, str]] = []
    for i, first in enumerate(primaries):
        for second in primaries[i + 1:]:
            if _similar_titles(first.title, second.title):
                pairs.append((first.id, second.id))
    new_ids = {p.id for p in primaries}
    for old in recent:
        for p in primaries:
            if old.id not in new_ids and old.id != p.id and _similar_titles(old.title, p.title):
                pairs.append((old.id, p.id))
    return clusters, pairs


def _similar_titles(a: str, b: str) -> bool:
    """Same normalized title, or at least 3 shared words covering half of the shorter title.
    Only proposes a pair: Jev's same-story question decides the merge."""
    ka, kb = title_key(a), title_key(b)
    if ka and ka == kb:
        return True
    wa, wb = set(ka.split()), set(kb.split())
    shared = wa & wb
    return len(shared) >= 3 and len(shared) >= 0.5 * min(len(wa), len(wb))


def _pine(gw, method: str, path: str, body: bytes, ctype: str):
    r = gw.request(method, "pinecone", path, body,
                   headers={"Content-Type": ctype, "X-Pinecone-Api-Version": PINECONE_VERSION})
    if r.status >= 300:
        from station.gateway import GatewayError

        raise GatewayError("pinecone", r.status, r.body.decode(errors="replace")[:300])
    return r


def embed_text(p: Post) -> str:
    return f"{p.title} {p.text[:300]}".strip()  # title + start only: free-tier embedding budget


def record_id(post_id: str) -> str:
    """Pinecone ids must be ASCII; post ids can hold any URL. The real id rides along as post_id."""
    return hashlib.sha1(post_id.encode()).hexdigest()


def upsert_texts(gw, index: str, namespace: str, items: list[tuple[str, str]]) -> None:
    items = [(pid, text) for pid, text in items if text.strip()]
    for i in range(0, len(items), 96):  # Pinecone's batch limit
        lines = "\n".join(json.dumps({"_id": record_id(pid), "post_id": pid, "text": text})
                          for pid, text in items[i:i + 96])
        _pine(gw, "POST", f"/indexes/{index}/records/namespaces/{namespace}/upsert", lines.encode(),
              "application/x-ndjson")


def similar(gw, index: str, namespace: str, text: str, top_k: int = 5) -> list[tuple[str, float]]:
    body = json.dumps({"query": {"inputs": {"text": text}, "top_k": top_k}, "fields": ["post_id"]}).encode()
    r = _pine(gw, "POST", f"/indexes/{index}/records/namespaces/{namespace}/search", body, "application/json")
    return [(h["fields"]["post_id"], float(h["_score"])) for h in json.loads(r.body)["result"]["hits"]
            if h.get("fields", {}).get("post_id")]


def pinecone_pairs(gw, stories: list[Post]) -> tuple[list[tuple[str, str]], list[str]]:
    """Search earlier posts for each new story, then store the new stories. Returns (pairs, notes).
    ponytail: searches before storing, so same-run semantic pairs are left to the title check."""
    stories = [p for p in stories if embed_text(p)]  # Pinecone rejects a batch holding one empty text
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            hits = list(pool.map(lambda p: similar(gw, INDEX, NAMESPACE, embed_text(p)), stories))
        pairs = [(hid, p.id) for p, found in zip(stories, hits) for hid, score in found
                 if hid != p.id and score >= SIMILAR_MIN]
        upsert_texts(gw, INDEX, NAMESPACE, [(p.id, embed_text(p)) for p in stories])
    except Exception as e:  # any Pinecone trouble: link and title matching still run
        return [], [f"Pinecone unavailable ({type(e).__name__}); link matching only"]
    return pairs, []
