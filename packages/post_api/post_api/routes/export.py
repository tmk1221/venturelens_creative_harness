"""`POST /api/projects/{pid}/cuts/{cut_id}/export/otio` -- only if `post_core.export` (the
`opentimelineio` extra) is importable; otherwise a clear 501, not an ImportError traceback."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_project_root
from ..models import ExportOut

router = APIRouter(prefix="/api/projects/{pid}/cuts", tags=["export"])


class ExportRequest(BaseModel):
    version: Optional[int] = None
    patch_since: Optional[int] = None


@router.post("/{cut_id}/export/otio", response_model=ExportOut)
def export_otio(cut_id: str, body: ExportRequest, root: Path = Depends(get_project_root)) -> ExportOut:
    try:
        from post_core.export import otio_export
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail=(
                "post_core.export is not importable -- install the 'export' extra "
                "(pip install 'post_core[export]'; see docs/HANDOFF.md for the macOS/3.14 "
                f"opentimelineio workaround): {exc}"
            ),
        ) from exc

    try:
        if body.patch_since is not None:
            path = otio_export.patch_export(root, cut_id, body.patch_since)
        else:
            path = otio_export.export_cut(root, cut_id, version=body.version)
    except otio_export.ExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExportOut(cut_id=cut_id, path=str(path))


__all__ = ["router"]
