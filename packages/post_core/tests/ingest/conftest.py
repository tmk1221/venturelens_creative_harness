from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

requires_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not on PATH")


@pytest.fixture
def tiny_video(tmp_path: Path) -> Path:
    """A ~1s 320x240 video with a 440Hz tone, generated entirely by ffmpeg's lavfi
    sources (no fixture binary checked in)."""
    out = tmp_path / "tiny.mp4"
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


@pytest.fixture
def tiny_audio(tmp_path: Path) -> Path:
    """A ~1s mono WAV tone, for peaks tests that don't need a video stream."""
    out = tmp_path / "tiny.wav"
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-ac", "1", "-ar", "8000", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out
