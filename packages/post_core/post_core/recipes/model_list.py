"""T39: every image and video model Higgsfield offers, for the card/graph model picker.

`higgsfield model list --json` (CLI 1.1.25, free and read-only) answers a flat list of
`{"display_name", "job_type", "type"}` (types: image, video, 3d, audio, data, text);
`fixtures/higgsfield/model_list.json` is that output verbatim. The picker shows image and
video models only, labelled with `display_name`. The list is cached per project in
`.post3/cache/higgsfield/model_list.json`; `refresh=True` asks the CLI again (the web
picker's refresh button). `POST3_FAKE_PROVIDERS=1` serves the fixture and never shells out;
`$POST3_HIGGSFIELD_BIN` overrides the binary (the test suites point it nowhere).

Post3's own ids stay first and keep their labels from what they resolve to: `nano_banana_2`
(the default still model) answers as job type `nano_banana_pro`, so it shows "Nano Banana Pro"
and replaces that row rather than appearing twice.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from ..store.atomic import atomic_write_bytes
from ..store.paths import store_root
from . import models as models_mod

BIN_ENV = "POST3_HIGGSFIELD_BIN"
LIST_FIXTURE = models_mod.FIXTURES_DIR.parent / "model_list.json"
PICKER_KINDS = ("image", "video")
# Post3's defaults per kind, first in the picker; `nano_banana_2` stays the still default.
DEFAULT_IDS = {"image": ["nano_banana_2", "seedream_v4_5"], "video": ["kling3_0"]}


def cache_path(project_root: str | Path) -> Path:
    return store_root(project_root) / "cache" / "higgsfield" / "model_list.json"


def _fetch() -> list[dict]:
    if models_mod.fake_mode():
        return json.loads(LIST_FIXTURE.read_text(encoding="utf-8"))
    binary = os.environ.get(BIN_ENV) or "higgsfield"
    proc = subprocess.run([binary, "model", "list", "--json"], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"higgsfield model list failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return json.loads(proc.stdout)


def _job_type(model_id: str) -> str:
    """What an id answers as (`observed.json`), e.g. `nano_banana_2` -> `nano_banana_pro`."""
    return models_mod._observed(model_id).get("job_type", model_id)


def picker_models(raw: list[dict]) -> list[dict]:
    """`[{id, label, kind}]`: Post3's defaults first, then every other image/video model,
    each kind sorted by label. Rows the defaults already stand for are dropped."""
    by_job = {r.get("job_type"): r for r in raw if r.get("type") in PICKER_KINDS and r.get("job_type")}
    out: list[dict] = []
    taken: set[str] = set()
    for kind in PICKER_KINDS:
        for model_id in DEFAULT_IDS[kind]:
            row = by_job.get(_job_type(model_id)) or by_job.get(model_id) or {}
            out.append({"id": model_id, "label": row.get("display_name") or model_id, "kind": kind})
            taken |= {model_id, _job_type(model_id)}
        rest = [r for r in by_job.values() if r["type"] == kind and r["job_type"] not in taken]
        out += [{"id": r["job_type"], "label": r.get("display_name") or r["job_type"], "kind": kind}
                for r in sorted(rest, key=lambda r: (str(r.get("display_name")).lower(), r["job_type"]))]
    return out


def list_models(project_root: Optional[str | Path] = None, *, refresh: bool = False) -> dict:
    """`{"models": [...], "fetched_at": <epoch>, "cached": bool}`. Reads the project's cache
    unless `refresh` (or there is none); a fetch is written back to the cache."""
    path = cache_path(project_root) if project_root is not None else None
    if path is not None and not refresh and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {"models": picker_models(data["raw"]), "fetched_at": data["fetched_at"], "cached": True}
        except (ValueError, KeyError):
            pass  # a damaged cache is fetched again
    raw = _fetch()
    fetched_at = time.time()
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, json.dumps({"raw": raw, "fetched_at": fetched_at}, indent=2).encode("utf-8"))
    return {"models": picker_models(raw), "fetched_at": fetched_at, "cached": False}


__all__ = ["DEFAULT_IDS", "LIST_FIXTURE", "cache_path", "list_models", "picker_models"]
