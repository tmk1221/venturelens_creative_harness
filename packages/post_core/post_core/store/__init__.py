"""The only persistence layer for post_core. Disk JSON is the source of truth."""
from . import undo
from .errors import CorruptFile, InvariantError, NotFound, RevisionConflict, StoreError
from .invariants import validate_cut_invariants
from .paths import ensure_layout, object_path, store_root
from .store import (
    add_approval,
    init_project,
    read,
    read_approvals,
    try_read,
    write,
)

__all__ = [
    "undo",
    "StoreError",
    "RevisionConflict",
    "NotFound",
    "CorruptFile",
    "InvariantError",
    "validate_cut_invariants",
    "ensure_layout",
    "object_path",
    "store_root",
    "init_project",
    "read",
    "try_read",
    "write",
    "read_approvals",
    "add_approval",
]
