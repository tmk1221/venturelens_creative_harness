"""Disk persistence for T13b suggestions: `<root>/.post3/suggestions/<cut_id>.json`, one file
per cut, same envelope/atomic-write/flock primitives as every other store kind (see
`store/atomic.py`) but deliberately NOT registered in `store/store.py`'s `KIND_MODELS` --
suggestions are provisional, never validated against Cut invariants, and never versioned by
`expected_rev` the way a Cut op is.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..store.atomic import locked, read_envelope, write_envelope
from ..store.paths import store_root
from .suggest_models import SuggestionsFile


def _path(project_root: str | Path, cut_id: str) -> Path:
    return store_root(project_root) / "suggestions" / f"{cut_id}.json"


def read_suggestions(project_root: str | Path, cut_id: str) -> SuggestionsFile:
    _revision, data = read_envelope(_path(project_root, cut_id))
    if data is None:
        return SuggestionsFile(cut_id=cut_id)
    return SuggestionsFile.model_validate(data)


def update_suggestions(
    project_root: str | Path, cut_id: str, fn: Callable[[SuggestionsFile], SuggestionsFile]
) -> SuggestionsFile:
    """Read-modify-write as one critical section (holds the file's flock for the whole
    read+`fn`+write), so two requests against the same cut's suggestions never race the way a
    plain read-then-separately-write would."""
    path = _path(project_root, cut_id)
    with locked(path):
        revision, data = read_envelope(path)
        current = SuggestionsFile(cut_id=cut_id) if data is None else SuggestionsFile.model_validate(data)
        updated = fn(current)
        write_envelope(path, revision + 1, updated.model_dump(mode="json"))
    return updated


__all__ = ["read_suggestions", "update_suggestions"]
