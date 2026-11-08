"""T05: the durable job queue + executor (ARCHITECTURE.md §1). SQLite (`db.py`) holds the
queue only; disk artifact dirs stay the source of truth (`artifacts.py` writes them)."""
from __future__ import annotations

from . import db
from .artifacts import finalize_success, mark_failed
from .db import connect, db_path, open_db
from .budget import get_budget, set_budget
from .enqueue import Authorization, SpendNotAuthorized, enqueue
from .executor import DEFAULT_LANES, DEFAULT_RETRY_SECONDS, Executor
from .resolve_lock import resolve_lock, resolve_lock_path

__all__ = [
    "db",
    "connect",
    "db_path",
    "open_db",
    "Authorization",
    "SpendNotAuthorized",
    "enqueue",
    "set_budget",
    "get_budget",
    "finalize_success",
    "mark_failed",
    "Executor",
    "DEFAULT_LANES",
    "DEFAULT_RETRY_SECONDS",
    "resolve_lock",
    "resolve_lock_path",
]
