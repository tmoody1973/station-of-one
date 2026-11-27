"""Fit by Jev (plan 2026-11-27-music-station-a, Task 5; PRD "Discovery pipeline" step 4).

Jev rates, as a probability, whether each candidate belongs on the station, given the brief and seed
artists. One batched request per 25 candidates. Code applies the threshold (program.py); Jev decides.
"""
from __future__ import annotations

from station.gateway import GatewayError
from station.radio.extract import Extracted
from station.radio.model import StationConfig
from station.radio.poll import FeedItem
from station.steps.judge import MODEL

BATCH = 25
QUESTION = ("Does the music in `candidates[{i}]` belong on a radio station whose brief is `station.brief` "
            "(its core artists are `station.seed_artists`)?")


def fit_scores(gw, station: StationConfig, cands: list[tuple[str, Extracted, FeedItem]]
               ) -> tuple[dict[str, float], dict[str, dict], str | None, list[str]]:
    """Scores, raw answers, model, notes. A failed batch is a note; earlier batches' scores are kept (review I5)."""
    scores: dict[str, float] = {}
    raw: dict[str, dict] = {}
    model = None
    notes: list[str] = []
    for start in range(0, len(cands), BATCH):
        batch = cands[start:start + BATCH]
        state = {"station": {"brief": station.brief, "seed_artists": station.seeds.get("artists", []),
                             "seed_labels": station.seeds.get("labels", [])},
                 "candidates": [{"artist": e.artist, "title": e.title, "release": e.release, "label": e.label,
                                 "year": e.year, "version": e.version,
                                 "found_in": {"feed": it.feed, "title": it.title, "excerpt": it.excerpt}}
                                for _, e, it in batch]}
        questions = {f"fit_{i}": {"type": "noul", "instructions": QUESTION.format(i=i)} for i in range(len(batch))}
        try:
            resp = gw.json("POST", "typesafe", "/v1/systemone", {"model": MODEL, "state": state, "questions": questions})
            answers = {cid: resp["answers"][f"fit_{i}"] for i, (cid, _, _) in enumerate(batch)}
            batch_scores = {cid: float(a["noul"]) for cid, a in answers.items()}
        except (GatewayError, KeyError, TypeError, ValueError) as e:
            notes.append(f"fit scoring failed for {len(batch)} candidates: {str(e)[:100]}")
            continue
        model = resp.get("model") or model
        raw.update(answers)
        scores.update(batch_scores)
    return scores, raw, model, notes
