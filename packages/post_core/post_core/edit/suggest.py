"""T13b/T30b: the automated "Suggest visuals" pass -- generate proposals for a whole cut / a
section / a selection, validate them, store them as `Suggestion`s (never as `Span`s), and let
a caller accept (-> a real `add_beat_spans`, T30b: creates the picture and/or overlay Span the
proposal describes) or dismiss (-> remembered so it is never re-suggested) one, or accept
every unblocked pending proposal at once.

Chunking: `_sentences_in_range` splits the scope's words into sentences on end-of-sentence
punctuation (falling back to one chunk if none is found), which is what gets sent to the
provider -- "chunk long transcripts by section" from the spec, done at sentence grain so a
whole-cut run on a long transcript still sends bounded-size chunks.

T36: real mode (anything but `POST3_FAKE_PROVIDERS=1`) asks a terminal agent
(`suggest_provider.AgentSuggestProvider`). Its context adds the cut's own words grouped by
section and the neighbouring beats (`suggest_context`), and the brand writer context defaults
to the project's own kit (`post_core.brand`). Whatever the agent says is still only a
proposal: validated here, stored as a `Suggestion`, never as a `Span`.

T42: a run replaces the pending proposals inside its scope instead of stacking on them, two
ideas for the same words become one proposal with variants, and the project's `picture_mode`
decides the prompt and, in `audio_only`, guarantees full picture coverage (`suggest_coverage`).
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from ..model.common import WordAnchor
from ..model.cut import Cut
from ..recipes import cast as cast_mod
from ..recipes.models import fake_mode
from ._reconcile import TranscriptsArg, index_of
from ._spans import add_beat_spans
from .ranges import TranscriptIndex
from .session import EditSession
from ..picture_mode import project_picture_mode
from .suggest_coverage import merge_same_range, tile_audio_only
from .suggest_edit import switch_variant, update_suggestion
from .suggest_models import SuggestError, Suggestion, SuggestionsFile, dismissed_key, layers_for
from .suggest_context import neighbouring_beats, split_sentences, transcript_by_section
from .suggest_provider import (
    AgentSuggestProvider,
    DeterministicSuggester,
    SuggestProvider,
    parse_suggest_response,
)
from .suggest_store import read_suggestions, update_suggestions

ScopeKind = Literal["cut", "selection"]


@dataclass(frozen=True)
class Scope:
    kind: ScopeKind
    sync_group_id: str
    start_word_id: str
    end_word_id: str


def _sentences_in_range(index: TranscriptIndex, sync_group_id: str, start_i: int, end_i: int) -> list[dict]:
    words = index.words(sync_group_id)[start_i : end_i + 1]
    return [{"words": sentence["words"]} for sentence in split_sentences(words)]


def _span_index_ranges(cut: Cut, index: TranscriptIndex) -> dict[str, list[tuple[int, int, str]]]:
    """Existing spans' (start_i, end_i, layer), keyed by sync_group_id, for overlap checks."""
    by_group: dict[str, list[tuple[int, int, str]]] = {}
    for span in cut.spans:
        if span.orphaned:
            continue
        try:
            sync_group_id = index.sync_group_of(span.start_anchor.transcript_id)
            s = index.index_of(sync_group_id, span.start_anchor.word_id)
            e = index.index_of(sync_group_id, span.end_anchor.word_id)
        except KeyError:
            continue
        by_group.setdefault(sync_group_id, []).append((s, e, span.layer))
    return by_group


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def _parse_proposal(raw: dict) -> Optional[dict]:
    """Best-effort shape/type validation of one raw proposal dict -- returns `None` (dropped,
    never surfaced) for anything malformed, exactly like the old kind/brief check did."""
    medium = raw.get("medium")
    overlay = raw.get("overlay") if isinstance(raw.get("overlay"), dict) else None
    brief = str(raw.get("brief", "")).strip()
    if not brief or (medium is None and overlay is None):
        return None
    if medium is not None and medium not in ("aroll", "provided", "live_action", "motion_graphic"):
        return None
    overlay_depth = overlay_position = None
    if overlay is not None:
        overlay_depth = overlay.get("depth")
        overlay_position = overlay.get("position")
        if overlay_depth not in ("in_front", "behind") or not overlay_position:
            return None
    flags = [f for f in raw.get("flags", []) if isinstance(f, str)] if isinstance(raw.get("flags"), list) else []
    cast_refs = [c for c in raw.get("cast_refs", []) if isinstance(c, str)] if isinstance(raw.get("cast_refs"), list) else []
    return {
        "medium": medium, "overlay_depth": overlay_depth, "overlay_position": overlay_position,
        "brief": brief, "direction_note": str(raw.get("direction_note", "")).strip(),
        "rationale": str(raw.get("rationale", "")).strip(), "flags": flags, "cast_refs": cast_refs,
        "density_hint": raw.get("density_hint"),
    }


