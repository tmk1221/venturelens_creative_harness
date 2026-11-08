"""`post cut new|show|op <name> --args json|undo|redo|derive`."""
from __future__ import annotations

import argparse
import functools
import json
from pathlib import Path

from ...edit import ops as ops_mod
from ...edit.session import EditSession
from ...model.common import Rational
from ...model.transcript import Transcript
from ...store import store as store_module
from ...store.errors import NotFound, StoreError
from ...store.paths import store_root
from ..context import resolve_project_root
from ..output import CLIError


def _report_dict(report: ops_mod.EditReport) -> dict:
    return {"affected_spans": report.affected_spans, "orphaned_spans": report.orphaned_spans}


def _parse_aspect(raw: str) -> Rational:
    if ":" in raw:
        num_s, den_s = raw.split(":", 1)
        return Rational(num=int(num_s), den=int(den_s))
    return Rational(num=int(raw), den=1)


def _load_all_transcripts(root: Path) -> dict[str, Transcript]:
    d = store_root(root) / "transcripts"
    out: dict[str, Transcript] = {}
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            obj, _rev = store_module.read(root, "transcript", f.stem)
            out[f.stem] = obj  # type: ignore[assignment]
    return out


def cut_new(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    try:
        transcript, _rev = store_module.read(root, "transcript", args.transcript)
    except NotFound as exc:
        raise CLIError(str(exc)) from exc
    cut = ops_mod.cut_from_transcript(transcript, args.angle, _parse_aspect(args.aspect))
    if args.variant_label:
        cut = cut.model_copy(update={"variant_label": args.variant_label})
    store_module.write(root, "cut", cut, expected_rev=0)
    return {"cut_id": cut.id}


def cut_show(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    try:
        cut, revision = store_module.read(root, "cut", args.cut)
    except NotFound as exc:
        raise CLIError(str(exc)) from exc
    return {"revision": revision, "cut": cut}


_OP_NAMES = (
    "delete_words", "restore_words", "insert_range", "move_passage", "move_words",
    "replace_range_with", "set_angle", "set_trim",
)


def cut_op(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    if args.name not in _OP_NAMES:
        raise CLIError(f"unknown cut op {args.name!r}; known ops: {', '.join(_OP_NAMES)}")
    try:
        op_kwargs = json.loads(args.op_args) if args.op_args else {}
    except json.JSONDecodeError as exc:
        raise CLIError(f"--args must be a JSON object: {exc}") from exc
    if not isinstance(op_kwargs, dict):
        raise CLIError("--args must be a JSON object")

    op_fn = functools.partial(getattr(ops_mod, args.name), **op_kwargs)
    session = EditSession(root, args.cut)
    try:
        report = session.apply(op_fn)
    except (StoreError, ValueError, KeyError, TypeError) as exc:
        raise CLIError(str(exc)) from exc
    return {"cut_id": args.cut, "report": _report_dict(report)}


def cut_undo(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    session = EditSession(root, args.cut)
    try:
        cut = session.undo()
    except StoreError as exc:
        raise CLIError(str(exc)) from exc
    return {"cut_id": cut.id}


def cut_redo(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    session = EditSession(root, args.cut)
    try:
        cut = session.redo()
    except StoreError as exc:
        raise CLIError(str(exc)) from exc
    return {"cut_id": cut.id}


def cut_derive(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    try:
        parent, _rev = store_module.read(root, "cut", args.parent)
    except NotFound as exc:
        raise CLIError(str(exc)) from exc
    try:
        passage_ids = json.loads(args.passage_ids)
    except json.JSONDecodeError as exc:
        raise CLIError(f"--passage-ids must be a JSON array: {exc}") from exc
    transcripts = _load_all_transcripts(root)
    try:
        derived, report = ops_mod.derive_cut(
            parent, transcripts, passage_ids, _parse_aspect(args.aspect), args.variant_label or "",
        )
    except (ValueError, KeyError) as exc:
        raise CLIError(str(exc)) from exc
    store_module.write(root, "cut", derived, expected_rev=0)
    return {"cut_id": derived.id, "parent_cut_id": parent.id, "report": _report_dict(report)}


__all__ = ["cut_new", "cut_show", "cut_op", "cut_undo", "cut_redo", "cut_derive"]
