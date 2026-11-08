"""Build an editor-playback audio proxy: AAC `.m4a` (mono/stereo, 128k), keyed by
fingerprint. T22: Post plays audio only -- no video proxies, no encode step for picture.
Picture/angle judgement happens in Resolve, where the operators already work.

Idempotent, same shape as `post_core.ingest.proxy`: a valid audio proxy already on disk for
this fingerprint is reused unless `force=True`, written via temp-file-then-rename so a crash
mid-encode never leaves a half file that `is_valid_audio_proxy` would mistake for done.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

ProgressFn = Callable[[float], None]


class AudioProxyError(RuntimeError):
    """ffmpeg failed to build the audio proxy."""


def audio_proxy_path_for(out_dir: str | Path, fingerprint: str) -> Path:
    return Path(out_dir) / f"{fingerprint}.audio.m4a"


def is_valid_audio_proxy(path: str | Path) -> bool:
    p = Path(path)
    return p.is_file() and p.stat().st_size > 0


def build_audio_proxy(
    source_path: str | Path,
    out_dir: str | Path,
    fingerprint: str,
    bitrate: str = "128k",
    force: bool = False,
    duration: Optional[float] = None,
    on_progress: Optional[ProgressFn] = None,
) -> Path:
    """T34: with `duration` (seconds, from the probe) and `on_progress`, ffmpeg's own
    `-progress` stream is read while it encodes and `on_progress(fraction)` is called with
    0..1 -- a 43-minute recording takes long enough that a silent step looks hung."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = audio_proxy_path_for(out_dir, fingerprint)
    if not force and is_valid_audio_proxy(out):
        return out

    tmp = out.with_suffix(out.suffix + ".tmp")
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(source_path),
        "-vn",
        "-c:a", "aac", "-b:a", bitrate,
        "-movflags", "+faststart",
        "-f", "mp4",
        str(tmp),
    ]
    try:
        proc = _run(cmd, duration, on_progress)
    except FileNotFoundError as exc:
        raise AudioProxyError("ffmpeg not found on PATH") from exc

    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise AudioProxyError(f"ffmpeg failed building audio proxy for {source_path}: {proc.stderr.strip()}")

    tmp.replace(out)
    return out


def _run(cmd: list[str], duration: Optional[float], on_progress: Optional[ProgressFn]) -> subprocess.CompletedProcess:
    if on_progress is None or not duration or duration <= 0:
        return subprocess.run(cmd, capture_output=True, text=True)
    # `-progress pipe:1` writes `key=value` lines to stdout; stderr goes to a temp file so a
    # chatty ffmpeg can never fill a pipe nobody is reading and deadlock the encode.
    with tempfile.TemporaryFile(mode="w+") as err:
        proc = subprocess.Popen([cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]],
                                stdout=subprocess.PIPE, stderr=err, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and value.isdigit():
                on_progress(min(1.0, int(value) / 1e6 / duration))
        proc.wait()
        err.seek(0)
        return subprocess.CompletedProcess(cmd, proc.returncode, "", err.read())
