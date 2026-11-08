"""`post export otio <cut>` -- only if `post_core.export` (the `opentimelineio` extra) is
importable; otherwise a clear, actionable error rather than an ImportError traceback."""
from __future__ import annotations

import argparse

from ..context import resolve_project_root
from ..output import CLIError


def export_otio(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    try:
        from ...export import otio_export
    except ImportError as exc:
        raise CLIError(
            "post_core.export is not importable -- install the 'export' extra "
            "(pip install 'post_core[export]'; see docs/HANDOFF.md for the opentimelineio "
            f"macOS/3.14 workaround): {exc}"
        ) from exc

    try:
        if args.patch_since is not None:
            path = otio_export.patch_export(root, args.cut, args.patch_since)
        else:
            path = otio_export.export_cut(root, args.cut, version=args.version)
    except otio_export.ExportError as exc:
        raise CLIError(str(exc)) from exc
    return {"cut_id": args.cut, "path": str(path)}


__all__ = ["export_otio"]
