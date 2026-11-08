"""approve/revoke by content hash; a new content hash naturally has no approval."""
from __future__ import annotations

from pathlib import Path

from post_core.graph import approvals


def test_approve_then_is_approved(tmp_path: Path):
    assert approvals.is_approved(tmp_path, "hash-a") is False
    approvals.approve(tmp_path, "hash-a", by="travis")
    assert approvals.is_approved(tmp_path, "hash-a") is True


def test_new_output_hash_is_not_approved(tmp_path: Path):
    approvals.approve(tmp_path, "hash-a", by="travis")
    assert approvals.is_approved(tmp_path, "hash-a") is True
    assert approvals.is_approved(tmp_path, "hash-b") is False


def test_revoke_then_reapprove(tmp_path: Path):
    approvals.approve(tmp_path, "hash-a", by="travis")
    approvals.revoke(tmp_path, "hash-a")
    assert approvals.is_approved(tmp_path, "hash-a") is False
    approvals.approve(tmp_path, "hash-a", by="travis")
    assert approvals.is_approved(tmp_path, "hash-a") is True
