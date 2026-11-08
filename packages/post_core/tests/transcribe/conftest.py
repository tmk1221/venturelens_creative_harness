"""T35 fixtures: a local fake Deepgram (no network, ever), and a project whose one recording
has (or lacks) a real ffmpeg-built audio proxy. Every test that could reach the provider
points `$DEEPGRAM_API_URL` at the fake and sets a fake key, so neither the real endpoint nor
the real `.env` key is ever used."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from post_core.model.common import Rational
from post_core.model.project import Project
from post_core.model.shoot import Shoot, Source, SyncGroup
from post_core.store import store as store_module
from post_core.store.paths import store_root

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

REPLY = Path(__file__).resolve().parents[1] / "ingest" / "fixtures" / "deepgram_response.json"
FAKE_KEY = "sk-test-fake-deepgram-key"


class FakeDeepgram:
    """Stands in for `api.deepgram.com/v1/listen`: records each request (path, headers, the
    body as it streamed in) and answers `status` with `reply`."""

    def __init__(self, reply: dict, status: int = 200) -> None:
        self.reply, self.status, self.requests = reply, status, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server's naming
                remaining, chunks = int(self.headers.get("Content-Length") or 0), []
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": b"".join(chunks)})
                payload = json.dumps(outer.reply if outer.status == 200 else {"err_msg": "fake failure"}).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1/listen"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake_deepgram(monkeypatch, tmp_path):
    fake_env = tmp_path / "fake.env"
    fake_env.write_text(f"DEEPGRAM_API_KEY={FAKE_KEY}\n")
    monkeypatch.setenv("POST_CORE_ENV_FILE", str(fake_env))
    monkeypatch.setenv("DEEPGRAM_API_KEY", FAKE_KEY)
    monkeypatch.delenv("POST3_FAKE_PROVIDERS", raising=False)
    fake = FakeDeepgram(json.loads(REPLY.read_text()))
    monkeypatch.setenv("DEEPGRAM_API_URL", fake.url)
    yield fake
    fake.close()


def make_m4a(path: Path, seconds: float) -> Path:
    """A real AAC `.m4a` audio proxy of `seconds` (silence encodes fast, even 43 minutes)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", str(seconds),
                    "-c:a", "aac", "-b:a", "16k", "-f", "mp4", str(path)], check=True, capture_output=True)
    return path


def make_project(tmp_path: Path, seconds: float = 3.0, with_proxy: bool = True) -> tuple[Path, Shoot, SyncGroup]:
    """A project with one camera recording (never uploaded) in its own sync group."""
    root = tmp_path / "proj"
    store_module.init_project(root)
    store_module.write(root, "project", Project(name="t35", root=str(root)), expected_rev=0)
    camera = tmp_path / "footage" / "episode-37.mp4"
    camera.parent.mkdir(parents=True, exist_ok=True)
    camera.write_bytes(b"camera file: must never be the upload")
    source = Source(path=str(camera), fps=Rational(num=25, den=1), role="a_roll", content_fingerprint="fp-cam")
    if with_proxy:
        proxy = make_m4a(store_root(root) / "proxies" / "fp-cam.audio.m4a", seconds)
        source = source.model_copy(update={"audio_proxy_path": str(proxy)})
    group = SyncGroup(source_ids=[source.id], offsets={source.id: 0.0})
    shoot = Shoot(name="default", sources=[source], sync_groups=[group])
    store_module.write(root, "shoot", shoot, expected_rev=0)
    return root, shoot, group


@pytest.fixture
def project_factory(tmp_path):
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")

    def _make(seconds: float = 3.0, with_proxy: bool = True) -> tuple[Path, Shoot, SyncGroup]:
        return make_project(tmp_path, seconds, with_proxy)

    return _make


@pytest.fixture
def m4a():
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    return make_m4a
