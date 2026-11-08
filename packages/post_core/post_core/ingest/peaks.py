"""Int8 min/max waveform peaks, decoded from source audio via an ffmpeg PCM pipe.

File layout: N samples/sec * 2 bytes/sample (signed int8 lo, hi), no header — the caller
already knows `samples_per_sec` (it chose it) and the source duration. Kept file-format
simple on purpose: this is a peaks cache, not an interchange format.
"""
from __future__ import annotations

import subprocess
import sys
from array import array
from pathlib import Path

PCM_RATE = 8000  # Hz; decode rate ffmpeg is asked to resample to before bucketing


class PeaksError(RuntimeError):
    """ffmpeg failed to decode audio for peaks."""


def _decode_pcm_s16le_mono(source_path: str | Path) -> bytes:
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(source_path),
        "-vn", "-ac", "1", "-ar", str(PCM_RATE), "-f", "s16le", "-",
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError as exc:
        raise PeaksError("ffmpeg not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise PeaksError(f"ffmpeg failed decoding audio for {source_path}: "
                          f"{exc.stderr.decode(errors='replace').strip()}") from exc
    return proc.stdout


def _to_int8(sample_16: int) -> int:
    v = sample_16 // 256
    return max(-128, min(127, v))


def compute_peaks(pcm_s16le: bytes, samples_per_sec: int = 100, pcm_rate: int = PCM_RATE) -> bytes:
    """Pure function: raw s16le mono PCM -> int8 min/max peaks bytes. No I/O; easy to test."""
    n_samples = len(pcm_s16le) // 2
    if n_samples == 0:
        return b""
    # T34: a typed array, not `struct.unpack` into a tuple of Python ints -- the tuple cost
    # ~1 GB of memory for a 45-minute show; this is the 2 bytes/sample the PCM already is.
    samples = array("h")
    samples.frombytes(pcm_s16le[: n_samples * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    bucket = max(1, pcm_rate // max(1, samples_per_sec))
    out = bytearray()
    for i in range(0, n_samples, bucket):
        chunk = samples[i:i + bucket]
        if not chunk:
            continue
        out.append(_to_int8(min(chunk)) & 0xFF)
        out.append(_to_int8(max(chunk)) & 0xFF)
    return bytes(out)


def build_peaks(source_path: str | Path, out_path: str | Path, samples_per_sec: int = 100) -> Path:
    pcm = _decode_pcm_s16le_mono(source_path)
    peaks_bytes = compute_peaks(pcm, samples_per_sec=samples_per_sec)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_bytes(peaks_bytes)
    tmp.replace(out)
    return out
