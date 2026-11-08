"""`GET /api/doctor` and `GET /api/projects/{pid}/doctor` -- booleans only, never a secret
value (same contract as `post doctor`: `post_core.cli.config.doctor_report` never returns key
values), plus T31's `providers: fake|real` so the web shell can show when clicks spend."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from post_core.cli import config as config_mod

from ..deps import get_project_root
from ..models import DoctorOut

router = APIRouter(prefix="/api/projects/{pid}", tags=["doctor"])
global_router = APIRouter(prefix="/api", tags=["doctor"])


@router.get("/doctor", response_model=DoctorOut)
def doctor(root: Path = Depends(get_project_root)) -> dict:
    return config_mod.doctor_report(root)


@global_router.get("/doctor", response_model=DoctorOut)
def doctor_global() -> dict:
    """No project needed: what the shell reads once to decide on its REAL badge."""
    return config_mod.doctor_report()


__all__ = ["router", "global_router"]
