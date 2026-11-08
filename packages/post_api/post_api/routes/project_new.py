"""T34: a new project from local recordings, over HTTP. `POST /api/projects/new` validates
(refusing a bad folder before anything is written), registers the project and starts the
ingest job (`ingest_jobs.py`: the same `post_core.project_new` op as `post project new`),
answering 202 with the job id; progress streams on `GET .../events?workflow=_ingest`.
`GET .../ingest/status` is what the web Ingest page renders from; `.../ingest/run` re-runs
(idempotent: finished steps skip), `.../ingest/transcript` imports a transcript file, and
`.../ingest/open-editor` makes the first cut if there is none. T39: `company` puts the project in
the media library (`routes/library.py` lists the companies). T35: each recording also reports its
latest transcription job (`routes/transcribe.py` queues one)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from post_core import brand as brand_mod
from post_core.ingest.audio_proxy import is_valid_audio_proxy
from post_core.ingest.transcribe import job as transcribe_job
from post_core.library import LibraryError
from post_core.project_new import NewProjectError, RootPlacementError, validate_request
from post_core.project_new import steps as steps_mod
from post_core.store import store as store_module
from post_core.store.paths import store_root

from ..deps import get_project_root
from ..ingest_jobs import IngestAlreadyRunning
from ..models import ProjectRef

router = APIRouter(tags=["ingest"])


class NewProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # T39: either `company` (the project is `<library>/<company>/<name>/`) or `root`.
    root: Optional[str] = None
    company: Optional[str] = None
    copy_sources: bool = False
    sources: list[str]
    transcripts: list[str] = []
    brand_kit: Optional[str] = None


class NewProjectOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectRef
    job_id: str


class IngestJobOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    state: str
    summary: Optional[str] = None


class IngestSourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    shoot_id: str
    sync_group_id: str
    name: str
    path: str
    audio_ready: bool
    peaks_ready: bool
    transcript_id: Optional[str] = None
    words: int = 0
    # T35: this recording's latest transcription job (queued/running/ok/failed/...), if any.
    transcribe_job: Optional[IngestJobOut] = None


class IngestStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    root: str
    brand_kit: str
    job: Optional[IngestJobOut] = None
    sources: list[IngestSourceOut]
    cut_ids: list[str]
    audio_ready: bool
    has_transcript: bool


class ImportTranscriptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sync_group_id: str
    path: str
    format: Optional[str] = None


def _bad(message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


def _absolute(paths: list[str], what: str) -> list[str]:
    for raw in paths:
        if not Path(raw).expanduser().is_absolute():
            raise _bad(f"The {what} {raw!r} must be a full path (starting with / or ~).")
    return paths


@router.post("/api/projects/new", response_model=NewProjectOut, status_code=202)
def new_project(body: NewProjectRequest, request: Request) -> NewProjectOut:
    company = (body.company or "").strip() or None
    if company is None:
        _absolute([body.root or ""], "project folder")
    _absolute(body.sources, "recording")
    _absolute(body.transcripts, "transcript")
    try:
        root = validate_request(None if company else body.root, body.sources, body.transcripts, body.brand_kit,
                                name=body.name.strip(), company=company)
    except (NewProjectError, RootPlacementError, brand_mod.UnknownKit, LibraryError) as exc:
        raise _bad(str(exc)) from exc
    store_module.init_project(root)  # the job's own `init` step writes project.json
    entry = request.app.state.registry.add(root, name=body.name.strip() or root.name)
    request.app.state.runtimes.open(entry["id"], root)
    params = {"root": str(root), "name": body.name.strip() or root.name, "sources": body.sources,
              "transcripts": body.transcripts, "brand_kit": body.brand_kit, "company": company,
              "copy": body.copy_sources}
    try:
        job_id = request.app.state.ingest_jobs.start(root, params)
    except IngestAlreadyRunning as exc:
        raise _bad(str(exc), 409) from exc
    return NewProjectOut(project=ProjectRef(**entry), job_id=job_id)


@router.post("/api/projects/{pid}/ingest/run", response_model=IngestJobOut, status_code=202)
def rerun(request: Request, root: Path = Depends(get_project_root)) -> IngestJobOut:
    """Run the project's last ingest again: finished steps skip, failed/missing ones run."""
    jobs = request.app.state.ingest_jobs
    latest = jobs.latest(root)
    if latest is None:
        raise _bad("This project has no ingest to run again; start one from the New project page.")
    try:
        job_id = jobs.start(root, json.loads(latest["cmd_json"]))
    except IngestAlreadyRunning as exc:
        raise _bad(str(exc), 409) from exc
    return IngestJobOut(id=job_id, state="running")


