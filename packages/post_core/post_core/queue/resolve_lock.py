"""Cross-process resource locks (ARCHITECTURE.md; ported idea from the old app's single
global `RESOLVE_LOCK`, `~/cc/post/backend/app/jobs.py`): DaVinci Resolve's scripting API is
one connection with mutable current-timeline/current-folder state, so two jobs touching it
at once interleave instead of colliding loudly.

T06 carry-over #3 replaces the old magic-lane-name approach (a hardcoded `{"resolve"}` lane
set) with `NodeType.resources` (graph/types.py): any node type can declare it needs one or
more named exclusive resources held for its whole run, and `executor.py` takes a flock per
declared resource rather than keying off the lane it happens to run in. `resolve_lock` is
kept as the well-known name for the one resource every real node type will actually declare
today (`resources=("resolve",)`); it is a thin wrapper over the generic `resource_lock`.

Reuses the store's own flock primitive (`store/atomic.locked`) so the lock behaves exactly
like every other cross-process lock in the app and is trivially tested across two real
processes.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..store.atomic import locked
from ..store.paths import store_root


def resource_lock_path(project_root: str | Path, name: str) -> Path:
    return store_root(project_root) / "queue" / "resources" / f"{name}.lock"


@contextmanager
def resource_lock(project_root: str | Path, name: str) -> Iterator[None]:
    """Hold the named cross-process resource lock for the duration of the `with` block."""
    with locked(resource_lock_path(project_root, name)):
        yield


def resolve_lock_path(project_root: str | Path) -> Path:
    return resource_lock_path(project_root, "resolve")


@contextmanager
def resolve_lock(project_root: str | Path) -> Iterator[None]:
    with resource_lock(project_root, "resolve"):
        yield
