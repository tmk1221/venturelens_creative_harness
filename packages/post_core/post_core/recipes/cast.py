"""Cast registry ops (T12 spec): read/write `CastEntry` rows, check anchor readiness.

A beat using a cast member (e.g. "Dave") before that entry has an *approved* anchor asset
is blocked on that beat's still pick -- `instantiate.py` calls `anchor_ready` while wiring
`still.generate` continuity inputs and marks the beat `needs_human` (not a crash) when it
isn't ready yet.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .. import store as store_mod
from ..graph.approvals import is_approved
from ..model.cast import CastEntry
from ..store.paths import store_root


def list_cast(project_root: str | Path) -> list[CastEntry]:
    cast_dir = store_root(project_root) / "casts"
    if not cast_dir.exists():
        return []
    out: list[CastEntry] = []
    for f in sorted(cast_dir.glob("*.json")):
        obj, _ = store_mod.read(project_root, "cast", f.stem)
        out.append(obj)  # type: ignore[arg-type]
    return out


def find_cast(project_root: str | Path, name: str) -> Optional[CastEntry]:
    return next((c for c in list_cast(project_root) if c.name == name), None)


def upsert_cast(project_root: str | Path, entry: CastEntry) -> CastEntry:
    _existing, rev = store_mod.try_read(project_root, "cast", entry.id)
    store_mod.write(project_root, "cast", entry, expected_rev=rev)
    return entry


def anchor_ready(project_root: str | Path, name: str) -> bool:
    """True iff cast entry `name` exists, has an anchor content hash, and that hash is
    approved (`graph.approvals.is_approved`) -- an anchor with no approval yet is "not
    ready", the same as no anchor at all."""
    entry = find_cast(project_root, name)
    if entry is None or not entry.anchor_content_hash:
        return False
    return is_approved(project_root, entry.anchor_content_hash)


__all__ = ["list_cast", "find_cast", "upsert_cast", "anchor_ready"]
