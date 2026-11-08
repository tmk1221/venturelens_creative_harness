from __future__ import annotations

from post_core.ingest import probe

from .conftest import requires_ffmpeg


@requires_ffmpeg
def test_probe_source_fields(tiny_video):
    result = probe.probe_source(tiny_video)
    assert result["path"] == str(tiny_video.resolve())
    assert result["width"] == 320
    assert result["height"] == 240
    assert result["fps"].as_float() == 25.0
    assert 0.5 < result["duration"] < 2.0
    assert len(result["audio_streams"]) == 1
    assert result["audio_streams"][0]["channels"] == 1
    assert len(result["content_fingerprint"]) == 64  # sha256 hex


@requires_ffmpeg
def test_probe_fingerprint_stable_for_unchanged_file(tiny_video):
    first = probe.content_fingerprint(tiny_video)
    second = probe.content_fingerprint(tiny_video)
    assert first == second


@requires_ffmpeg
def test_probe_fingerprint_changes_with_content(tmp_path, tiny_video):
    other = tmp_path / "other.mp4"
    other.write_bytes(tiny_video.read_bytes() + b"\x00")
    assert probe.content_fingerprint(tiny_video) != probe.content_fingerprint(other)


def test_probe_raises_clear_error_for_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.mp4"
    try:
        probe.probe_source(missing)
    except (probe.ProbeError, FileNotFoundError, OSError):
        pass
    else:
        raise AssertionError("expected an error probing a missing file")


def test_probe_reads_timecode_from_data_stream(monkeypatch, tmp_path):
    """Some cameras (e.g. Sony) stamp a start timecode on a separate `data` stream
    rather than on the video stream's own tags or the container format tags."""
    fake = tmp_path / "cam.mp4"
    fake.write_bytes(b"fake")
    payload = {
        "format": {"duration": "10.0", "tags": {}},
        "streams": [
            {"codec_type": "video", "r_frame_rate": "24000/1001", "width": 3840, "height": 2160, "tags": {}},
            {"codec_type": "audio", "channels": 2, "sample_rate": "48000", "codec_name": "pcm_s16be"},
            {"codec_type": "data", "tags": {"timecode": "18:26:57:00"}},
        ],
    }
    monkeypatch.setattr(probe, "ffprobe_json", lambda p: payload)
    monkeypatch.setattr(probe, "content_fingerprint", lambda p: "x" * 64)
    result = probe.probe_source(fake)
    assert result["start_timecode"] == "18:26:57:00"
