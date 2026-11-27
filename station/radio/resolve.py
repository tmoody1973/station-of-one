"""Resolver (plan 2026-11-27-music-station-a, Task 6; PRD "Resolve").

Matches an extracted track or release to the Apple Music catalog (Apple Music API through the
station's custom_api connector). Score = artist 0.4 + title 0.4 + year/album 0.2, minus 0.3 for an
unrequested version (remaster, live, edit...). Below MATCH_MIN the candidate is held, not programmed.
A release (album review) gives the track the item names, else the title track, else track one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import quote

from station.gateway import GatewayError
from station.radio.extract import Extracted
from station.radio.model import normalize

MATCH_MIN = 0.8
VERSION_WORDS = ("remaster", "live", "edit", "clean", "instrumental", "karaoke", "acoustic", "demo", "remix", "sped up")
FEAT = re.compile(r"\s*[\(\[](feat\.?|featuring|with)\b[^\)\]]*[\)\]]", re.I)


class AppleRefused(Exception):
    pass


@dataclass(frozen=True)
class Match:
    song_id: str
    artist: str
    title: str
    album: str
    duration_ms: int
    isrc: str
    release_date: str
    preview_url: str
    apple_url: str
    artwork_url: str
    confidence: float


def _sim(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    if ta <= tb or tb <= ta:  # "Nubya Garcia" vs "Nubya Garcia & Esperanza Spalding"
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def _bare(title: str) -> str:
    """Song name without '(feat. ...)' and without bracketed version words, for the title comparison."""
    t = FEAT.sub("", title or "")
    return re.sub(r"\s*[\(\[][^\)\]]*[\)\]]|\s+-\s+.*$", "", t).strip() or t


def match_score(want: Extracted, attrs: dict) -> float:
    artist = _sim(want.artist, attrs.get("artistName", ""))
    title = _sim(want.title or want.release, _bare(attrs.get("name", "")))
    year = (attrs.get("releaseDate") or "")[:4]
    if want.year and year:
        extra = 0.2 if str(want.year) == year else 0.0
    elif want.release and attrs.get("albumName"):
        extra = 0.2 if _sim(want.release, attrs["albumName"]) > 0.8 else 0.0
    else:
        extra = 0.2  # nothing to disagree with
    asked = normalize(f"{want.title} {want.version}")
    name = normalize(attrs.get("name", ""))
    penalty = 0.3 if any(w in name and w not in asked for w in VERSION_WORDS) else 0.0
    # the version the item asked for ("Live at the Barbican", "VIP") beats the plain take
    bonus = 0.05 if want.version and normalize(want.version) in name else 0.0
    return round(0.4 * artist + 0.4 * title + extra - penalty + bonus, 3)


def _match(song: dict, confidence: float) -> Match:
    a = song.get("attributes", {})
    art = (a.get("artwork") or {}).get("url", "").replace("{w}", "300").replace("{h}", "300")
    return Match(song["id"], a.get("artistName", ""), a.get("name", ""), a.get("albumName", ""),
                 int(a.get("durationInMillis") or 0), a.get("isrc", ""), a.get("releaseDate", ""),
                 ((a.get("previews") or [{}])[0]).get("url", ""), a.get("url", ""), art, confidence)


def _get(gw, conn: str, path: str) -> dict:
    try:
        return gw.json("GET", conn, path)
    except GatewayError as e:
        if e.status in (401, 403):
            raise AppleRefused(f"Apple Music refused the developer token ({e.status}); re-sign it with "
                               "scripts/apple_check.sh and paste it into the Apple Music connector") from e
        raise


def resolve(gw, conn: str, want: Extracted, storefront: str, excerpt: str = "") -> tuple[list[Match], str]:
    if want.kind == "release":
        return _resolve_release(gw, conn, want, storefront, excerpt)
    term = quote(f"{want.artist} {want.title}")
    songs = _get(gw, conn, f"/v1/catalog/{storefront}/search?term={term}&types=songs&limit=10") \
        .get("results", {}).get("songs", {}).get("data", [])
    if not songs:
        return [], "not_on_apple"
    # best score first; among equals the earliest release (the original, not a later compilation)
    scored = sorted(((match_score(want, s.get("attributes", {})), s) for s in songs),
                    key=lambda x: (-x[0], x[1].get("attributes", {}).get("releaseDate") or "9999"))
    best, top = scored[0]
    return ([_match(top, best)], "resolved") if best >= MATCH_MIN else ([], "held")


def _resolve_release(gw, conn: str, want: Extracted, storefront: str, excerpt: str) -> tuple[list[Match], str]:
    term = quote(f"{want.artist} {want.release}")
    albums = _get(gw, conn, f"/v1/catalog/{storefront}/search?term={term}&types=albums&limit=5") \
        .get("results", {}).get("albums", {}).get("data", [])
    if not albums:
        return [], "not_on_apple"
    probe = Extracted("track", want.artist, want.release, want.release, want.label, want.year, want.version)
    scored = sorted(((match_score(probe, {**a.get("attributes", {}), "albumName": a.get("attributes", {}).get("name", "")}), a)
                     for a in albums), key=lambda x: -x[0])
    best, album = scored[0]
    if best < MATCH_MIN:
        return [], "held"
    tracks = _get(gw, conn, f"/v1/catalog/{storefront}/albums/{album['id']}/tracks").get("data", [])
    if not tracks:
        return [], "not_on_apple"
    text = normalize(excerpt)
    named = [t for t in tracks if (n := normalize(_bare(t.get("attributes", {}).get("name", "")))) and f" {n} " in f" {text} "]
    title_track = [t for t in tracks if normalize(_bare(t.get("attributes", {}).get("name", ""))) == normalize(want.release)]
    chosen = (named or title_track or tracks[:1])[:2]
    return [_match(t, best) for t in chosen], "resolved"
