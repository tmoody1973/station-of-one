import json
import zipfile

import pytest

from station.gateway import Response
from station.steps import archive as arc
from station.steps.archive import ARCHIVE_FOLDER, archive, bundle, ensure_folder, upload
from tests.test_rundown import j


class BoxFake:
    """Answers Box calls from a list of (method, path_prefix, Response); records every call."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def request(self, method, provider, path, body=None, headers=None, timeout=120):
        self.calls.append((method, path, body, headers))
        m, prefix, resp = self.script.pop(0)
        assert (m, path.startswith(prefix)) == (method, True), f"unexpected {method} {path}"
        return resp


def r(status, data):
    return Response(status, {}, json.dumps(data).encode())


def make_run(tmp_path):
    run = tmp_path / "2026-11-26T17"
    run.mkdir()
    for name in ["newscast.json", "chapters.json", "scripts.json", "rundown.json", "run_log.json"]:
        (run / name).write_text("{}")
    (run / "newscast.mp3").write_bytes(b"ID3" + b"\0" * 100)
    (run / "judged.json").write_text(json.dumps([j("a", 0.6).to_dict()]))
    return run


def test_bundle_contains_decision_log(tmp_path):
    z = zipfile.ZipFile(bundle(make_run(tmp_path)))
    assert {"newscast.json", "chapters.json", "scripts.json", "rundown.json", "run_log.json", "newscast.mp3",
            "decisions.jsonl"} <= set(z.namelist())
    lines = [json.loads(x) for x in z.read("decisions.jsonl").decode().splitlines()]
    assert lines and all({"post_id", "question_id", "answer", "model"} <= set(x) for x in lines)
    assert {x["question_id"] for x in lines} >= {"matter_week", "private_harm"}


def test_bundle_size_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(arc, "MAX_BYTES", 50)
    with pytest.raises(ValueError, match="50 MiB"):
        bundle(make_run(tmp_path))


def test_multipart_attributes_first(tmp_path):
    f = tmp_path / "x.zip"
    f.write_bytes(b"PK-data")
    gw = BoxFake([("POST", "/upload/files/content", r(201, {"entries": [{"id": "77"}]}))])
    assert upload(gw, "9", f) == "77"
    _, _, body, headers = gw.calls[0]
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert body.index(b'name="attributes"') < body.index(b'name="file"') and b"PK-data" in body
    assert b'"parent": {"id": "9"}' in body and b'"name": "x.zip"' in body


def test_folder_409_reuses_existing():
    gw = BoxFake([("POST", "/2.0/folders", r(409, {"code": "item_name_in_use",
                                                   "context_info": {"conflicts": [{"id": "441"}]}}))])
    assert ensure_folder(gw, "0", ARCHIVE_FOLDER) == "441"


def test_rerun_uploads_new_version(tmp_path):
    gw = BoxFake([("POST", "/2.0/folders", r(201, {"id": "1"})), ("POST", "/2.0/folders", r(201, {"id": "2"})),
                  ("POST", "/upload/files/content", r(409, {"context_info": {"conflicts": {"id": "55"}}})),
                  ("POST", "/upload/files/55/content", r(201, {"entries": [{"id": "55"}]}))])
    assert archive(gw, make_run(tmp_path)) == "55"
    assert gw.calls[1][2] == {"name": "2026-11-26", "parent": {"id": "1"}}  # one folder per day
