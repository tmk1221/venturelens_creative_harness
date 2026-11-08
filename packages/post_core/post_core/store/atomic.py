"""Locking and atomic-write primitives shared by every store operation.

Every write: hold an exclusive cross-process flock on a sibling `.lock` file, write to a
temp file in the same directory, fsync it, then `os.replace` it over the target. Readers
never see a partial file. The lock is what makes read-check-write (revision compare) safe
across processes; `os.replace` alone is not enough because two writers could both pass the
revision check before either one's rename lands.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .errors import CorruptFile
from .paths import lock_path


@contextmanager
def locked(target: Path) -> Iterator[None]:
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path(target)
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def atomic_write_bytes(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.stem + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def read_envelope(path: Path) -> tuple[int, dict[str, Any] | None]:
    """Return (revision, data) for an object file, or (0, None) if it does not exist yet.

    Raises CorruptFile rather than returning a guess if the file exists but is unreadable,
    invalid JSON, or not a valid `{revision, data}` envelope — the file is left untouched.
    """
    if not path.exists():
        return 0, None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CorruptFile(str(path), f"unreadable: {exc}") from exc
    try:
        envelope = json.loads(raw)
    except ValueError as exc:
        raise CorruptFile(str(path), f"invalid JSON: {exc}") from exc
    if (
        not isinstance(envelope, dict)
        or not isinstance(envelope.get("revision"), int)
        or envelope["revision"] < 0
        or "data" not in envelope
        or not isinstance(envelope.get("data"), dict)
    ):
        raise CorruptFile(str(path), "not a valid {revision, data} envelope")
    return envelope["revision"], envelope["data"]


def write_envelope(path: Path, revision: int, data: dict[str, Any]) -> None:
    payload = json.dumps({"revision": revision, "data": data}, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write_bytes(path, payload.encode("utf-8"))
