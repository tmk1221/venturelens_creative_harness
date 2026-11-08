"""The only persistence layer: `read(kind, id)` / `write(kind, obj, expected_rev)`.

Disk JSON is the source of truth (per AGENTS.md). Every object file is a
`{"revision": int, "data": {...}}` envelope, written atomically under a per-file flock.
`write` refuses (RevisionConflict) unless the caller's `expected_rev` matches what is on
disk right now, so two writers can never silently clobber each other — the loser gets a
typed error and must reload. Writing a `cut` additionally validates the cross-object
invariants in `invariants.py` against every Transcript on disk before it is allowed to land.
"""
from __future__ import annotations

from pathlib import Path
from typing import Type

from pydantic import BaseModel, ValidationError

from ..model.asset import Approval, Asset
from ..model.base import Entity
from ..model.cast import CastEntry
from ..model.cut import Cut
from ..model.project import Project
from ..model.shoot import Shoot
from ..model.transcript import Transcript
from .atomic import locked, read_envelope, write_envelope
from .errors import CorruptFile, NotFound, RevisionConflict
from .invariants import validate_cut_invariants
from .paths import ensure_layout, object_path, store_root

# "cast" (T12) joins the kinds this module persists directly. "workflow" (T12 carry-over
# #1) is deliberately NOT a module-level entry here: `graph/__init__.py` imports
# `graph.approvals`, which imports `from ..store import add_approval, read_approvals` (this
# package's own `__init__`, which imports this module) -- a module-level
# `from ..graph.workflow import Workflow` here would be a real import cycle
# (store -> graph -> store). `_model_for` resolves "workflow" with a local import instead,
# which only runs after both packages have finished initialising.
KIND_MODELS: dict[str, Type[Entity]] = {
    "project": Project,
    "shoot": Shoot,
    "transcript": Transcript,
    "cut": Cut,
    "asset": Asset,
    "cast": CastEntry,
}


def _model_for(kind: str) -> Type[Entity]:
    if kind == "workflow":
        from ..graph.workflow import Workflow

        return Workflow
    try:
        return KIND_MODELS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown store kind: {kind!r}") from exc


def _validate(model_cls: Type[BaseModel], path: Path, data: dict) -> BaseModel:
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise CorruptFile(str(path), f"data does not match {model_cls.__name__}: {exc}") from exc


def init_project(project_root: str | Path) -> Path:
    """Create the `.post3/` layout under `project_root` if it doesn't exist yet."""
    return ensure_layout(project_root)


def read(project_root: str | Path, kind: str, obj_id: str | None = None) -> tuple[Entity, int]:
    """Return (object, revision). Raises NotFound or CorruptFile.

    Deliberately takes no lock (T23): every write lands via `atomic_write_bytes`'s
    temp-file-then-`os.replace`, so a concurrent reader always sees either the whole old
    file or the whole new one, never a partial write -- the lock exists only to serialise
    writers' read-check-write sequence, not to protect readers. A request handler (or any
    other long-lived reader) that never releases promptly must never be able to block a
    writer elsewhere by holding this object's `.lock` file (found 2026-09-21: an idle
    uvicorn worker held a cut's lock and blocked an external import for ~10 minutes).
    """
    model_cls = _model_for(kind)
    path = object_path(project_root, kind, obj_id)
    revision, data = read_envelope(path)
    if data is None:
        raise NotFound(kind, obj_id or kind)
    obj = _validate(model_cls, path, data)
    return obj, revision  # type: ignore[return-value]


def try_read(project_root: str | Path, kind: str, obj_id: str | None = None) -> tuple[Entity | None, int]:
    """Like `read`, but returns (None, 0) instead of raising NotFound."""
    try:
        return read(project_root, kind, obj_id)
    except NotFound:
        return None, 0


def write(project_root: str | Path, kind: str, obj: Entity, expected_rev: int) -> int:
    """Persist `obj`, refusing unless `expected_rev` matches the file's current revision.

    `expected_rev=0` means "this object must not already exist". Returns the new revision.
    """
    model_cls = _model_for(kind)
    if not isinstance(obj, model_cls):
        raise TypeError(f"write(kind={kind!r}, ...) expects a {model_cls.__name__}, got {type(obj).__name__}")
    obj_id = None if kind in ("project",) else obj.id
    path = object_path(project_root, kind, obj_id)
    with locked(path):
        current_rev, _ = read_envelope(path)
        if current_rev != expected_rev:
            raise RevisionConflict(kind, obj_id or kind, expected_rev, current_rev)
        if kind == "cut":
            transcripts = _load_all_transcripts(project_root)
            validate_cut_invariants(obj, transcripts)  # type: ignore[arg-type]
        new_rev = current_rev + 1
        write_envelope(path, new_rev, obj.model_dump(mode="json"))
    return new_rev


def _load_all_transcripts(project_root: str | Path) -> dict[str, Transcript]:
    root = store_root(project_root) / "transcripts"
    if not root.exists():
        return {}
    transcripts: dict[str, Transcript] = {}
    for file in sorted(root.glob("*.json")):
        transcript_id = file.stem
        obj, _ = read(project_root, "transcript", transcript_id)
        transcripts[transcript_id] = obj  # type: ignore[assignment]
    return transcripts


# --- approvals.json: an append-only list, not an object-per-file kind -----------------

def read_approvals(project_root: str | Path) -> tuple[int, list[Approval]]:
    """Pure read (T23): no lock -- see `read()`'s docstring."""
    path = object_path(project_root, "approvals")
    revision, data = read_envelope(path)
    if data is None:
        return 0, []
    items = data.get("items")
    if not isinstance(items, list):
        raise CorruptFile(str(path), "approvals.json data.items must be a list")
    approvals = [_validate(Approval, path, item) for item in items]
    return revision, approvals  # type: ignore[return-value]


def add_approval(project_root: str | Path, approval: Approval, expected_rev: int) -> int:
    path = object_path(project_root, "approvals")
    with locked(path):
        current_rev, data = read_envelope(path)
        if current_rev != expected_rev:
            raise RevisionConflict("approvals", approval.id, expected_rev, current_rev)
        items = list((data or {}).get("items", []))
        if any(item.get("id") == approval.id for item in items):
            raise ValueError(f"Approval {approval.id!r} already recorded")
        items.append(approval.model_dump(mode="json"))
        new_rev = current_rev + 1
        write_envelope(path, new_rev, {"items": items})
    return new_rev
