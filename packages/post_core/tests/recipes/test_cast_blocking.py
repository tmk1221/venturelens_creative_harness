"""Acceptance: a beat naming a cast member blocks `instantiate` until that member has an
approved continuity anchor, then unblocks."""
from __future__ import annotations

import pytest

from post_core.graph import approvals
from post_core.model.cast import CastEntry
from post_core.recipes import cast as cast_mod
from post_core.recipes.instantiate import CastNotReady, SpanSpec, instantiate


def test_cast_anchor_blocks_then_unblocks(project_root, registry, kit):
    span = SpanSpec(id="beat-dave", continuity_names=["Dave"])

    with pytest.raises(CastNotReady) as exc:
        instantiate("live_action", span, kit, None, project_root)
    assert "Dave" in str(exc.value)

    entry = CastEntry(name="Dave", kind="character", anchor_content_hash="hash-dave-anchor")
    cast_mod.upsert_cast(project_root, entry)

    # An anchor recorded but not yet approved still isn't ready.
    with pytest.raises(CastNotReady):
        instantiate("live_action", span, kit, None, project_root)

    approvals.approve(project_root, "hash-dave-anchor", by="test")

    workflow = instantiate("live_action", span, kit, None, project_root)
    assert workflow.node("beat-dave-still0") is not None
