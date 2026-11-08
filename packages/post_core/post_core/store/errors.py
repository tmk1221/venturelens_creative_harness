"""Store error types. All are refusals: on any of these, the file on disk is left untouched."""
from __future__ import annotations


class StoreError(Exception):
    """Base class for all store errors."""


class RevisionConflict(StoreError):
    """The caller's expected_rev did not match the file's current revision."""

    def __init__(self, kind: str, obj_id: str, expected_rev: int, actual_rev: int) -> None:
        self.kind = kind
        self.obj_id = obj_id
        self.expected_rev = expected_rev
        self.actual_rev = actual_rev
        super().__init__(
            f"{kind}/{obj_id}: expected revision {expected_rev}, found {actual_rev} "
            "(someone else wrote this object first; reload and retry)"
        )


class NotFound(StoreError):
    """No object of this kind/id exists in the store."""

    def __init__(self, kind: str, obj_id: str) -> None:
        self.kind = kind
        self.obj_id = obj_id
        super().__init__(f"{kind}/{obj_id}: not found")


class CorruptFile(StoreError):
    """The on-disk file is not valid JSON, not a valid envelope, or fails model validation."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: refused to read corrupt file ({reason})")


class InvariantError(StoreError):
    """A cross-object invariant failed (e.g. a Cut's passages/spans/anchors)."""
