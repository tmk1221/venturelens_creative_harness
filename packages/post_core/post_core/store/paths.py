"""The on-disk project layout.

    <root>/.post3/
        project.json
        approvals.json
        shoots/<id>.json
        transcripts/<id>.json
        cuts/<id>.json
        workflows/<id>.json
        assets/<id>.json
        cuts/<id>.undo.json   (undo/redo stacks, one per cut)
"""
from __future__ import annotations

from pathlib import Path

# kind -> subdirectory holding one file per object id, or None for a singleton file.
KIND_DIRS: dict[str, str | None] = {
    "project": None,
    "approvals": None,
    "shoot": "shoots",
    "transcript": "transcripts",
    "cut": "cuts",
    "workflow": "workflows",
    "asset": "assets",
    "cast": "casts",
}

# kind -> filename, for singleton kinds only (KIND_DIRS[kind] is None).
SINGLETON_FILES: dict[str, str] = {
    "project": "project.json",
    "approvals": "approvals.json",
}


def store_root(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".post3"


def ensure_layout(project_root: str | Path) -> Path:
    root = store_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    for kind, subdir in KIND_DIRS.items():
        if subdir is not None:
            (root / subdir).mkdir(parents=True, exist_ok=True)
    return root


def object_path(project_root: str | Path, kind: str, obj_id: str | None = None) -> Path:
    if kind not in KIND_DIRS:
        raise ValueError(f"Unknown store kind: {kind!r}")
    root = store_root(project_root)
    subdir = KIND_DIRS[kind]
    if subdir is None:
        return root / SINGLETON_FILES[kind]
    if not obj_id:
        raise ValueError(f"Store kind {kind!r} requires an object id")
    return root / subdir / f"{obj_id}.json"


def lock_path(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".lock")


def undo_path(project_root: str | Path, cut_id: str) -> Path:
    return store_root(project_root) / "cuts" / f"{cut_id}.undo.json"
