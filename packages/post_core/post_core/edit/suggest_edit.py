"""T40/T42: changing a pending proposal before it is accepted -- inline edits on its card
(`update_suggestion`) and switching between the ideas the agent offered for the same words
(`switch_variant`). Both re-validate the row as a whole and write it back under the
suggestions file's lock; accept later reads it from disk, so what the card shows is what
becomes the real Spans."""
from __future__ import annotations

from pathlib import Path

from .suggest_models import IDEA_FIELDS, SuggestError, Suggestion, SuggestionsFile
from .suggest_store import update_suggestions

_EDITABLE = ("brief", "direction_note", "medium")


def _rewrite(project_root: str | Path, cut_id: str, suggestion_id: str, change) -> Suggestion:
    holder: dict[str, Suggestion] = {}

    def _edit(f: SuggestionsFile) -> SuggestionsFile:
        current = next((s for s in f.items if s.id == suggestion_id), None)
        if current is None:
            raise SuggestError(f"No pending suggestion {suggestion_id!r}")
        try:
            edited = Suggestion.model_validate(change(current))
        except ValueError as e:
            raise SuggestError(str(e)) from e
        holder["s"] = edited
        return f.model_copy(update={"items": [edited if s.id == suggestion_id else s for s in f.items]})

    update_suggestions(project_root, cut_id, _edit)
    return holder["s"]


def update_suggestion(project_root: str | Path, cut_id: str, suggestion_id: str, changes: dict) -> Suggestion:
    """T40: edit a pending proposal -- only its brief, direction note and medium. The edited
    row is re-validated as a whole (a medium change can make the proposed overlay position
    illegal; that is refused, nothing written)."""
    unknown = set(changes) - set(_EDITABLE)
    if unknown:
        raise SuggestError(f"Cannot edit {sorted(unknown)} on a suggestion (editable: {list(_EDITABLE)})")
    return _rewrite(project_root, cut_id, suggestion_id, lambda current: {**current.model_dump(), **changes})


def switch_variant(project_root: str | Path, cut_id: str, suggestion_id: str, index: int) -> Suggestion:
    """T42: make variant `index` the proposal's active idea. The active idea's current fields
    (edits included) are kept in its own variant slot first, so switching back restores them."""
    def change(current: Suggestion) -> dict:
        if not 0 <= index < len(current.variants):
            raise SuggestError(f"Suggestion {suggestion_id!r} has no variant {index}")
        variants = [v.model_dump() for v in current.variants]
        variants[current.active_variant] = current.idea().model_dump()
        return {**current.model_dump(), **{k: variants[index][k] for k in IDEA_FIELDS},
                "variants": variants, "active_variant": index}

    return _rewrite(project_root, cut_id, suggestion_id, change)


__all__ = ["update_suggestion", "switch_variant"]
