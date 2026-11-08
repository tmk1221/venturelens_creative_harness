"""T35 over HTTP: the API loads `.env` at startup without overriding real env vars (and never
prints a value); transcription is estimate -> one-click budget -> a queued job the project's
runtime runs against a local fake Deepgram (never the network), with progress events, the
audio proxy uploaded as `audio/mp4`, and refusals; speakers are listed and renamed; and the
runtime never interrupts a live job from a workflow created after it started."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from post_api.app import create_app
from post_core.graph.workflow import Node, Workflow
from post_core.model.common import Rational
from post_core.model.shoot import Shoot, Source, SyncGroup
from post_core.queue import db as db_mod
from post_core.store import store as store_module
from post_core.store.paths import store_root

REPLY = Path(__file__).resolve().parents[2] / "post_core" / "tests" / "ingest" / "fixtures" / "deepgram_response.json"
FAKE_KEY = "sk-test-fake-deepgram-key"


class FakeDeepgram:
    """A local stand-in for `api.deepgram.com/v1/listen` that records what it was sent."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.requests.append({"headers": dict(self.headers), "body": body})
                payload = REPLY.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/listen"


@pytest.fixture
def fake_deepgram(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", FAKE_KEY)  # never the real key, even if the shell has one
    monkeypatch.delenv("POST3_FAKE_PROVIDERS", raising=False)
    fake = FakeDeepgram()
    monkeypatch.setenv("DEEPGRAM_API_URL", fake.url)
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


def _project(client, tmp_path: Path, with_proxy: bool = True) -> tuple[str, Path, Shoot, SyncGroup]:
    root = tmp_path / "proj"
    pid = client.post("/api/projects", json={"root": str(root), "name": "t35"}).json()["id"]
    camera = tmp_path / "footage" / "episode-37.mp4"
    camera.parent.mkdir(parents=True)
    camera.write_bytes(b"camera file: never the upload")
    source = Source(path=str(camera), fps=Rational(num=25, den=1), role="a_roll", content_fingerprint="fp-cam")
    if with_proxy:
        proxy = store_root(root) / "proxies" / "fp-cam.audio.m4a"
        proxy.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", "3",
                        "-c:a", "aac", "-b:a", "16k", "-f", "mp4", str(proxy)], check=True, capture_output=True)
        source = source.model_copy(update={"audio_proxy_path": str(proxy)})
    group = SyncGroup(source_ids=[source.id], offsets={source.id: 0.0})
    shoot = Shoot(name="default", sources=[source], sync_groups=[group])
    store_module.write(root, "shoot", shoot, expected_rev=0)
    return pid, root, shoot, group