def _pending_index(index: TranscriptIndex, sync_group_id: str, s: Suggestion) -> Optional[tuple[int, int]]:
    try:
        if index.sync_group_of(s.start_anchor.transcript_id) != sync_group_id:
            return None
        return index.index_of(sync_group_id, s.start_anchor.word_id), index.index_of(sync_group_id, s.end_anchor.word_id)
    except KeyError:
        return None


def pending_inside_scope(index: TranscriptIndex, scope: Scope, items: list[Suggestion]) -> set[str]:
    """T42: ids of the pending proposals wholly inside `scope` -- the ones a run over it replaces."""
    start_i = index.index_of(scope.sync_group_id, scope.start_word_id)
    end_i = index.index_of(scope.sync_group_id, scope.end_word_id)
    out = set()
    for s in items:
        r = _pending_index(index, scope.sync_group_id, s)
        if r is not None and start_i <= r[0] and r[1] <= end_i:
            out.add(s.id)
    return out


def _for_audio_only(suggestion: Suggestion) -> Optional[Suggestion]:
    """T42: no aroll, no overlay-only beat (every beat is a picture), no behind overlay."""
    if suggestion.medium is None or suggestion.medium == "aroll":
        return None
    if suggestion.overlay_depth == "behind":
        return suggestion.model_copy(update={"overlay_depth": None, "overlay_position": None})
    return suggestion