def _job_out(row: Optional[dict]) -> Optional[IngestJobOut]:
    return IngestJobOut(id=row["id"], state=row["state"], summary=row["summary"]) if row else None


@router.get("/api/projects/{pid}/ingest/status", response_model=IngestStatusOut)
def ingest_status(request: Request, root: Path = Depends(get_project_root)) -> IngestStatusOut:
    project, _rev = store_module.try_read(root, "project")
    latest = request.app.state.ingest_jobs.latest(root)
    transcripts = steps_mod.transcripts_by_group(root)
    sources: list[IngestSourceOut] = []
    shoots_dir = store_root(root) / "shoots"
    for f in sorted(shoots_dir.glob("*.json")) if shoots_dir.is_dir() else []:
        shoot, _ = store_module.read(root, "shoot", f.stem)
        for source in shoot.sources:
            if source.kind != "real":
                continue
            group = steps_mod.group_of(shoot, source.id)
            transcript = transcripts.get(group.id)
            sources.append(IngestSourceOut(
                source_id=source.id, shoot_id=shoot.id, sync_group_id=group.id, name=Path(source.path).name,
                path=source.path, audio_ready=bool(source.audio_proxy_path and is_valid_audio_proxy(source.audio_proxy_path)),
                peaks_ready=bool(source.peaks_path and Path(source.peaks_path).is_file()),
                transcript_id=transcript.id if transcript else None, words=len(transcript.words) if transcript else 0,
                transcribe_job=_job_out(transcribe_job.latest_job(root, group.id)),
            ))
    cuts_dir = store_root(root) / "cuts"
    cut_ids = sorted(p.stem for p in cuts_dir.glob("*.json") if not p.name.endswith(".undo.json")) if cuts_dir.is_dir() else []
    return IngestStatusOut(
        name=project.name if project else root.name,
        root=str(root), brand_kit=brand_mod.project_kit_id(root),
        job=_job_out(latest),
        sources=sources, cut_ids=cut_ids,
        audio_ready=bool(sources) and all(s.audio_ready for s in sources),
        has_transcript=any(s.transcript_id for s in sources),
    )


@router.post("/api/projects/{pid}/ingest/transcript", response_model=IngestSourceOut)
def import_transcript(body: ImportTranscriptIn, request: Request,
                      root: Path = Depends(get_project_root)) -> IngestSourceOut:
    """Import a finished transcript file (JSON/SRT/VTT) for one recording. Free -- never a
    provider call. Refuses a recording that already has one."""
    _absolute([body.path], "transcript")
    status = ingest_status(request, root)
    source = next((s for s in status.sources if s.sync_group_id == body.sync_group_id), None)
    if source is None:
        raise _bad(f"This project has no recording in sync group {body.sync_group_id!r}.", 404)
    if source.transcript_id:
        raise _bad(f"{source.name} already has a transcript.", 409)
    path = Path(body.path).expanduser()
    if not path.is_file():
        raise _bad(f"Can't find the transcript {path}.")
    try:
        transcript = steps_mod.import_transcript(root, source.shoot_id, source.sync_group_id, path, body.format)
    except (ValueError, KeyError) as exc:
        raise _bad(f"Couldn't read the transcript {path.name}: {exc}") from exc
    return source.model_copy(update={"transcript_id": transcript.id, "words": len(transcript.words)})


class OpenEditorOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cut_id: str
    created: bool


@router.post("/api/projects/{pid}/ingest/open-editor", response_model=OpenEditorOut)
def open_editor(root: Path = Depends(get_project_root)) -> OpenEditorOut:
    try:
        cut_id, created = steps_mod.ensure_first_cut(root)
    except steps_mod.NoTranscript as exc:
        raise _bad(str(exc)) from exc
    return OpenEditorOut(cut_id=cut_id, created=created)


__all__ = ["router"]
