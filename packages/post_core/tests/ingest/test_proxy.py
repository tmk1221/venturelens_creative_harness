from __future__ import annotations

import subprocess

from post_core.ingest import proxy

from .conftest import requires_ffmpeg


@requires_ffmpeg
def test_build_proxy_creates_valid_file(tmp_path, tiny_video):
    out_dir = tmp_path / "proxies"
    out = proxy.build_proxy(tiny_video, out_dir, fingerprint="abc123")
    assert out == out_dir / "abc123.proxy.mp4"
    assert proxy.is_valid_proxy(out)


@requires_ffmpeg
def test_build_proxy_is_idempotent(tmp_path, tiny_video):
    out_dir = tmp_path / "proxies"
    first = proxy.build_proxy(tiny_video, out_dir, fingerprint="abc123")
    mtime_before = first.stat().st_mtime_ns
    second = proxy.build_proxy(tiny_video, out_dir, fingerprint="abc123")
    assert second == first
    assert second.stat().st_mtime_ns == mtime_before  # not re-encoded


@requires_ffmpeg
def test_build_proxy_force_rebuilds(tmp_path, tiny_video):
    out_dir = tmp_path / "proxies"
    first = proxy.build_proxy(tiny_video, out_dir, fingerprint="abc123")
    first.write_bytes(b"")  # corrupt it
    assert not proxy.is_valid_proxy(first)
    rebuilt = proxy.build_proxy(tiny_video, out_dir, fingerprint="abc123")
    assert proxy.is_valid_proxy(rebuilt)


@requires_ffmpeg
def test_build_proxy_raises_on_bad_source(tmp_path):
    bad = tmp_path / "not_media.txt"
    bad.write_text("not a video")
    try:
        proxy.build_proxy(bad, tmp_path / "out", fingerprint="x")
    except proxy.ProxyError:
        pass
    else:
        raise AssertionError("expected ProxyError for a non-media source")


@requires_ffmpeg
def test_build_proxy_out_dir_need_not_be_near_source(tmp_path, tiny_video):
    """out_dir is caller-chosen and may sit far from source_path (e.g. source on a
    read-only volume, out_dir inside the project store)."""
    out_dir = tmp_path / "elsewhere" / "proxies"
    out = proxy.build_proxy(tiny_video, out_dir, fingerprint="abc123", prefer_videotoolbox=False)
    assert out.parent == out_dir
    assert proxy.is_valid_proxy(out)


@requires_ffmpeg
def test_build_proxy_partial_is_shorter_and_named_distinctly(tmp_path, tiny_video):
    full = proxy.build_proxy(tiny_video, tmp_path / "out", fingerprint="abc123", prefer_videotoolbox=False)
    partial = proxy.build_proxy(
        tiny_video, tmp_path / "out", fingerprint="abc123", start=0.0, duration=0.3, prefer_videotoolbox=False,
    )
    assert partial != full
    assert partial.name == "abc123.s0-d0.3.proxy.mp4"
    assert proxy.is_valid_proxy(partial)

    def dur(path):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())

    assert dur(partial) < dur(full)


@requires_ffmpeg
def test_build_proxy_falls_back_to_software_when_videotoolbox_unavailable(tmp_path, tiny_video, monkeypatch):
    monkeypatch.setattr(proxy, "_videotoolbox_available", lambda: False)
    out = proxy.build_proxy(tiny_video, tmp_path / "out", fingerprint="abc123", prefer_videotoolbox=True)
    assert proxy.is_valid_proxy(out)


def test_proxy_path_for_partial_vs_full_dont_collide(tmp_path):
    full = proxy.proxy_path_for(tmp_path, "fp")
    partial = proxy.proxy_path_for(tmp_path, "fp", start=0.0, duration=180.0)
    assert full != partial
