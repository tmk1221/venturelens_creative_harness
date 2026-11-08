from __future__ import annotations

import struct

from post_core.ingest import peaks

from .conftest import requires_ffmpeg


def test_compute_peaks_length_and_range():
    # 1 second of a synthetic 16-bit sine wave at the decode rate.
    rate = peaks.PCM_RATE
    import math
    samples = [int(16000 * math.sin(2 * math.pi * 440 * t / rate)) for t in range(rate)]
    pcm = struct.pack(f"<{len(samples)}h", *samples)

    out = peaks.compute_peaks(pcm, samples_per_sec=100, pcm_rate=rate)
    assert len(out) == 100 * 2  # 100 windows/sec * (min, max) bytes
    for b in out:
        signed = b - 256 if b > 127 else b
        assert -128 <= signed <= 127


def test_compute_peaks_empty_input():
    assert peaks.compute_peaks(b"", samples_per_sec=100) == b""


@requires_ffmpeg
def test_build_peaks_writes_file(tmp_path, tiny_audio):
    out = peaks.build_peaks(tiny_audio, tmp_path / "peaks.bin", samples_per_sec=50)
    assert out.is_file()
    data = out.read_bytes()
    assert len(data) > 0
    assert len(data) % 2 == 0
    # ~1s of audio at 50 windows/sec should be roughly 50 windows (allow ffmpeg slack).
    n_windows = len(data) // 2
    assert 30 <= n_windows <= 70


@requires_ffmpeg
def test_build_peaks_from_video_source(tmp_path, tiny_video):
    out = peaks.build_peaks(tiny_video, tmp_path / "peaks.bin", samples_per_sec=100)
    assert out.is_file()
    assert out.stat().st_size > 0
