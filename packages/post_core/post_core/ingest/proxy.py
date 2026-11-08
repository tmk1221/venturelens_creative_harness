"""Build an editor-playback proxy: 720p H.264 + AAC, faststart, keyed by fingerprint.

Idempotent: a valid proxy already on disk for this fingerprint is reused unless
`force=True`. Written via temp-file-then-rename so a crash mid-encode never leaves a
half-written file that `is_valid_proxy` would mistake for done.

`out_dir` is caller-chosen and may be anywhere writable (e.g. inside the project store,
even when the source lives elsewhere, possibly on a read-only volume) -- nothing here
ever writes next to the source.

`start`/`duration` (seconds) build a partial proxy -- e.g. a fast 3-minute smoke proxy of
a multi-hour source -- keyed into a distinct filename so it never collides with (or gets
mistaken for) the full proxy of the same fingerprint.

Encoding prefers `h264_videotoolbox` (Apple Silicon/Intel hardware encode, much faster)
when ffmpeg reports it available, falling back to the `libx264` software encoder on any
hardware-encode failure or when videotoolbox isn't present.
"""
from __future__ import annotations

import functools
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class ProxyError(RuntimeError):
    """ffmpeg failed to build the proxy."""


def proxy_path_for(
    out_dir: str | Path, fingerprint: str, start: Optional[float] = None, duration: Optional[float] = None,
) -> Path:
    suffix = ""
    if start is not None or duration is not None:
        s = start or 0.0
        d = duration or 0.0
        suffix = f".s{s:g}-d{d:g}"
    return Path(out_dir) / f"{fingerprint}{suffix}.proxy.mp4"


def is_valid_proxy(path: str | Path) -> bool:
    p = Path(path)
    return p.is_file() and p.stat().st_size > 0


@functools.lru_cache(maxsize=1)
def _videotoolbox_available() -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "h264_videotoolbox" in proc.stdout


def _video_codec_args(use_videotoolbox: bool) -> list[str]:
    if use_videotoolbox:
        return ["-c:v", "h264_videotoolbox", "-b:v", "6M", "-allow_sw", "1"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]


def _build_cmd(
    source_path: str | Path, tmp: Path, height: int,
    start: Optional[float], duration: Optional[float], use_videotoolbox: bool,
) -> list[str]:
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]  # before -i: fast (keyframe-seek) input trim
    cmd += ["-i", str(source_path)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-vf", f"scale=-2:{height}"]
    cmd += _video_codec_args(use_videotoolbox)
    cmd += [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-f", "mp4",
        str(tmp),
    ]
    return cmd


def build_proxy(
    source_path: str | Path,
    out_dir: str | Path,
    fingerprint: str,
    height: int = 720,
    force: bool = False,
    start: Optional[float] = None,
    duration: Optional[float] = None,
    prefer_videotoolbox: bool = True,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = proxy_path_for(out_dir, fingerprint, start=start, duration=duration)
    if not force and is_valid_proxy(out):
        return out

    tmp = out.with_suffix(out.suffix + ".tmp")
    use_vt = prefer_videotoolbox and _videotoolbox_available()
    cmd = _build_cmd(source_path, tmp, height, start, duration, use_vt)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ProxyError("ffmpeg not found on PATH") from exc

    if proc.returncode != 0 and use_vt:
        # Hardware encode can fail on some sources/machines; retry once in software.
        tmp.unlink(missing_ok=True)
        cmd = _build_cmd(source_path, tmp, height, start, duration, use_videotoolbox=False)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise ProxyError("ffmpeg not found on PATH") from exc

    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise ProxyError(f"ffmpeg failed building proxy for {source_path}: {proc.stderr.strip()}")

    tmp.replace(out)
    return out
