"""T34: `POST /api/projects/new` is a job, not a blocking request -- refusals before anything is
written, step/progress events over SSE, status for the Ingest page, re-run, import, open-editor."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import httpx

TONES = "aevalsrc='0.4*sin(2*PI*if(lt(mod(t\\,2)\\,1)\\,180\\,260)*t)':s=48000:d=2"


def _recording(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=160x120:r=25:d=2",
                    "-f", "lavfi", "-i", TONES, "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", str(path)], check=True, capture_output=True)
    return path


def _wait(client, pid: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/api/projects/{pid}/ingest/status").json()
        if status["job"] and status["job"]["state"] != "running":
            return status
        time.sleep(0.1)
    raise AssertionError("ingest job did not finish")


def _events(client, pid: str, job_id: str) -> list[dict]:
    return [e["event"] for e in client.get(f"/api/projects/{pid}/queue/{job_id}").json()["events"]]


def test_new_project_job_then_import_then_open_editor(client, tmp_path):
    clip = _recording(tmp_path / "footage" / "ep37.mp4")
    root = tmp_path / "Post" / "keith"
    resp = client.post("/api/projects/new", json={"name": "Sample", "root": str(root), "sources": [str(clip)]})
    assert resp.status_code == 202, resp.text
    pid, job_id = resp.json()["project"]["id"], resp.json()["job_id"]
    assert client.get(f"/api/projects/{pid}").json()["name"] == "Sample"  # init ran before the 202

    status = _wait(client, pid)
    assert status["job"] == {"id": job_id, "state": "ok", "summary": status["job"]["summary"]}
    assert status["audio_ready"] and not status["has_transcript"] and status["cut_ids"] == []
    (source,) = status["sources"]
    assert source["name"] == "ep37.mp4" and source["peaks_ready"]

    events = _events(client, pid, job_id)
    done = [e["step"] for e in events if e["kind"] == "step" and e["status"] == "done"]
    assert done == ["check", "init", "source:0", "audio:0", "peaks:0"]
    assert any(e["kind"] == "progress" and e["step"] == "audio:0" for e in events)
    assert events[-1] == {"kind": "result", "ok": True, "detail": status["job"]["summary"]}
    assert sorted(p.name for p in clip.parent.iterdir()) == ["ep37.mp4"]  # footage untouched

    refused = client.post(f"/api/projects/{pid}/ingest/open-editor")
    assert refused.status_code == 400 and "no transcript yet" in refused.json()["detail"]
    words = tmp_path / "words.json"
    words.write_text(json.dumps([{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.3, "speaker": f"S{i % 2}"}
                                 for i, t in enumerate("so is AI becoming permanent".split())]))
    missing = client.post(f"/api/projects/{pid}/ingest/transcript",
                          json={"sync_group_id": source["sync_group_id"], "path": str(tmp_path / "nope.json")})
    assert missing.status_code == 400 and "Can't find the transcript" in missing.json()["detail"]
    imported = client.post(f"/api/projects/{pid}/ingest/transcript",
                           json={"sync_group_id": source["sync_group_id"], "path": str(words)})
    assert imported.status_code == 200 and imported.json()["words"] == 5
    assert client.get(f"/api/projects/{pid}/ingest/status").json()["has_transcript"]

    opened = client.post(f"/api/projects/{pid}/ingest/open-editor").json()
    assert opened["created"] and client.post(f"/api/projects/{pid}/ingest/open-editor").json() == {
        "cut_id": opened["cut_id"], "created": False}
    cut = client.get(f"/api/projects/{pid}/cuts/{opened['cut_id']}").json()["cut"]
    assert len(cut["passages"]) == 1 and cut["passages"][0]["angle_source_id"] == source["source_id"]

    rerun = client.post(f"/api/projects/{pid}/ingest/run")
    assert rerun.status_code == 202
    status = _wait(client, pid)
    assert status["job"]["id"] == rerun.json()["id"] and status["job"]["state"] == "ok"
    statuses = [e["status"] for e in _events(client, pid, rerun.json()["id"]) if e["kind"] == "step"
                and e["status"] not in ("pending", "running")]
    assert statuses == ["done", "skipped", "skipped", "skipped", "skipped"]


def test_refusals_happen_before_anything_is_written(client, tmp_path, monkeypatch):
    clip = _recording(tmp_path / "footage" / "ep37.mp4")
    cases = [
        ({"root": str(tmp_path / "footage")}, "is the folder ep37.mp4 is in"),
        ({"root": str(tmp_path / "footage" / "post")}, "inside the footage folder"),
        ({"root": str(tmp_path / "Co" / "P" / "Video" / "source" / "x")}, "inside the footage folder"),
        ({"root": "relative/proj"}, "must be a full path"),
        ({"sources": [str(tmp_path / "footage" / "missing.mp4")]}, "Can't find the recording"),
    ]
    for override, message in cases:
        body = {"name": "K", "root": str(tmp_path / "proj"), "sources": [str(clip)], **override}
        resp = client.post("/api/projects/new", json=body)
        assert resp.status_code == 400 and message in resp.json()["detail"], (override, resp.text)
    assert client.get("/api/projects").json()["projects"] == []
    assert not (tmp_path / "proj").exists() and sorted(p.name for p in clip.parent.iterdir()) == ["ep37.mp4"]

    kits = tmp_path / "kits"
    (kits / "only").mkdir(parents=True)
    (kits / "only" / "brand.yaml").write_text("name: only\n")
    monkeypatch.setenv("POST3_KITS_DIR", str(kits))
    resp = client.post("/api/projects/new", json={"name": "K", "root": str(tmp_path / "proj"),
                                                  "sources": [str(clip)], "brand_kit": "nope"})
    assert resp.status_code == 400 and "available: only" in resp.json()["detail"]

    resp = client.post("/api/projects", json={"root": str(tmp_path / "Co" / "P" / "Video" / "source" / "x")})
    assert resp.status_code == 400 and "inside the footage folder" in resp.json()["detail"]


def test_a_failing_step_is_reported_in_plain_words(client, tmp_path):
    notmedia = tmp_path / "footage" / "notes.mp4"
    notmedia.parent.mkdir(parents=True)
    notmedia.write_text("not a recording")
    resp = client.post("/api/projects/new", json={"name": "K", "root": str(tmp_path / "proj"), "sources": [str(notmedia)]})
    pid, job_id = resp.json()["project"]["id"], resp.json()["job_id"]
    status = _wait(client, pid)
    assert status["job"]["state"] == "failed"
    assert status["job"]["summary"].startswith("Add notes.mp4: ffmpeg could not read the file")
    failed = [e for e in _events(client, pid, job_id) if e.get("status") == "failed"]
    assert [(e["step"], e["error"]) for e in failed] == [("source:0", status["job"]["summary"])]


def test_ingest_events_stream_over_sse(live_server, tmp_path):
    clip = _recording(tmp_path / "footage" / "ep37.mp4")
    with httpx.Client(base_url=live_server, timeout=30) as c:
        resp = c.post("/api/projects/new", json={"name": "K", "root": str(tmp_path / "proj"), "sources": [str(clip)]})
        pid, job_id = resp.json()["project"]["id"], resp.json()["job_id"]
        kinds: list[str] = []
        payloads: list[dict] = []
        deadline = time.monotonic() + 20
        with c.stream("GET", f"/api/projects/{pid}/events", params={"workflow": "_ingest"}) as stream:
            for line in stream.iter_lines():
                if line.startswith("event: "):
                    kinds.append(line[len("event: "):])
                elif line.startswith("data: "):
                    payloads.append(json.loads(line[len("data: "):]))
                if kinds and kinds[-1] == "result" and len(payloads) == len(kinds) or time.monotonic() > deadline:
                    break
    assert {"step", "progress", "result"} <= set(kinds)
    assert {p["job_id"] for p in payloads} == {job_id} and {p["workflow_id"] for p in payloads} == {"_ingest"}
    assert payloads[-1]["event"]["ok"] is True