def generate_suggestions(
    project_root: str | Path,
    cut: Cut,
    transcripts: TranscriptsArg,
    scope: Scope,
    provider: Optional[SuggestProvider] = None,
    writer_context: Optional[dict] = None,
    picture_mode: Optional[str] = None,
) -> list[Suggestion]:
    """Pure-ish: reads the suggestions file for dismissed keys/existing pending ranges, calls
    `provider`, validates every proposal (anchors exist, within scope, not previously
    dismissed, no same-layer overlap with existing spans or pending suggestions OUTSIDE the
    scope -- T42: the ones inside it are about to be replaced), folds same-range ideas into
    variants and, in `audio_only` mode, tiles the scope (`suggest_coverage`). Returns only the
    NEW `Suggestion`s (does not persist -- `suggest_visuals` does)."""
    index = index_of(transcripts)
    transcript = index.transcript_for(scope.sync_group_id)
    start_i = index.index_of(scope.sync_group_id, scope.start_word_id)
    end_i = index.index_of(scope.sync_group_id, scope.end_word_id)
    if start_i > end_i:
        raise SuggestError("scope start_word_id must come at or before end_word_id")

    provider = provider or (DeterministicSuggester() if fake_mode() else AgentSuggestProvider(project_root))
    if writer_context is None:
        from ..brand import project_writer_context

        writer_context = project_writer_context(project_root)
    if picture_mode is None:
        picture_mode = project_picture_mode(project_root)
    audio_only = picture_mode == "audio_only"
    existing_file = read_suggestions(project_root, cut.id)
    replaced = pending_inside_scope(index, scope, existing_file.items)
    kept_pending = [s for s in existing_file.items if s.id not in replaced]
    context = dict(writer_context)
    context["sentences"] = _sentences_in_range(index, scope.sync_group_id, start_i, end_i)
    context["sections"] = transcript_by_section(cut, index, scope.sync_group_id, start_i, end_i)
    context["neighbours"] = neighbouring_beats(cut, index, kept_pending, scope.sync_group_id, start_i, end_i)
    context["scope"] = scope.kind
    context["picture_mode"] = picture_mode
    context["cast"] = [c.name for c in cast_mod.list_cast(project_root)]
    raw = provider.draft(context)
    raw_proposals = parse_suggest_response(raw)

    dismissed = set(existing_file.dismissed_keys)
    pending_ranges = list(_span_index_ranges(cut, index).get(scope.sync_group_id, []))
    for s in kept_pending:
        r = _pending_index(index, scope.sync_group_id, s)
        if r is not None:
            pending_ranges.extend((r[0], r[1], layer) for layer in layers_for(s))

    candidates: list[tuple[int, int, Suggestion]] = []
    for raw_proposal in raw_proposals:
        try:
            p_start_id = str(raw_proposal["start_word_id"])
            p_end_id = str(raw_proposal["end_word_id"])
            p_start_i = index.index_of(scope.sync_group_id, p_start_id)
            p_end_i = index.index_of(scope.sync_group_id, p_end_id)
        except (KeyError, TypeError, ValueError):
            continue  # anchors don't exist / malformed proposal -- dropped, never surfaced
        if p_start_i > p_end_i or p_start_i < start_i or p_end_i > end_i:
            continue  # out of scope
        if dismissed_key(p_start_id, p_end_id) in dismissed:
            continue

        parsed = _parse_proposal(raw_proposal)
        if parsed is None:
            continue
        try:
            suggestion = Suggestion(
                start_anchor=WordAnchor(transcript_id=transcript.id, word_id=p_start_id),
                end_anchor=WordAnchor(transcript_id=transcript.id, word_id=p_end_id),
                **parsed,
            )
        except ValueError:
            continue  # e.g. an overlay position illegal for its own medium+depth
        if audio_only and (suggestion := _for_audio_only(suggestion)) is None:
            continue
        candidates.append((p_start_i, p_end_i, suggestion))
    candidates = merge_same_range(candidates)

    if audio_only:
        blocked = [(s, e) for s, e, layer in pending_ranges if layer == "picture"]
        words = index.words(scope.sync_group_id)
        candidates = tile_audio_only(candidates, start_i, end_i, blocked, [w.id for w in words],
                                     [w.text for w in words], transcript.id)

    accepted: list[Suggestion] = []
    for p_start_i, p_end_i, suggestion in candidates:
        proposed_layers = layers_for(suggestion)
        clash = [layer for layer in proposed_layers
                 if any(layer == lay and _overlaps(p_start_i, p_end_i, s, e) for s, e, lay in pending_ranges)]
        if audio_only and clash == ["overlay"]:  # the picture is guaranteed; its overlay is not
            suggestion = suggestion.model_copy(update={"overlay_depth": None, "overlay_position": None})
            proposed_layers, clash = ["picture"], []
        if clash:
            continue
        accepted.append(suggestion)
        pending_ranges.extend((p_start_i, p_end_i, layer) for layer in proposed_layers)
    return accepted


def suggest_visuals(
    project_root: str | Path,
    cut_id: str,
    transcripts: TranscriptsArg,
    scope: Scope,
    cut: Optional[Cut] = None,
    provider: Optional[SuggestProvider] = None,
    writer_context: Optional[dict] = None,
    picture_mode: Optional[str] = None,
) -> list[Suggestion]:
    """Generate + persist. Returns the full pending list for `cut_id` after the run. T42: the
    run replaces the pending proposals wholly inside the scope (one proposal per passage);
    pending ones elsewhere stay, and accepted beats (spans) are never touched."""
    if cut is None:
        from ..store import store as store_module
        cut, _rev = store_module.read(project_root, "cut", cut_id)
    new_items = generate_suggestions(project_root, cut, transcripts, scope, provider, writer_context, picture_mode)
    index = index_of(transcripts)

    def _apply(file: SuggestionsFile) -> SuggestionsFile:
        replaced = pending_inside_scope(index, scope, file.items)
        return file.model_copy(update={"items": [*(s for s in file.items if s.id not in replaced), *new_items]})

    updated = update_suggestions(project_root, cut_id, _apply)
    return updated.items


