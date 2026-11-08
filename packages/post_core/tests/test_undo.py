"""Per-cut undo/redo: snapshot, undo, redo, and the 100-entry cap."""
from __future__ import annotations

from pathlib import Path

import pytest

from post_core import store
from post_core.model import Cut, Rational
from post_core.store import undo
from post_core.store.paths import undo_path


def test_undo_restores_previous_state(tmp_path: Path):
    store.init_project(tmp_path)
    cut = Cut(aspect=Rational(num=16, den=9), variant_label="v1")
    store.write(tmp_path, "cut", cut, expected_rev=0)

    undo.record(tmp_path, cut.id, cut.model_dump(mode="json"))
    edited = cut.model_copy(update={"variant_label": "v2"})
    store.write(tmp_path, "cut", edited, expected_rev=1)

    restored = undo.undo(tmp_path, cut.id)
    assert restored.variant_label == "v1"
    on_disk, _ = store.read(tmp_path, "cut", cut.id)
    assert on_disk.variant_label == "v1"


def test_redo_reapplies_undone_edit(tmp_path: Path):
    store.init_project(tmp_path)
    cut = Cut(aspect=Rational(num=16, den=9), variant_label="v1")
    store.write(tmp_path, "cut", cut, expected_rev=0)

    undo.record(tmp_path, cut.id, cut.model_dump(mode="json"))
    edited = cut.model_copy(update={"variant_label": "v2"})
    store.write(tmp_path, "cut", edited, expected_rev=1)

    undo.undo(tmp_path, cut.id)
    restored = undo.redo(tmp_path, cut.id)
    assert restored.variant_label == "v2"


def test_undo_with_empty_stack_raises(tmp_path: Path):
    store.init_project(tmp_path)
    cut = Cut(aspect=Rational(num=16, den=9))
    store.write(tmp_path, "cut", cut, expected_rev=0)
    with pytest.raises(undo.NothingToUndo):
        undo.undo(tmp_path, cut.id)


def test_undo_stack_capped_at_100(tmp_path: Path):
    store.init_project(tmp_path)
    cut = Cut(aspect=Rational(num=16, den=9))
    store.write(tmp_path, "cut", cut, expected_rev=0)
    for i in range(120):
        undo.record(tmp_path, cut.id, {**cut.model_dump(mode="json"), "variant_label": str(i)})
    _rev, undo_stack, _redo_stack = undo._read_stacks(undo_path(tmp_path, cut.id))
    assert len(undo_stack) == 100
    assert undo_stack[-1]["variant_label"] == "119"
    assert undo_stack[0]["variant_label"] == "20"
