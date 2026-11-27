"""Song tags by Jev (plan B1, Task 2): energy (low, mid, high) and sung vocals, for the scheduler's separation
rules. One batched request per 20 songs, two questions each. Code maps the answers; Jev decides."""
from __future__ import annotations

from station.gateway import GatewayError
from station.steps.judge import MODEL

BATCH = 20
ENERGY = {"low": 1, "mid": 2, "high": 3}
VOCAL_MIN = 0.5


def _questions(i: int) -> dict[str, dict]:
    return {f"energy_{i}": {"type": "choice", "instructions": f"How much energy does the recording `songs[{i}]` have?",
                            "criteria": {"low": "Slow, quiet or meditative", "mid": "Steady, moderate tempo",
                                         "high": "Fast, loud or driving"}},
            f"vocal_{i}": {"type": "noul", "instructions": f"Does the recording `songs[{i}]` have sung vocals?"}}


def tag_songs(gw, items: list[dict]) -> tuple[dict[str, dict], dict[str, dict], str | None, list[str]]:
    """Tags {id: {energy 1-3, vocal 0/1}}, raw answers, model, notes. A failed batch is a note; its songs stay untagged."""
    tags: dict[str, dict] = {}
    raw: dict[str, dict] = {}
    model, notes = None, []
    for start in range(0, len(items), BATCH):
        batch = items[start:start + BATCH]
        state = {"songs": [{k: s.get(k) for k in ("artist", "title", "album", "release_date")} for s in batch]}
        questions = {k: v for i in range(len(batch)) for k, v in _questions(i).items()}
        try:
            resp = gw.json("POST", "typesafe", "/v1/systemone", {"model": MODEL, "state": state, "questions": questions})
            got = {s["id"]: {"energy": resp["answers"][f"energy_{i}"], "vocal": resp["answers"][f"vocal_{i}"]} for i, s in enumerate(batch)}
            mapped = {sid: {"energy": ENERGY[a["energy"]["choice"]], "vocal": int(float(a["vocal"]["noul"]) >= VOCAL_MIN)}
                      for sid, a in got.items()}
        except (GatewayError, KeyError, TypeError, ValueError) as e:
            notes.append(f"tagging failed for {len(batch)} songs: {str(e)[:100]}")
            continue
        model = resp.get("model") or model
        raw.update(got)
        tags.update(mapped)
    return tags, raw, model, notes
