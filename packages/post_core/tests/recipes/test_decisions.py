"""T30b: Decisions rows derived from graph states across a cut."""
from __future__ import annotations

from post_core import store
from post_core.cli.context import save_workflow
from post_core.model import CastEntry
from post_core.model.common import Rational, WordAnchor
from post_core.model.cut import Cut, Span
from post_core.recipes import cast as cast_mod
from post_core.recipes.decisions import counts_by_kind, decisions_for_cut
from post_core.recipes.instantiate import SpanSpec, instantiate


def _anchor(word_id: str) -> WordAnchor:
    return WordAnchor(transcript_id="t1", word_id=word_id)


def test_decisions_waiting_on_unready_cast(project_root):
    span = Span(
        layer="picture", kind="live_action", start_anchor=_anchor("w0"), end_anchor=_anchor("w5"),
        cast_refs=["Dave"],
    )
    cut = Cut(aspect=Rational(num=16, den=9), spans=[span])
    rows = decisions_for_cut(project_root, cut)
    assert len(rows) == 1
    assert rows[0].kind == "waiting_on"
    assert "Dave" in rows[0].cause


def test_decisions_no_waiting_on_once_cast_anchor_approved(project_root):
    from post_core.graph import approvals as approvals_mod

    entry = CastEntry(name="Dave", kind="character", anchor_content_hash="deadbeef")
    cast_mod.upsert_cast(project_root, entry)
    approvals_mod.approve(project_root, "deadbeef", by="test")

    span = Span(
        layer="picture", kind="live_action", start_anchor=_anchor("w0"), end_anchor=_anchor("w5"),
        cast_refs=["Dave"],
    )
    cut = Cut(aspect=Rational(num=16, den=9), spans=[span])
    rows = decisions_for_cut(project_root, cut)
    assert rows == []


def test_decisions_pick_and_approve_rows_from_a_real_workflow(project_root, kit):
    workflow_span = SpanSpec(id="beat1", variants=2)
    workflow = instantiate("live_action", workflow_span, kit, None, project_root)
    save_workflow(project_root, workflow, expected_rev=0)

    span = Span(
        layer="picture", kind="live_action", start_anchor=_anchor("w0"), end_anchor=_anchor("w5"),
        workflow_id=workflow.id,
    )
    cut = Cut(aspect=Rational(num=16, den=9), spans=[span])
    rows = decisions_for_cut(project_root, cut)
    kinds = {r.kind for r in rows}
    assert "pick" in kinds
    picks = [r for r in rows if r.kind == "pick"]
    assert picks[0].node_id == "beat1-pick"
    assert picks[0].link == f"span:{span.id}/node:beat1-pick"

    counts = counts_by_kind(rows)
    assert counts["pick"] == 1
    assert counts["approve"] == 0


def test_decisions_ignores_orphaned_spans(project_root):
    span = Span(
        layer="picture", kind="live_action", start_anchor=_anchor("w0"), end_anchor=_anchor("w5"),
        cast_refs=["Dave"], orphaned=True,
    )
    cut = Cut(aspect=Rational(num=16, den=9), spans=[span])
    assert decisions_for_cut(project_root, cut) == []