def accept_suggestion(project_root: str | Path, cut_id: str, suggestion_id: str) -> tuple[Cut, Suggestion]:
    """Turn one pending suggestion into real `Span`s (validated the same way any manual "Add
    visual" is -- same-layer overlap refused with the conflicting span named) and drop it
    from the suggestions store. T30b: a suggestion carrying both a medium and an overlay
    creates BOTH layers in one atomic op (`add_beat_spans`). Raises `SuggestError` if the
    suggestion is gone, or whatever `add_beat_spans`/invariant error the underlying op raises
    if it now conflicts."""
    from ..store import store as store_module

    file = read_suggestions(project_root, cut_id)
    suggestion = next((s for s in file.items if s.id == suggestion_id), None)
    if suggestion is None:
        raise SuggestError(f"No pending suggestion {suggestion_id!r}")

    transcript, _rev = store_module.read(project_root, "transcript", suggestion.start_anchor.transcript_id)
    op_fn = functools.partial(
        add_beat_spans,
        sync_group_id=transcript.sync_group_id,
        start_word_id=suggestion.start_anchor.word_id,
        end_word_id=suggestion.end_anchor.word_id,
        picture_kind=suggestion.medium,
        brief_text=suggestion.brief,
        direction_note=suggestion.direction_note,
        flags=suggestion.flags,
        cast_refs=suggestion.cast_refs,
        density_hint=suggestion.density_hint,
        overlay_depth=suggestion.overlay_depth,
        overlay_position=suggestion.overlay_position,
        provenance="agent",
    )
    session = EditSession(project_root, cut_id)
    session.apply(op_fn)

    def _drop(f: SuggestionsFile) -> SuggestionsFile:
        return f.model_copy(update={"items": [s for s in f.items if s.id != suggestion_id]})

    update_suggestions(project_root, cut_id, _drop)
    new_cut, _rev = store_module.read(project_root, "cut", cut_id)
    return new_cut, suggestion


def dismiss_suggestion(project_root: str | Path, cut_id: str, suggestion_id: str) -> Suggestion:
    """Drop a pending suggestion and remember its word range so `generate_suggestions` never
    proposes it again."""
    holder: dict[str, Suggestion] = {}

    def _drop(f: SuggestionsFile) -> SuggestionsFile:
        suggestion = next((s for s in f.items if s.id == suggestion_id), None)
        if suggestion is None:
            raise SuggestError(f"No pending suggestion {suggestion_id!r}")
        holder["s"] = suggestion
        key = dismissed_key(suggestion.start_anchor.word_id, suggestion.end_anchor.word_id)
        return f.model_copy(update={
            "items": [s for s in f.items if s.id != suggestion_id],
            "dismissed_keys": [*f.dismissed_keys, key],
        })

    update_suggestions(project_root, cut_id, _drop)
    return holder["s"]


@dataclass(frozen=True)
class AcceptAllResult:
    accepted: list[str]
    blocked: list[str]


def accept_all(project_root: str | Path, cut_id: str) -> AcceptAllResult:
    """Accept every currently-pending suggestion, in transcript order, skipping (not failing
    on) any that no longer validate -- e.g. two proposals that would now land on the same
    layer once the first is accepted. Header text ("Accept all (N)") is this call's
    `len(accepted)` plus a note of `len(blocked)`."""
    from ..store import store as store_module
    from ..store.paths import store_root

    file = read_suggestions(project_root, cut_id)
    transcripts_dir = store_root(project_root) / "transcripts"
    index: Optional[TranscriptIndex] = None
    if transcripts_dir.is_dir():
        loaded = [store_module.read(project_root, "transcript", f.stem)[0] for f in sorted(transcripts_dir.glob("*.json"))]
        index = TranscriptIndex(loaded)

    def _sort_key(s: Suggestion) -> tuple[int, str]:
        if index is None:
            return (0, s.start_anchor.word_id)
        try:
            sync_group_id = index.sync_group_of(s.start_anchor.transcript_id)
            return (index.index_of(sync_group_id, s.start_anchor.word_id), s.id)
        except KeyError:
            return (10**9, s.id)

    ordered = sorted(file.items, key=_sort_key)
    accepted: list[str] = []
    blocked: list[str] = []
    for suggestion in ordered:
        try:
            accept_suggestion(project_root, cut_id, suggestion.id)
            accepted.append(suggestion.id)
        except Exception:
            blocked.append(suggestion.id)
    return AcceptAllResult(accepted=accepted, blocked=blocked)


__all__ = [
    "Scope", "SuggestError", "generate_suggestions", "suggest_visuals",
    "accept_suggestion", "dismiss_suggestion", "update_suggestion", "switch_variant", "accept_all",
    "AcceptAllResult", "pending_inside_scope",
]
