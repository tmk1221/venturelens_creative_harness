"""T10 acceptance test: two projects open at once, cut op conflict -> 409, Range requests
-> 206, SSE resumes from Last-Event-ID, spend refused without authorisation, path traversal
rejected, OpenAPI generation runs. Drives the FastAPI app in-process with `TestClient`
against fake node types/workers, exactly like post_core's own CLI acceptance test."""
from __future__ import annotations

import json
import stat
import subprocess
import sys
import textwrap
import time

import pytest

from post_api.openapi import main as openapi_main


@pytest.fixture
def ok_worker_cmd(tmp_path):
    out_path = tmp_path / "out.bin"
    script = tmp_path / "worker.py"
    script.write_text(textwrap.dedent(f"""
        import hashlib, json
        out = {str(out_path)!r}
        with open(out, "w") as f:
            f.write("payload")
        sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
        print("##POST " + json.dumps({{"kind": "cost", "amount": 1.5, "unit": "usd"}}), flush=True)
        print("##POST " + json.dumps({{"kind": "artifact", "path": out, "role": "output", "sha256": sha}}), flush=True)
        print("##POST " + json.dumps({{"kind": "result", "ok": True, "detail": "done"}}), flush=True)
    """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [sys.executable, str(script)]


def _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path):
    r = client.post(f"/api/projects/{pid}/sources", json={"path": str(lavfi_clip), "role": "a_roll"})
    assert r.status_code == 200, r.text
    body = r.json()
    shoot_id, source_id, sync_group_id = body["shoot_id"], body["source_id"], body["sync_group_id"]

    transcript_path = tmp_path / "t.json"
    transcript_path.write_text(json.dumps([
        {"text": "hello", "start": 0.0, "end": 0.2},
        {"text": "there", "start": 0.2, "end": 0.4},
        {"text": "world", "start": 0.4, "end": 0.6},
    ]))
    r = client.post(f"/api/projects/{pid}/ingest/import-transcript", json={
        "shoot": shoot_id, "sync_group": sync_group_id, "path": str(transcript_path), "format": "json",
    })
    assert r.status_code == 200, r.text
    return shoot_id, source_id, sync_group_id, r.json()["transcript_id"]


def test_two_projects_open_at_once(client, tmp_path):
    r1 = client.post("/api/projects", json={"root": str(tmp_path / "a"), "name": "a"})
    r2 = client.post("/api/projects", json={"root": str(tmp_path / "b"), "name": "b"})
    assert r1.status_code == 200 and r2.status_code == 200
    pid1, pid2 = r1.json()["id"], r2.json()["id"]
    assert pid1 != pid2

    listing = client.get("/api/projects").json()["projects"]
    assert {p["id"] for p in listing} >= {pid1, pid2}

    show1 = client.get(f"/api/projects/{pid1}").json()
    show2 = client.get(f"/api/projects/{pid2}").json()
    assert show1["name"] == "a" and show2["name"] == "b"


def test_cut_ops_conflict_and_media_range(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    _shoot_id, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)

    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    assert r.status_code == 200, r.text
    cut_id = r.json()["cut_id"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    assert r.status_code == 200
    cut = r.json()
    revision = cut["revision"]
    passage_id = cut["cut"]["passages"][0]["id"]

    # stale expected_rev -> 409
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "set_trim", "args": {"passage_id": passage_id, "head": 0.05, "tail": 0.0},
        "expected_rev": revision + 5,
    })
    assert r.status_code == 409, r.text
    assert r.json()["current_revision"] == revision

    # correct expected_rev -> ok, revision bumps
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "set_trim", "args": {"passage_id": passage_id, "head": 0.05, "tail": 0.0},
        "expected_rev": revision,
    })
    assert r.status_code == 200, r.text
    assert r.json()["revision"] == revision + 1

    # media proxy: build it, then request a byte-range slice -> 206 with correct bytes
    r = client.post(f"/api/projects/{pid}/ingest/proxy", json={"shoot": _shoot_id, "source_id": source_id})
    assert r.status_code == 200, r.text
    proxy_path = r.json()["proxy_path"]
    full_bytes = open(proxy_path, "rb").read()

    r = client.get(f"/api/projects/{pid}/media/{source_id}/proxy", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206, r.text
    assert r.content == full_bytes[:10]
    assert r.headers["Content-Range"] == f"bytes 0-9/{len(full_bytes)}"

    # T22: audio proxy (AAC .m4a), same build-then-Range-slice shape as the video proxy above.
    r = client.post(f"/api/projects/{pid}/ingest/audio", json={"shoot": _shoot_id, "source_id": source_id})
    assert r.status_code == 200, r.text
    audio_path = r.json()["audio_proxy_path"]
    full_audio_bytes = open(audio_path, "rb").read()

    r = client.get(f"/api/projects/{pid}/media/{source_id}/audio", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206, r.text
    assert r.content == full_audio_bytes[:10]
    assert r.headers["Content-Range"] == f"bytes 0-9/{len(full_audio_bytes)}"

    # the timeline carries `audio_source_id` per segment -- with no dedicated audio recorder
    # in this fixture's sync group, it falls back to the a_roll camera (the same source).
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}/timeline")
    assert r.status_code == 200, r.text
    assert all(seg["audio_source_id"] == source_id for seg in r.json())


def test_run_refused_then_authorised_and_runs(client, project, ok_worker_cmd):
    pid = project["id"]
    graph = {"nodes": [{"id": "g1", "type_id": "fake.api_spend", "params": {"text": "x", "cmd": ok_worker_cmd}}], "edges": []}
    r = client.post(f"/api/projects/{pid}/workflows", json={"recipe": "e2e", "graph": graph})
    assert r.status_code == 200, r.text
    workflow_id = r.json()["workflow_id"]

    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}/plan")
    assert r.status_code == 200
    assert r.json()["plan"]["needs_authorization"] == ["g1"]

    r = client.post(f"/api/projects/{pid}/workflows/{workflow_id}/run", json={})
    assert r.status_code == 402, r.text
    assert r.json()["reason"] == "spend_not_authorized"

    r = client.put(f"/api/projects/{pid}/budgets/b1", json={"cap": 10.0, "unit": "usd"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/projects/{pid}/workflows/{workflow_id}/run", json={"budget": "b1", "by": "tester"})
    assert r.status_code == 200, r.text
    job_ids = r.json()["job_ids"]
    assert len(job_ids) == 1

    deadline = time.monotonic() + 10
    state = None
    while time.monotonic() < deadline:
        r = client.get(f"/api/projects/{pid}/queue/{job_ids[0]}")
        state = r.json()["job"]["state"]
        if state in ("ok", "failed"):
            break
        time.sleep(0.2)
    assert state == "ok", state


def test_path_traversal_rejected(client, project):
    pid = project["id"]
    r = client.delete(f"/api/projects/{pid}/approvals/%2e%2e")
    assert r.status_code == 400, r.text
    r = client.get(f"/api/projects/{pid}/media/..etc/proxy")
    assert r.status_code == 400, r.text
    r = client.get(f"/api/projects/{pid}/assets/%2e%2e")
    assert r.status_code == 400, r.text


def _collect_sse_ids(base_url, path, headers, want, hard_timeout):
    """Read up to `want` SSE `id:` lines from a *real* HTTP connection (see `live_server`
    fixture docstring for why this can't go through the in-process `TestClient`), bounded
    by `hard_timeout` wall-clock seconds via a real socket read timeout."""
    import httpx

    ids: list[int] = []
    status = None
    try:
        with httpx.Client(base_url=base_url, timeout=hard_timeout) as raw_client:
            with raw_client.stream("GET", path, headers=headers) as resp:
                status = resp.status_code
                for line in resp.iter_lines():
                    if line.startswith("id: "):
                        ids.append(int(line[4:]))
                    if len(ids) >= want:
                        break
    except httpx.ReadTimeout:
        pass
    return status, ids


def test_sse_resumes_from_last_event_id(live_server, ok_worker_cmd, tmp_path):
    import httpx

    with httpx.Client(base_url=live_server) as setup:
        r = setup.post("/api/projects", json={"root": str(tmp_path / "sse-proj"), "name": "t"})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]

        graph = {"nodes": [{"id": "g1", "type_id": "fake.api_free", "params": {"text": "x", "cmd": ok_worker_cmd}}], "edges": []}
        r = setup.post(f"/api/projects/{pid}/workflows", json={"recipe": "e2e", "graph": graph})
        assert r.status_code == 200, r.text
        workflow_id = r.json()["workflow_id"]

        r = setup.post(f"/api/projects/{pid}/workflows/{workflow_id}/run", json={})
        assert r.status_code == 200, r.text

    status, seen_ids = _collect_sse_ids(live_server, f"/api/projects/{pid}/events", {}, want=2, hard_timeout=8.0)
    assert status == 200
    assert seen_ids, "expected at least one queue event to arrive"

    last_id = seen_ids[-1]
    _status2, resumed_ids = _collect_sse_ids(
        live_server, f"/api/projects/{pid}/events", {"Last-Event-ID": str(last_id)}, want=1, hard_timeout=2.0,
    )
    assert all(i > last_id for i in resumed_ids), (last_id, resumed_ids)


def test_export_otio_without_extra_returns_clean_error(client, project):
    pid = project["id"]
    try:
        import opentimelineio  # noqa: F401
        pytest.skip("opentimelineio is installed; the not-importable path isn't exercised here")
    except ImportError:
        pass
    r = client.post(f"/api/projects/{pid}/cuts/does-not-matter/export/otio", json={})
    assert r.status_code == 501
    assert "opentimelineio" in r.json()["detail"] or "export" in r.json()["detail"]


def test_openapi_generation_runs(capsys):
    assert openapi_main() == 0
    out = capsys.readouterr().out
    schema = json.loads(out)
    assert schema["openapi"]
    assert "/api/projects" in schema["paths"]
