"""Media serving: proxy playback (HTTP Range), waveform peaks, and content-addressed
assets. Every path here is resolved from an id server-side (T10 spec: "path always resolved
from ids server-side, never from a client-supplied path") -- a client only ever sends a
`source_id` / `content_hash`, and every response carries the content fingerprint (as an
ETag) so a browser never replays a stale file for the same URL."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from post_core.model.shoot import Source
from post_core.store import store as store_module
from post_core.store.paths import store_root

from ..deps import get_project_root
from ..errors import PathTraversal

router = APIRouter(prefix="/api/projects/{pid}/media", tags=["media"])

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_token(value: str, field: str) -> str:
    if not _SAFE_TOKEN.match(value or ""):
        raise PathTraversal(f"{field} must be a plain id, not a path: {value!r}")
    return value


def _find_source(root: Path, source_id: str) -> Source:
    d = store_root(root) / "shoots"
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            shoot, _rev = store_module.read(root, "shoot", f.stem)
            for source in shoot.sources:
                if source.id == source_id:
                    return source
    raise HTTPException(status_code=404, detail=f"no source {source_id!r}")


def _range_response(path: Path, request: Request, media_type: str, etag: str) -> Response:
    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    headers = {"Accept-Ranges": "bytes", "ETag": etag}
    if not range_header:
        return FileResponse(path, media_type=media_type, headers=headers)

    match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not match:
        raise HTTPException(status_code=416, detail="malformed Range header")
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        raise HTTPException(status_code=416, detail="Range not satisfiable")
    length = end - start + 1

    def _iter():
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            chunk_size = 1 << 20
            while remaining > 0:
                chunk = fh.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers.update({
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(length),
    })
    return StreamingResponse(_iter(), status_code=206, media_type=media_type, headers=headers)


@router.get("/{source_id}/proxy")
def media_proxy(source_id: str, request: Request, root: Path = Depends(get_project_root)) -> Response:
    _safe_token(source_id, "source_id")
    source = _find_source(root, source_id)
    if not source.proxy_path:
        raise HTTPException(status_code=404, detail=f"source {source_id!r} has no proxy built yet")
    path = Path(source.proxy_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"proxy file missing on disk: {path}")
    return _range_response(path, request, "video/mp4", etag=source.content_fingerprint)


@router.get("/{source_id}/audio")
def media_audio(source_id: str, request: Request, root: Path = Depends(get_project_root)) -> Response:
    _safe_token(source_id, "source_id")
    source = _find_source(root, source_id)
    if not source.audio_proxy_path:
        raise HTTPException(status_code=404, detail=f"source {source_id!r} has no audio proxy built yet")
    path = Path(source.audio_proxy_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"audio proxy file missing on disk: {path}")
    return _range_response(path, request, "audio/mp4", etag=source.content_fingerprint)


@router.get("/{source_id}/peaks")
def media_peaks(source_id: str, root: Path = Depends(get_project_root)) -> Response:
    _safe_token(source_id, "source_id")
    source = _find_source(root, source_id)
    if not source.peaks_path:
        raise HTTPException(status_code=404, detail=f"source {source_id!r} has no peaks built yet")
    path = Path(source.peaks_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"peaks file missing on disk: {path}")
    return FileResponse(path, media_type="application/octet-stream",
                         headers={"ETag": source.content_fingerprint})


def _find_asset(root: Path, content_hash: str) -> Optional[Path]:
    artifacts_dir = store_root(root) / "artifacts"
    if not artifacts_dir.is_dir():
        return None
    for manifest_path in artifacts_dir.glob("*/*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for output in manifest.get("outputs", []):
            if output.get("sha256") == content_hash:
                candidate = manifest_path.parent / output["path"]
                if candidate.is_file():
                    return candidate
    return None


assets_router = APIRouter(prefix="/api/projects/{pid}/assets", tags=["assets"])


@assets_router.get("/{content_hash}")
def get_asset(content_hash: str, root: Path = Depends(get_project_root)) -> Response:
    _safe_token(content_hash, "content_hash")
    path = _find_asset(root, content_hash)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no asset with content hash {content_hash!r}")
    return FileResponse(path, headers={"ETag": content_hash})


__all__ = ["router", "assets_router"]
