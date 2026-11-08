from __future__ import annotations

from post_core.ingest import audio_proxy

from .conftest import requires_ffmpeg


@requires_ffmpeg
def test_build_audio_proxy_creates_valid_file(tmp_path, tiny_video):
    out_dir = tmp_path / "proxies"
    out = audio_proxy.build_audio_proxy(tiny_video, out_dir, fingerprint="abc123")
    assert out == out_dir / "abc123.audio.m4a"
    assert audio_proxy.is_valid_audio_proxy(out)


@requires_ffmpeg
def test_build_audio_proxy_has_no_video_stream(tmp_path, tiny_video):
    import subprocess

    out = audio_proxy.build_audio_proxy(tiny_video, tmp_path / "out", fingerprint="abc123")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )
    streams = [s for s in probe.stdout.strip().splitlines() if s]
    assert streams == ["audio"]


@requires_ffmpeg
def test_build_audio_proxy_is_idempotent(tmp_path, tiny_video):
    out_dir = tmp_path / "proxies"
    first = audio_proxy.build_audio_proxy(tiny_video, out_dir, fingerprint="abc123")
    mtime_before = first.stat().st_mtime_ns
    second = audio_proxy.build_audio_proxy(tiny_video, out_dir, fingerprint="abc123")
    assert second == first
    assert second.stat().st_mtime_ns == mtime_before  # not re-encoded


@requires_ffmpeg
def test_build_audio_proxy_force_rebuilds(tmp_path, tiny_video):
    out_dir = tmp_path / "proxies"
    first = audio_proxy.build_audio_proxy(tiny_video, out_dir, fingerprint="abc123")
    first.write_bytes(b"")  # corrupt it
    assert not audio_proxy.is_valid_audio_proxy(first)
    rebuilt = audio_proxy.build_audio_proxy(tiny_video, out_dir, fingerprint="abc123", force=True)
    assert audio_proxy.is_valid_audio_proxy(rebuilt)


@requires_ffmpeg
def test_build_audio_proxy_raises_on_bad_source(tmp_path):
    bad = tmp_path / "not_media.txt"
    bad.write_text("not media")
    try:
        audio_proxy.build_audio_proxy(bad, tmp_path / "out", fingerprint="x")
    except audio_proxy.AudioProxyError:
        pass
    else:
        raise AssertionError("expected AudioProxyError for a non-media source")
