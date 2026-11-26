"""Step 10, archive: zip the hour's records and upload them to Box through the connector gateway.

Proven 2026-11-26: POST /2.0/folders → 201, or 409 naming the existing folder in
context_info.conflicts; POST /upload/files/content (multipart, attributes part first) → 201.
Layout: "Station of One archive"/<YYYY-MM-DD>/<run id>.zip. A re-run (station manager retry) gets
409 for the same file name and uploads a new version instead.
"""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from station.gateway import GatewayError

ARCHIVE_FOLDER = "Station of One archive"
MAX_BYTES = 50 * 1024 * 1024  # Box's limit for one upload request
FILES = ["newscast.json", "chapters.json", "scripts.json", "rundown.json", "run_log.json", "newscast.mp3"]


def _decision_lines(run: Path) -> str:
    """Every Jev answer this hour, one JSON object per line (from judged.json)."""
    if not (run / "judged.json").exists():
        return ""
    lines = []
    for d in json.loads((run / "judged.json").read_text()):
        for qid, answer in d["answers"].items():
            lines.append(json.dumps({"post_id": d["post"]["id"], "question_id": qid, "answer": answer,
                                     "model": d.get("model")}))
    return "\n".join(lines) + "\n"


def bundle(run: Path, files: list[str] = FILES) -> Path:
    out = run / f"{run.name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            if (run / name).exists():
                z.write(run / name, name)
        z.writestr("decisions.jsonl", _decision_lines(run))
    if out.stat().st_size > MAX_BYTES:
        raise ValueError(f"archive bundle is {out.stat().st_size:,} bytes; Box allows 50 MiB per upload")
    return out


def _check(r, ok=(200, 201)):
    if r.status not in ok:
        raise GatewayError("box", r.status, r.body.decode(errors="replace")[:300])
    return json.loads(r.body)


def _conflict_id(body: bytes) -> str:
    c = json.loads(body)["context_info"]["conflicts"]
    return (c[0] if isinstance(c, list) else c)["id"]  # folders: list; files: one object


def ensure_folder(gw, parent_id: str, name: str) -> str:
    r = gw.request("POST", "box", "/2.0/folders", {"name": name, "parent": {"id": parent_id}})
    return _conflict_id(r.body) if r.status == 409 else _check(r)["id"]


def _multipart(attributes: dict, filename: str, data: bytes) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="attributes"\r\n\r\n{json.dumps(attributes)}\r\n'
            f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{b}--\r\n".encode()
    return body, f"multipart/form-data; boundary={b}"


def upload(gw, folder_id: str, path: Path) -> str:
    body, ctype = _multipart({"name": path.name, "parent": {"id": folder_id}}, path.name, path.read_bytes())
    r = gw.request("POST", "box", "/upload/files/content", body, headers={"Content-Type": ctype})
    if r.status == 409:  # same name already archived: upload a new version
        fid = _conflict_id(r.body)
        body, ctype = _multipart({"name": path.name}, path.name, path.read_bytes())
        r = gw.request("POST", "box", f"/upload/files/{fid}/content", body, headers={"Content-Type": ctype})
    return _check(r)["entries"][0]["id"]


def archive(gw, run: Path, files: list[str] = FILES) -> str:
    top = ensure_folder(gw, "0", ARCHIVE_FOLDER)
    day = ensure_folder(gw, top, run.name[:10])
    return upload(gw, day, bundle(run, files))
