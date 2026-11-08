"""T34 fixtures: real (tiny) media from ffmpeg's `lavfi` sources in temp dirs -- a footage
folder holding the recordings, and a separate project folder Post may write to."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not on PATH")

SHIPPED_DEMO = Path(__file__).resolve().parents[3] / "brandkit" / "kits" / "_demo"

# Two "voices": a low and a high tone, swapping every 5 s (the CLI smoke run's 60 s file).
TWO_VOICES = "aevalsrc='0.4*sin(2*PI*if(lt(mod(t\\,10)\\,5)\\,180\\,260)*t)':s=48000:d={d}"


def make_recording(path: Path, seconds: float = 2, video: bool = True, audio: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if video:
        cmd += ["-f", "lavfi", "-i", f"color=c=gray:s=160x120:r=25:d={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", TWO_VOICES.format(d=seconds)]
    if video:
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac"]
    subprocess.run([*cmd, "-shortest", str(path)] if video and audio else [*cmd, str(path)],
                   check=True, capture_output=True)
    return path


def two_speaker_words(seconds: float, per_turn: float = 5.0) -> list[dict]:
    words, t, i = [], 0.0, 0
    vocab = "so the question this week is whether AI is becoming permanent".split()
    while t + 0.3 < seconds:
        speaker = "SPEAKER_00" if int(t // per_turn) % 2 == 0 else "SPEAKER_01"
        words.append({"text": vocab[i % len(vocab)], "start": round(t, 3), "end": round(t + 0.3, 3), "speaker": speaker})
        t, i = t + 0.4, i + 1
    return words


@pytest.fixture
def footage(tmp_path) -> Path:
    return tmp_path / "footage"


@pytest.fixture
def clip(footage) -> Path:
    return make_recording(footage / "episode.mp4")


@pytest.fixture
def words_file(footage) -> Path:
    path = footage / "episode.words.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"words": two_speaker_words(2, per_turn=1.0)}))
    return path


@pytest.fixture
def kits(tmp_path, monkeypatch) -> Path:
    kits = tmp_path / "kits"
    for kit_id in ("_demo", "show"):
        shutil.copytree(SHIPPED_DEMO, kits / kit_id)
    monkeypatch.setenv("POST3_KITS_DIR", str(kits))
    return kits
