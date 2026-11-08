"""T41: the project's brand kit as a live style guide for the Ingest page's Brand panel.

`GET /api/projects/{pid}/brand` says which kit and its current signature (the panel polls it
and reloads when the kit's files change); `.../brand/index.html` and `.../brand/tokens.css`
are the kit's design-system page rendered in memory (`post_core.brand_page`, re-rendered on
change); anything else under `.../brand/` is a file from the kit's `design-system/` folder
(logos, the approved look), confined to that folder. Read-only: nothing here writes, least of
all into the kit."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, ConfigDict

from post_core import brand as brand_mod
from post_core import brand_page as page_mod

from ..deps import get_project_root

router = APIRouter(prefix="/api/projects/{pid}/brand", tags=["brand"])

# The page is the kit's own HTML: never let it run script, even opened outside the iframe.
_HEADERS = {"Cache-Control": "no-store", "Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"}


class BrandPageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kit_id: str
    signature: str
    page_url: str
    approved_looks: list[str]


def _page(root: Path) -> page_mod.BrandPage:
    try:
        return page_mod.page(root)
    except (brand_mod.UnknownKit, page_mod.NoDesignSystem) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=BrandPageOut)
def brand_info(pid: str, root: Path = Depends(get_project_root)) -> BrandPageOut:
    p = _page(root)
    return BrandPageOut(kit_id=p.kit_id, signature=p.signature, page_url=f"/api/projects/{pid}/brand/index.html",
                        approved_looks=list(p.approved_looks))


@router.get("/index.html", response_class=HTMLResponse)
def brand_index(root: Path = Depends(get_project_root)) -> HTMLResponse:
    p = _page(root)
    return HTMLResponse(p.html, headers={**_HEADERS, "ETag": f'"{p.signature}"'})


@router.get("/tokens.css")
def brand_tokens(root: Path = Depends(get_project_root)) -> Response:
    p = _page(root)
    return Response(p.css, media_type="text/css", headers={**_HEADERS, "ETag": f'"{p.signature}"'})


@router.get("/{rel:path}")
def brand_asset(rel: str, root: Path = Depends(get_project_root)) -> FileResponse:
    try:
        path = page_mod.asset_path(root, rel)
    except (brand_mod.UnknownKit, page_mod.NoDesignSystem, page_mod.OutsideKit, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=f"no such brand file: {rel}") from exc
    return FileResponse(path, headers=_HEADERS)


__all__ = ["router"]
