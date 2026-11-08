"""Per-cut undo/redo stacks, stored on disk at `cuts/<cut_id>.undo.json`.

A snapshot is a full Cut document (as of just before an edit was applied). `record`
pushes one before an edit lands and clears the redo stack (a fresh edit invalidates any
previously undone future). The stack is capped at 100 entries; older snapshots are
dropped. `undo`/`redo` move the *currently stored* cut between the two stacks and write
the restored version back to `cuts/<cut_id>.json` through the normal revisioned `write`,
so an undo can itself hit a RevisionConflict if something else wrote the cut meanwhile.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..model.cut import Cut
from .atomic import locked, read_envelope, write_envelope
from .errors import StoreError
from .paths import undo_path
from .store import read as store_read
from .store import write as store_write

CAP = 100


class NothingToUndo(StoreError):
    pass


class NothingToRedo(StoreError):
    pass


def _read_stacks(path: Path) -> tuple[int, list[dict], list[dict]]:
    revision, data = read_envelope(path)
    if data is None:
        return 0, [], []
    undo_stack = data.get("undo", [])
    redo_stack = data.get("redo", [])
    if not isinstance(undo_stack, list) or not isinstance(redo_stack, list):
        from .errors import CorruptFile

        raise CorruptFile(str(path), "undo file must have list undo/redo stacks")
    return revision, undo_stack, redo_stack


def _write_stacks(path: Path, revision: int, undo_stack: list[dict], redo_stack: list[dict]) -> int:
    new_rev = revision + 1
    write_envelope(path, new_rev, {"undo": undo_stack[-CAP:], "redo": redo_stack[-CAP:]})
    return new_rev


def record(project_root: str | Path, cut_id: str, snapshot: dict[str, Any]) -> None:
    """Push `snapshot` (a Cut's data, pre-edit) onto the undo stack; clear the redo stack."""
    path = undo_path(project_root, cut_id)
    with locked(path):
        revision, undo_stack, _redo_stack = _read_stacks(path)
        undo_stack.append(snapshot)
        _write_stacks(path, revision, undo_stack, [])


def undo(project_root: str | Path, cut_id: str) -> Cut:
    """Restore the most recent undo snapshot, writing it back as the current cut."""
    path = undo_path(project_root, cut_id)
    with locked(path):
        revision, undo_stack, redo_stack = _read_stacks(path)
        if not undo_stack:
            raise NothingToUndo(f"No undo history for cut {cut_id!r}")
        previous_data = undo_stack.pop()
        current, current_rev = store_read(project_root, "cut", cut_id)
        redo_stack.append(current.model_dump(mode="json"))
        restored = Cut.model_validate(previous_data)
        store_write(project_root, "cut", restored, current_rev)
        _write_stacks(path, revision, undo_stack, redo_stack)
    return restored


def redo(project_root: str | Path, cut_id: str) -> Cut:
    """Re-apply the most recently undone snapshot."""
    path = undo_path(project_root, cut_id)
    with locked(path):
        revision, undo_stack, redo_stack = _read_stacks(path)
        if not redo_stack:
            raise NothingToRedo(f"No redo history for cut {cut_id!r}")
        next_data = redo_stack.pop()
        current, current_rev = store_read(project_root, "cut", cut_id)
        undo_stack.append(current.model_dump(mode="json"))
        restored = Cut.model_validate(next_data)
        store_write(project_root, "cut", restored, current_rev)
        _write_stacks(path, revision, undo_stack, redo_stack)
    return restored
