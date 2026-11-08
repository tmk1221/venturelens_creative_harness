"""Apply an edit op to a stored Cut: validate invariants, persist with revision, push undo.

`EditSession` is the only bridge between the pure functions in `ops.py`/`ranges.py` and the
store (`post_core.store`). A caller builds a closure over one of the `ops` functions (binding
its non-`cut`/`transcripts` arguments) and hands it to `apply`; the session reads the current
cut and transcripts, runs the op, validates the result, writes it, and records an undo
snapshot of the pre-op cut.

Gesture coalescing: `begin_gesture()` / `end_gesture()` bracket a run of `apply` calls (e.g.
every intermediate frame of a trim-handle drag) that should land as a single undo step -- only
the snapshot from just before the first op in the gesture is pushed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..model.cut import Cut
from ..model.transcript import Transcript
from ..store import store as store_module
from ..store import undo as undo_module
from ..store.invariants import validate_cut_invariants
from ..store.paths import store_root
from .ops import EditReport
from .ranges import TranscriptIndex

OpFn = Callable[[Cut, TranscriptIndex], tuple[Cut, EditReport]]


def _load_all_transcripts(project_root: str | Path) -> dict[str, Transcript]:
    root = store_root(project_root) / "transcripts"
    transcripts: dict[str, Transcript] = {}
    if root.exists():
        for file in sorted(root.glob("*.json")):
            obj, _rev = store_module.read(project_root, "transcript", file.stem)
            transcripts[file.stem] = obj  # type: ignore[assignment]
    return transcripts


class EditSession:
    """One open editing session against a single stored Cut."""

    def __init__(self, project_root: str | Path, cut_id: str):
        self.project_root = project_root
        self.cut_id = cut_id
        self._gesture_depth = 0
        self._gesture_snapshot: dict[str, Any] | None = None

    def begin_gesture(self) -> None:
        """Open a coalesced-undo gesture. Nestable; only the outermost begin/end pair counts."""
        self._gesture_depth += 1
        if self._gesture_depth == 1:
            cut, _rev = store_module.read(self.project_root, "cut", self.cut_id)
            self._gesture_snapshot = cut.model_dump(mode="json")

    def end_gesture(self) -> None:
        if self._gesture_depth == 0:
            raise RuntimeError("end_gesture called without a matching begin_gesture")
        self._gesture_depth -= 1
        if self._gesture_depth == 0:
            self._gesture_snapshot = None

    def apply(self, op: OpFn) -> EditReport:
        """Run `op(cut, index)` against the current stored cut, persist the result, and record
        undo history (coalesced into the open gesture, if any)."""
        cut, revision = store_module.read(self.project_root, "cut", self.cut_id)
        transcripts = _load_all_transcripts(self.project_root)
        index = TranscriptIndex(transcripts.values())

        new_cut, report = op(cut, index)
        validate_cut_invariants(new_cut, transcripts)

        if self._gesture_depth > 0:
            snapshot = self._gesture_snapshot
            self._gesture_snapshot = None  # only the first op in a gesture pushes a snapshot
        else:
            snapshot = cut.model_dump(mode="json")

        store_module.write(self.project_root, "cut", new_cut, revision)
        if snapshot is not None:
            undo_module.record(self.project_root, self.cut_id, snapshot)
        return report

    def undo(self) -> Cut:
        return undo_module.undo(self.project_root, self.cut_id)

    def redo(self) -> Cut:
        return undo_module.redo(self.project_root, self.cut_id)
