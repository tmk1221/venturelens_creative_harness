"""Runs the ingest worker subcommands as real subprocesses through T03's runner, the
same way the graph/queue layer will drive them."""
from __future__ import annotations

import json
import sys

from post_core.workers import runner

from .conftest import requires_ffmpeg

PY = sys.executable


@requires_ffmpeg
def test_worker_proxy_ok_through_runner(tmp_path, tiny_video):
    out_dir = tmp_path / "proxies"
    result = runner.run(
        [PY, "-m", "post_core.ingest.worker", "proxy",
         "--source", str(tiny_video), "--out-dir", str(out_dir), "--fingerprint", "fp1"],
        cwd=tmp_path,
    )
    assert result.outcome == runner.OK, result.tail
    assert result.exit_code == 0
    assert len(result.artifacts) == 1
    assert result.artifacts[0]["role"] == "proxy"
    assert (out_dir / "fp1.proxy.mp4").is_file()


@requires_ffmpeg
def test_worker_peaks_ok_through_runner(tmp_path, tiny_audio):
    out = tmp_path / "peaks.bin"
    result = runner.run(
        [PY, "-m", "post_core.ingest.worker", "peaks",
         "--source", str(tiny_audio), "--out", str(out), "--rate", "50"],
        cwd=tmp_path,
    )
    assert result.outcome == runner.OK, result.tail
    assert out.is_file()
    assert result.artifacts[0]["role"] == "peaks"


def test_worker_transcribe_import_json_ok_through_runner(tmp_path):
    src = tmp_path / "words.json"
    src.write_text(json.dumps([{"text": "hi", "start": 0.0, "end": 0.2}]))
    out = tmp_path / "transcript.json"
    result = runner.run(
        [PY, "-m", "post_core.ingest.worker", "transcribe",
         "--source", str(src), "--out", str(out), "--provider", "import",
         "--sync-group-id", "sg1", "--fingerprint", "fp1"],
        cwd=tmp_path,
    )
    assert result.outcome == runner.OK, result.tail
    assert out.is_file()
    data = json.loads(out.read_text())
    assert data["sync_group_id"] == "sg1"
    assert data["words"][0]["text"] == "hi"


def test_worker_transcribe_missing_source_is_failed(tmp_path):
    out = tmp_path / "transcript.json"
    result = runner.run(
        [PY, "-m", "post_core.ingest.worker", "transcribe",
         "--source", str(tmp_path / "does_not_exist.json"), "--out", str(out),
         "--provider", "import", "--format", "json",
         "--sync-group-id", "sg1", "--fingerprint", "fp1"],
        cwd=tmp_path,
    )
    assert result.outcome == runner.FAILED
    assert not out.exists()


def test_worker_proxy_bad_source_is_failed(tmp_path):
    bad = tmp_path / "not_media.txt"
    bad.write_text("nope")
    result = runner.run(
        [PY, "-m", "post_core.ingest.worker", "proxy",
         "--source", str(bad), "--out-dir", str(tmp_path / "out"), "--fingerprint", "fp1"],
        cwd=tmp_path,
    )
    assert result.outcome == runner.FAILED
