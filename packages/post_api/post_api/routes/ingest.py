"""`/api/projects/{pid}/ingest/...`: proxy, peaks, import-transcript. Mirrors `post ingest ...`
-- thin calls into `post_core.ingest`, same as the CLI. Transcription (paid) is a queued job
with its own estimate + authorised budget: `routes/transcribe.py` (T35)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from post_core.ingest import audio_proxy as audio_proxy_mod, peaks as peaks_mod, proxy as proxy_mod
from post_core.ingest.transcribe import importer
from post_core.ingest.transcribe.link import add_transcript
from post_core.model.shoot import Shoot
from post_core.store import store as store_module
from post_core.store.paths import store_root

from ..deps import get_project_root

router = APIRouter(prefix="/api/projects/{pid}/ingest", tags=["ingest"])


def _load_shoot_and_source(root: Path, shoot_id: str, source_id: str):
    shoot, revision = store_module.read(root, "shoot", shoot_id)
    source = next((s for s in shoot.sources if s.id == source_id), None)
    if source is None:
        raise HTTPException(status_code=404, detail=f"shoot {shoot_id!r} has no source {source_id!r}")
    return shoot, revision, source


def _write_source_update(root: Path, shoot: Shoot, revision: int, source_id: str, **fields) -> Shoot:
    new_sources = [s.model_copy(update=fields) if s.id == source_id else s for s in shoot.sources]
    updated = shoot.model_copy(update={"sources": new_sources})
    store_module.write(root, "shoot", updated, expected_rev=revision)
    return updated


class ProxyRequest(BaseModel):
    shoot: str
    source_id: str
    height: int = 720
    force: bool = False


@router.post("/proxy")
def ingest_proxy(body: ProxyRequest, root: Path = Depends(get_project_root)) -> dict:
    shoot, revision, source = _load_shoot_and_source(root, body.shoot, body.source_id)
    out_dir = store_root(root) / "proxies"
    try:
        out = proxy_mod.build_proxy(source.path, out_dir, source.content_fingerprint,
                                     height=body.height, force=body.force)
    except proxy_mod.ProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_source_update(root, shoot, revision, source.id, proxy_path=str(out))
    return {"source_id": source.id, "proxy_path": str(out)}


class AudioProxyRequest(BaseModel):
    shoot: str
    source_id: str
    force: bool = False


@router.post("/audio")
def ingest_audio(body: AudioProxyRequest, root: Path = Depends(get_project_root)) -> dict:
    shoot, revision, source = _load_shoot_and_source(root, body.shoot, body.source_id)
    out_dir = store_root(root) / "proxies"
    try:
        out = audio_proxy_mod.build_audio_proxy(source.path, out_dir, source.content_fingerprint, force=body.force)
    except audio_proxy_mod.AudioProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_source_update(root, shoot, revision, source.id, audio_proxy_path=str(out))
    return {"source_id": source.id, "audio_proxy_path": str(out)}


class PeaksRequest(BaseModel):
    shoot: str
    source_id: str
    rate: int = 100


@router.post("/peaks")
def ingest_peaks(body: PeaksRequest, root: Path = Depends(get_project_root)) -> dict:
    shoot, revision, source = _load_shoot_and_source(root, body.shoot, body.source_id)
    out_path = store_root(root) / "peaks" / f"{source.content_fingerprint}.peaks"
    try:
        out = peaks_mod.build_peaks(source.path, out_path, samples_per_sec=body.rate)
    except peaks_mod.PeaksError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_source_update(root, shoot, revision, source.id, peaks_path=str(out))
    return {"source_id": source.id, "peaks_path": str(out)}


class ImportTranscriptRequest(BaseModel):
    shoot: str
    sync_group: str
    path: str
    format: Optional[str] = None
    fingerprint: Optional[str] = None


@router.post("/import-transcript")
def ingest_import_transcript(body: ImportTranscriptRequest, root: Path = Depends(get_project_root)) -> dict:
    shoot, _revision = store_module.read(root, "shoot", body.shoot)
    if not any(body.sync_group == g.id for g in shoot.sync_groups):
        raise HTTPException(status_code=400, detail=f"shoot {body.shoot!r} has no sync group {body.sync_group!r}")

    text = Path(body.path).read_text(encoding="utf-8")
    fmt = body.format or importer.guess_format(body.path)
    try:
        words = importer.import_words(text, fmt)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    transcript = add_transcript(root, shoot.id, importer.words_to_transcript(
        words, sync_group_id=body.sync_group, provider=f"import:{fmt}",
        fingerprint=body.fingerprint or f"import:{Path(body.path).name}",
    ))
    return {"transcript_id": transcript.id, "sync_group_id": body.sync_group, "words": len(transcript.words)}


__all__ = ["router"]