def _wait_for_transcript(client, pid: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        (source,) = client.get(f"/api/projects/{pid}/ingest/status").json()["sources"]
        job = source["transcribe_job"]
        if job and job["state"] not in ("queued", "running"):
            return source
        time.sleep(0.1)
    raise AssertionError("the transcription job did not finish")


def test_api_loads_dotenv_at_startup_without_overriding_real_env(tmp_path, monkeypatch, capsys, caplog):
    env_file = tmp_path / "t35.env"
    env_file.write_text("DEEPGRAM_API_KEY=value-from-dotenv\nT35_ONLY_IN_DOTENV=value-from-dotenv\n")
    monkeypatch.setenv("POST_CORE_ENV_FILE", str(env_file))
    monkeypatch.setenv("DEEPGRAM_API_KEY", "value-from-real-env")
    monkeypatch.setenv("T35_ONLY_IN_DOTENV", "x")
    monkeypatch.delenv("T35_ONLY_IN_DOTENV")  # absent now, and removed again after the test

    app = create_app(tmp_path / "registry.json")
    assert "T35_ONLY_IN_DOTENV" not in os.environ
    with TestClient(app) as c:
        assert os.environ["T35_ONLY_IN_DOTENV"] == "value-from-dotenv"
        assert os.environ["DEEPGRAM_API_KEY"] == "value-from-real-env"
        assert c.get("/api/doctor").json()["keys"]["DEEPGRAM_API_KEY"] is True
    out = capsys.readouterr()
    assert "value-from-dotenv" not in out.out + out.err + caplog.text


def test_transcribe_is_an_authorised_queued_job(client, tmp_path, fake_deepgram):
    pid, root, shoot, group = _project(client, tmp_path)
    base = f"/api/projects/{pid}"
    estimate = client.get(f"{base}/ingest/transcribe/estimate", params={"sync_group_id": group.id}).json()
    assert (estimate["amount"], estimate["unit"], estimate["provider"]) == (0.01, "usd", "deepgram")

    no_budget = client.post(f"{base}/ingest/transcribe", json={"sync_group_id": group.id})
    assert no_budget.status_code == 402 and "needs a budget" in no_budget.json()["error"]
    unknown = client.post(f"{base}/ingest/transcribe", json={"sync_group_id": group.id, "budget": "never-made"})
    assert unknown.status_code == 409 and unknown.json()["reason"] == "unknown_budget"
    assert client.put(f"{base}/budgets/tiny", json={"cap": 0.001, "unit": "usd"}).status_code == 200
    tiny = client.post(f"{base}/ingest/transcribe", json={"sync_group_id": group.id, "budget": "tiny"})
    assert tiny.status_code == 402 and tiny.json()["reason"] == "over_headroom"
    with db_mod.open_db(root) as con:
        assert con.execute("SELECT COUNT(*) AS c FROM job").fetchone()["c"] == 0
    assert fake_deepgram.requests == []

    assert client.put(f"{base}/budgets/click-1", json={"cap": estimate["amount"], "unit": "usd"}).status_code == 200
    queued = client.post(f"{base}/ingest/transcribe", json={"sync_group_id": group.id, "budget": "click-1", "by": "web"})
    assert queued.status_code == 202, queued.text
    assert queued.json()["workflow_id"] == f"transcribe-{group.id}" and queued.json()["amount"] == 0.01

    source = _wait_for_transcript(client, pid)
    assert source["transcribe_job"]["state"] == "ok", source["transcribe_job"]
    assert source["transcript_id"] and source["words"] == 6
    events = [e["event"] for e in client.get(f"{base}/queue/{queued.json()['job_id']}").json()["events"]]
    assert any(e["kind"] == "progress" and e["n"] == 100 for e in events)
    assert events[-1]["kind"] == "result" and events[-1]["ok"] is True
    (req,) = fake_deepgram.requests
    proxy = Path(shoot.sources[0].audio_proxy_path)
    assert req["headers"]["Content-Type"] == "audio/mp4"
    assert hashlib.sha256(req["body"]).hexdigest() == hashlib.sha256(proxy.read_bytes()).hexdigest()
    assert client.get(f"{base}/budgets/click-1").json()["budget"]["spent"] == pytest.approx(0.01)

    again = client.post(f"{base}/ingest/transcribe", json={"sync_group_id": group.id, "budget": "click-1"})
    assert again.status_code == 409 and "already has a transcript" in again.json()["detail"]


def test_speakers_are_listed_and_renamed_everywhere(client, tmp_path):
    pid, root, shoot, group = _project(client, tmp_path)
    words = tmp_path / "words.json"
    words.write_text(json.dumps([{"text": t, "start": i * 0.5, "end": i * 0.5 + 0.4, "speaker": f"SPEAKER_0{i // 3}"}
                                 for i, t in enumerate("so is AI becoming permanent now".split())]))
    imported = client.post(f"/api/projects/{pid}/ingest/transcript", json={"sync_group_id": group.id, "path": str(words)})
    tid = imported.json()["transcript_id"]
    url = f"/api/projects/{pid}/transcripts/{tid}/speakers"

    listed = client.get(url).json()
    assert listed["source_id"] == shoot.sources[0].id
    assert [(s["label"], s["name"], s["words"]) for s in listed["speakers"]] == [("SPEAKER_00", None, 3), ("SPEAKER_01", None, 3)]
    assert listed["speakers"][1]["sample"] == {"start": 1.5, "end": 2.9, "text": "becoming permanent now"}

    renamed = client.put(url, json={"names": {"SPEAKER_00": "a podcast host"}})
    assert renamed.status_code == 200 and renamed.json()["speakers"][0]["name"] == "a podcast host"
    assert renamed.json()["revision"] == listed["revision"] + 1
    assert client.get(url).json()["speakers"][0]["name"] == "a podcast host"
    bad = client.put(url, json={"names": {"SPEAKER_09": "Nobody"}})
    assert bad.status_code == 400 and "no speaker SPEAKER_09" in bad.json()["detail"]


def test_missing_audio_proxy_is_refused(client, tmp_path, fake_deepgram):
    pid, _root, _shoot, group = _project(client, tmp_path, with_proxy=False)
    for resp in (client.get(f"/api/projects/{pid}/ingest/transcribe/estimate", params={"sync_group_id": group.id}),
                 client.post(f"/api/projects/{pid}/ingest/transcribe", json={"sync_group_id": group.id, "budget": "b"})):
        assert resp.status_code == 400 and "run ingest audio first" in resp.json()["detail"]
    assert fake_deepgram.requests == []


def test_runtime_never_interrupts_a_live_job_of_a_workflow_it_did_not_start_with(client, project):
    """Another process (e.g. `post ingest transcribe` in a terminal) queued and is running this
    job; the API's runtime first sees the workflow mid-run and must leave it alone, not mark
    it interrupted and re-run (re-spend) it."""
    root = Path(project["root"])
    time.sleep(0.3)  # the runtime has started and listed the workflows it began with
    workflow = Workflow(id="wf-later", recipe_id="t35", nodes=[Node(id="n", type_id="text.prompt", params={"text": "x"})])
    store_module.write(root, "workflow", workflow, expected_rev=0)
    with db_mod.open_db(root) as con:
        con.execute("INSERT INTO job (id, workflow_id, node_id, input_hash, lane, state, cmd_json, attempts, created_at, "
                    "started_at) VALUES ('job-elsewhere', 'wf-later', 'n', 'h', 'remote', 'running', '[]', 1, ?, ?)",
                    (time.time(), time.time()))
        con.commit()
    time.sleep(1.0)  # several runtime polls
    with db_mod.open_db(root) as con:
        assert con.execute("SELECT state FROM job WHERE id='job-elsewhere'").fetchone()["state"] == "running"
