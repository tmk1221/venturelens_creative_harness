"""Real-mode Higgsfield CLI calls, shared by `still_generate`/`endframe_generate`/
`video_generate`. Never imported by a fake-mode code path, and never exercised by this
repo's tests (POST3_FAKE_PROVIDERS=1 always short-circuits before these run).

UNVERIFIED ASSUMPTIONS -- a human must check these against a real (authorised) call before
the first paid run; `~/.claude/skills/higgsfield/SKILL.md` documents the commands below but
not their exact JSON, beyond the two examples it happens to show:
  - `generate create <model> ... --wait --json` returns either a bare array of id strings
    (no `--wait`) or "full objects" (with `--wait`) -- SKILL.md's own wording, but it never
    shows a full object's shape. This module assumes the object (or, once fetched via
    `generate wait`) carries a `media`/`output`/`url` field with a downloadable URL; it
    checks several likely key names and fails loudly (`HiggsfieldShapeError`) if none match,
    rather than guessing.
  - `upload create <png> --json` returns `{"id": "<uuid>"}` (per SKILL.md's one example).
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional


class HiggsfieldShapeError(RuntimeError):
    """A Higgsfield CLI response didn't match this module's assumed (unverified) shape."""


def upload_image(png_path: Path) -> str:
    out = subprocess.run(
        ["higgsfield", "upload", "create", str(png_path), "--json"],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    uid = data.get("id")
    if not uid:
        raise HiggsfieldShapeError(f"upload create: no 'id' in {data!r}")
    return uid


_URL_KEYS = ("url", "media_url", "output_url", "download_url")


def _find_url(obj: dict) -> str:
    for key in _URL_KEYS:
        if obj.get(key):
            return str(obj[key])
    media = obj.get("media") or obj.get("output")
    if isinstance(media, dict):
        for key in _URL_KEYS:
            if media.get(key):
                return str(media[key])
    if isinstance(media, list) and media:
        return _find_url(media[0]) if isinstance(media[0], dict) else str(media[0])
    raise HiggsfieldShapeError(f"generate create: no known url field in {obj!r}")


def generate(model: str, args: list[str]) -> dict:
    """`generate create <model> <args> --wait --json` -- THE paid call. Returns the finished
    job object; `download` fetches its media. Split from the download (T31) so a worker can
    record the cost the moment this returns, even if the download then fails."""
    out = subprocess.run(
        ["higgsfield", "generate", "create", model, *args, "--wait", "--json"],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    obj = data[0] if isinstance(data, list) else data
    if isinstance(obj, str):
        # `--wait` should return full objects per SKILL.md, but guard the id-only shape too.
        wait_out = subprocess.run(
            ["higgsfield", "generate", "wait", obj, "--timeout", "25m", "--interval", "10s", "--json"],
            check=True, capture_output=True, text=True,
        )
        obj = json.loads(wait_out.stdout)
        obj = obj[0] if isinstance(obj, list) else obj
    if not isinstance(obj, dict):
        raise HiggsfieldShapeError(f"generate create: expected an object, got {obj!r}")
    return obj


# UNVERIFIED: no documented field carries a job's charged credits. Only explicitly cost-named
# keys are read (never e.g. `credits`, which could be an account balance); anything else
# means "not reported" and the worker records its pre-call estimate instead.
_COST_KEYS = ("cost", "credits_spent", "credits_used")


def reported_cost(obj: dict) -> Optional[float]:
    """The amount the provider says this job cost, if it says so; None otherwise."""
    for key in _COST_KEYS:
        value = obj.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
    return None


def download(obj: dict, dest: Path) -> None:
    url = _find_url(obj)
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)  # noqa: S310 -- deliberate, real-mode-only download


__all__ = ["upload_image", "generate", "reported_cost", "download", "HiggsfieldShapeError"]
