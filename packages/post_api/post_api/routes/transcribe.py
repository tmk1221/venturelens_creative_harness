"""T35: `/api/projects/{pid}/ingest/transcribe` -- transcription is a paid, queued job, never a
blocking request. `GET .../estimate` prices one recording (its audio proxy's minutes x the
Deepgram rate, in `usd`); the web shows that, creates a budget capped at exactly that amount
(`PUT .../budgets/{id}`) and `POST`s here naming it. The core (`post_core.ingest.transcribe.job`)
refuses a missing/unknown/too-small budget before anything is queued; the project's runtime
then runs the job, and its `step`/`progress`/`result` events stream on `GET .../events`
(`?workflow=transcribe-<sync_group_id>`)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from post_core.ingest.transcribe import job as transcribe_job

from ..deps import get_project_root

router = APIRouter(prefix="/api/projects/{pid}/ingest/transcribe", tags=["ingest"])


class TranscribeEstimateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sync_group_id: str
    provider: str
    audio_path: str
    minutes: float
    usd_per_minute: float
    amount: Optional[float] = None
    unit: str


class TranscribeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sync_group_id: str
    provider: str = "deepgram"
    budget: Optional[str] = None
    by: Optional[str] = None


class TranscribeJobOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    workflow_id: str
    amount: Optional[float] = None
    unit: str


@router.get("/estimate", response_model=TranscribeEstimateOut)
def transcribe_estimate(
    sync_group_id: str = Query(...), provider: str = Query("deepgram"), root: Path = Depends(get_project_root),
) -> TranscribeEstimateOut:
    try:
        return TranscribeEstimateOut(**transcribe_job.estimate(root, sync_group_id, provider))
    except transcribe_job.TranscribeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=TranscribeJobOut, status_code=202)
def transcribe(body: TranscribeIn, root: Path = Depends(get_project_root)) -> TranscribeJobOut:
    """Queue it. No budget -> 402; an unknown budget -> 409; an estimate past the budget's
    headroom -> 402 (the app's spend handlers); no audio proxy -> 400; already has a
    transcript -> 409."""
    try:
        queued = transcribe_job.enqueue_transcription(
            root, body.sync_group_id, budget_id=body.budget, by=body.by or "api", provider=body.provider,
        )
    except transcribe_job.AlreadyTranscribed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except transcribe_job.TranscribeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TranscribeJobOut(**queued)


__all__ = ["router"]
