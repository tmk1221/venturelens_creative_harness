"""Approve/revoke a content hash, via the store's append-only approvals ledger.

`store.add_approval` / `store.read_approvals` already give us an append-only ledger of
`Approval(content_hash, by, at)` records (asset.py, T02) -- that covers "approve" directly.
The ledger has no delete, so "revoke" is tracked separately here as a small revocation set
next to it (`<root>/.post3/graph/revocations.json`, same atomic-write/lock primitives the
store itself uses). A hash is approved iff a ledger record names it and it is not in the
revocation set; approving again clears any prior revocation for that same hash. A node
whose params/upstream change gets a brand new content hash automatically, with no entry in
either file -- that's what makes "approval bound to content hash invalidates on new output"
true for free.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from ..model.asset import Approval
from ..store import add_approval, read_approvals
from ..store.atomic import locked, read_envelope, write_envelope
from ..store.paths import store_root


def _revocations_path(project_root: str | Path) -> Path:
    return store_root(project_root) / "graph" / "revocations.json"


def _revoked_hashes(project_root: str | Path) -> set[str]:
    path = _revocations_path(project_root)
    with locked(path):
        _, data = read_envelope(path)
    return set((data or {}).get("hashes", []))


def _set_revoked(project_root: str | Path, content_hash: str, revoked: bool) -> None:
    path = _revocations_path(project_root)
    with locked(path):
        rev, data = read_envelope(path)
        hashes = set((data or {}).get("hashes", []))
        if revoked:
            hashes.add(content_hash)
        else:
            hashes.discard(content_hash)
        write_envelope(path, rev + 1, {"hashes": sorted(hashes)})


def approve(project_root: str | Path, content_hash: str, by: str, at: Optional[float] = None) -> Approval:
    approval = Approval(content_hash=content_hash, by=by, at=at if at is not None else time.time())
    rev, _ = read_approvals(project_root)
    add_approval(project_root, approval, expected_rev=rev)
    _set_revoked(project_root, content_hash, revoked=False)
    return approval


def revoke(project_root: str | Path, content_hash: str) -> None:
    _set_revoked(project_root, content_hash, revoked=True)


def is_approved(project_root: str | Path, content_hash: str) -> bool:
    if content_hash in _revoked_hashes(project_root):
        return False
    _, approvals = read_approvals(project_root)
    return any(a.content_hash == content_hash for a in approvals)
