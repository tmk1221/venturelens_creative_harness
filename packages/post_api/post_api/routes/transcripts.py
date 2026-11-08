"""`/api/projects/{pid}/transcripts/{tid}`: metadata, and `/words` paged by range (T10
spec: "words paged by range for long transcripts" -- a multi-hour transcript's word list is
too big to ship in one response). T35: `/speakers` lists and names the speakers."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from post_core.edit.heuristics import find_filler_words, find_long_silences
from post_core.ingest.transcribe import job as transcribe_job, speakers as speakers_mod
from post_core.model.shoot import clean_audio_source
from post_core.store import store as store_module

from ..deps import get_project_root
from ..models import SuggestionOut, TranscriptMetaOut, TranscriptShowOut, TranscriptWordsPage, WordOut

router = APIRouter(prefix="/api/projects/{pid}/transcripts", tags=["transcripts"])

MAX_PAGE = 2000


@router.get("/{transcript_id}", response_model=TranscriptShowOut)
def show_transcript(transcript_id: str, root: Path = Depends(get_project_root)) -> TranscriptShowOut:
    transcript, revision = store_module.read(root, "transcript", transcript_id)
    meta = TranscriptMetaOut(
        id=transcript.id, schema_version=transcript.schema_version,
        sync_group_id=transcript.sync_group_id, provider=transcript.provider,
        fingerprint=transcript.fingerprint,
    )
    return TranscriptShowOut(revision=revision, transcript=meta, word_count=len(transcript.words))


@router.get("/{transcript_id}/words", response_model=TranscriptWordsPage)
def transcript_words(
    transcript_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=MAX_PAGE),
    root: Path = Depends(get_project_root),
) -> TranscriptWordsPage:
    transcript, _revision = store_module.read(root, "transcript", transcript_id)
    words = [
        WordOut(
            id=w.id, schema_version=w.schema_version, text=w.text, start=w.start,
            end=w.end, speaker=w.speaker, confidence=w.confidence,
        )
        for w in transcript.words[offset:offset + limit]
    ]
    return TranscriptWordsPage(
        transcript_id=transcript_id, total=len(transcript.words),
        offset=offset, limit=limit, words=words,
    )


@router.get("/{transcript_id}/suggestions", response_model=list[SuggestionOut])
def transcript_suggestions(
    transcript_id: str, kind: str = Query("all", pattern="^(all|filler|silence)$"),
    root: Path = Depends(get_project_root),
) -> list[SuggestionOut]:
    """'Remove fillers' / 'Remove long silences' candidate ranges. Never auto-applied --
    the client turns an accepted one into a normal `delete_words` op."""
    transcript, _revision = store_module.read(root, "transcript", transcript_id)
    suggestions = []
    if kind in ("all", "filler"):
        suggestions += find_filler_words(transcript)
    if kind in ("all", "silence"):
        suggestions += find_long_silences(transcript)
    return [
        SuggestionOut(
            sync_group_id=s.sync_group_id, start_word_id=s.start_word_id,
            end_word_id=s.end_word_id, kind=s.kind, reason=s.reason,
        )
        for s in suggestions
    ]


class SpeakerSampleOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: float
    end: float
    text: str


class SpeakerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    name: Optional[str] = None
    words: int
    sample: SpeakerSampleOut


class SpeakersOut(BaseModel):
    """T35: each speaker label, its name (None until someone names it) and its longest
    utterance as a sample. `source_id` is the recording whose audio proxy plays the samples
    (`GET .../media/{source_id}/audio`)."""

    model_config = ConfigDict(extra="forbid")

    transcript_id: str
    revision: int
    source_id: Optional[str] = None
    speakers: list[SpeakerOut]


class SpeakersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    names: dict[str, str]  # label -> name; an empty name un-names that speaker


def _speakers_out(root: Path, transcript_id: str) -> SpeakersOut:
    transcript, revision = store_module.read(root, "transcript", transcript_id)
    try:
        shoot, group = transcribe_job.find_group(root, transcript.sync_group_id)
        source_id: Optional[str] = clean_audio_source(shoot, group).id
    except (transcribe_job.TranscribeError, ValueError):
        source_id = None
    return SpeakersOut(transcript_id=transcript.id, revision=revision, source_id=source_id,
                       speakers=[SpeakerOut(**s) for s in speakers_mod.summary(transcript)])


@router.get("/{transcript_id}/speakers", response_model=SpeakersOut)
def transcript_speakers(transcript_id: str, root: Path = Depends(get_project_root)) -> SpeakersOut:
    return _speakers_out(root, transcript_id)


@router.put("/{transcript_id}/speakers", response_model=SpeakersOut)
def name_speakers(transcript_id: str, body: SpeakersIn, root: Path = Depends(get_project_root)) -> SpeakersOut:
    """Rename everywhere: the names live on the transcript, every label shows them."""
    try:
        speakers_mod.set_names(root, transcript_id, body.names)
    except speakers_mod.UnknownSpeaker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _speakers_out(root, transcript_id)


__all__ = ["router"]
