"""Step 2, dedupe: merge posts about the same link; flag same-title pairs for Jev Q5.

Friday version: link matching only (the spec's cut-order fallback). Task 16 adds Pinecone
similarity as a second source of candidate pairs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit

from station.store import Post

TRACKING_PARAMS = {"ref", "ref_src", "fbclid", "gclid"}
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


def cluster(posts: list[Post], recent_aired: list[Post]) -> tuple[list[Cluster], list[tuple[str, str]]]:
    """Group stories by normalized URL. Returns (clusters, same-title candidate pairs for Jev Q5)."""
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
