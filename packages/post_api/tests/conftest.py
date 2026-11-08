"""Shared fixtures for post_api tests: a fresh `create_app()` per test (own registry file,
own `app.state`) driven with `fastapi.testclient.TestClient`, plus fake node types so tests
never touch a real provider (same pattern as post_core's own CLI acceptance test)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from post_api.app import create_app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def lavfi_clip(tmp_path):
    out = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest",
         "-c:v", "libx264", "-c:a", "aac", str(out)],
        check=True, capture_output=True,
    )
    return out


@pytest.fixture(autouse=True)
def fake_node_types(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("POST_CORE_EXTRA_NODE_TYPES", "fake_nodes:register")
    # T39: no test ever reads the real media library (or `~/.post3rc`).
    monkeypatch.setenv("POST3_LIBRARY", str(tmp_path_factory.getbasetemp() / "no-library"))
    monkeypatch.setenv("POST3_RC", str(tmp_path_factory.getbasetemp() / "no-post3rc"))
    monkeypatch.setenv("POST3_HIGGSFIELD_BIN", "/nonexistent/post3-tests-never-run-higgsfield")
    monkeypatch.setenv("POST_CORE_ENV_FILE", str(FIXTURES_DIR / "fake.env"))
    # T36: never the real `claude`/`codex` -- a forgotten real-mode agent call fails here.
    monkeypatch.setenv("POST3_CLAUDE_BIN", "/nonexistent/post3-tests-never-run-a-real-agent")
    monkeypatch.setenv("POST3_CODEX_BIN", "/nonexistent/post3-tests-never-run-a-real-agent")
    if str(FIXTURES_DIR) not in sys.path:
        sys.path.insert(0, str(FIXTURES_DIR))
    yield


@pytest.fixture
def client(tmp_path):
    registry_path = tmp_path / "registry.json"
    app = create_app(registry_path)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client, tmp_path):
    """Register + open a fresh project, return its `{id, root, name}` registry entry."""
    root = tmp_path / "proj"
    resp = client.post("/api/projects", json={"root": str(root), "name": "t"})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
def live_server(tmp_path):
    """A real uvicorn server on a real socket, for the one test (SSE) that needs genuine
    incremental streaming: httpx's `ASGITransport` (what `TestClient`/`httpx.AsyncClient`
    use in-process) buffers an ASGI app's entire response body before returning anything,
    so it cannot exercise a real never-ending `StreamingResponse` -- only a real socket can."""
    import socket
    import threading

    import uvicorn

    registry_path = tmp_path / "registry.json"
    app = create_app(registry_path)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = __import__("time").monotonic() + 10
    while not server.started and __import__("time").monotonic() < deadline:
        __import__("time").sleep(0.05)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)
