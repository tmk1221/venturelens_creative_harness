"""Pydantic response models for routes that don't already return a post_core model
(Project/Shoot/Transcript/Cut/Workflow -- those are used directly as `response_model`).
Keeps the OpenAPI contract typed end to end without duplicating post_core's own models.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from post_core.model.common import Rational
from post_core.model.cut import Cut

# T42: the Suggest-visuals shapes live in their own module; re-exported here.
from .suggest_models import AcceptAllOut, AcceptSuggestionOut, SuggestionVariantOut, SuggestVisualsResult, VisualSuggestionOut


class ProjectRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    root: str
    name: str


class ProjectList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projects: list[ProjectRef]


class RevisionedCut(BaseModel):
    model_config = ConfigDict(extra="allow")

    revision: int
    cut: dict


class CutSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    aspect: Rational
    variant_label: str
    parent_cut_id: Optional[str] = None
    passage_count: int


class CutShowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int
    cut: Cut


class TranscriptMetaOut(BaseModel):
    """A Transcript's metadata without its (possibly huge) `words` list -- see `/words` for
    those, paged."""

    model_config = ConfigDict(extra="forbid")

    id: str
    schema_version: int
    sync_group_id: str
    provider: str
    fingerprint: str


class TranscriptShowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int
    transcript: TranscriptMetaOut
    word_count: int


class WordOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    schema_version: int
    text: str
    start: float
    end: float
    speaker: str
    confidence: float


class EditReportOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affected_spans: list[str]
    orphaned_spans: list[str]


class CutOpResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cut_id: str
    revision: int
    report: EditReportOut


class ProbeOut(BaseModel):
    model_config = ConfigDict(extra="allow")


class SourceAddOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shoot_id: str
    source_id: str
    sync_group_id: str
    probe: dict


class TimelineSegmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passage_id: str
    sync_group_id: str
    angle_source_id: str
    audio_source_id: str
    source_start: float
    source_end: float
    start_frame: int
    duration_frames: int


class SwapCandidateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sync_group_id: str
    start_word_id: str
    end_word_id: str
    text: str
    score: float


class SuggestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sync_group_id: str
    start_word_id: str
    end_word_id: str
    kind: str
    reason: str


class TranscriptWordsPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript_id: str
    total: int
    offset: int
    limit: int
    words: list[WordOut]


class WorkflowRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str


class PlanOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    plan: dict


class StatesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    states: dict[str, str]


class RunOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    job_ids: list[str]
    plan: dict


class SpanWorkflowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_id: str
    workflow_id: str
    recipe_id: str


class NodeUpdateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    node_id: str
    revision: int


class EdgeOpOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    revision: int
    edges: list[dict]


class NodeTypeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    inputs: list[dict]
    outputs: list[dict]
    spends: bool
    lane: str
    uses_brand_kit: bool
    params_schema: dict


class ModelOptionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    label: str = ""  # T39: Higgsfield's `display_name` (`higgsfield model list`)
    pricing: dict
    # T30d: plain-word chips ("start frame"/"end frame"/"refs"/"max Ns") for the in-node and
    # inspector model pickers -- see `post_core.recipes.models.capabilities_for`.
    capabilities: list[str] = []


class NodeRegistryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_types: list[NodeTypeOut]
    handle_types: list[str]
    models: list[ModelOptionOut]


class CastEntryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: str
    description: str
    anchor_ready: bool
    anchor_asset_path: Optional[str] = None


class CastListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cast: list[CastEntryOut]


class ProvidedClipOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    label: str
    duration_seconds: float


class ProvidedCatalogueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clips: list[ProvidedClipOut]


class JobOut(BaseModel):
    model_config = ConfigDict(extra="allow")


class QueueListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: list[dict]


class QueueShowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: dict
    events: list[dict]


class CancelOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    cancelled: bool


class ApprovalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str
    by: str
    at: float


class RevokeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str
    revoked: bool


class BudgetOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget: dict


class ExportOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cut_id: str
    path: str


class ErrorOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    error: str


class DoctorOut(BaseModel):
    model_config = ConfigDict(extra="allow")


class DecisionRowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    span_id: str
    node_id: Optional[str] = None
    cause: str
    link: str


class DecisionsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[DecisionRowOut]
    counts: dict[str, int]


class MoreVariantsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    node_ids: list[str]
    revision: int


__all__ = [
    "ProjectRef", "ProjectList", "RevisionedCut", "EditReportOut", "CutOpResult",
    "ProbeOut", "SourceAddOut", "TranscriptWordsPage", "WorkflowRef", "PlanOut",
    "StatesOut", "RunOut", "JobOut", "QueueListOut", "QueueShowOut", "CancelOut",
    "ApprovalOut", "RevokeOut", "BudgetOut", "ExportOut", "ErrorOut", "DoctorOut",
    "TimelineSegmentOut", "SwapCandidateOut", "SuggestionOut",
    "CutShowOut", "TranscriptMetaOut", "TranscriptShowOut", "WordOut", "CutSummaryOut",
    "SpanWorkflowOut", "NodeUpdateOut", "EdgeOpOut", "NodeTypeOut", "ModelOptionOut",
    "NodeRegistryOut", "VisualSuggestionOut", "SuggestVisualsResult", "AcceptSuggestionOut",
    "AcceptAllOut", "DecisionRowOut", "DecisionsOut", "MoreVariantsOut",
    "CastEntryOut", "CastListOut", "ProvidedClipOut", "ProvidedCatalogueOut",
]
