"""Model contracts + cost estimation over the Higgsfield CLI (T12 spec, shapes verified in T18).

`model_get` reads `higgsfield model get <id> --json`, cached on disk under a project's
`.post3/cache/higgsfield/models/`; `estimate_cost` reads `higgsfield generate cost <model>
... --json`. `POST3_FAKE_PROVIDERS=1` (set by every test, never by a real run) serves both
from the bundled fixtures instead and never shells out -- this module is the only place
recipe code touches the Higgsfield CLI's exact shape.

Real shapes (CLI 1.1.25, recorded 2026-10-13; fixtures/higgsfield/models/*.json are verbatim):
  - `model get <id> --json` -> `{"display_name", "job_type", "type": "image"|"video",
    "params": [{"name", "type", "default", "required", "enum"?}, ...], "rules": [{"cel",
    "message"}]}`. No pricing, no fps, no max duration. `job_type` may differ from the id
    asked for (`nano_banana_2` answers as `nano_banana_pro`). `_normalise` turns the list
    into `{"params": {name: {...}}}` so callers index by name.
  - `generate cost <id> ... --json` -> `{"credits": <number>}`; invalid values exit 4 with
    "Invalid values: aspect_ratio=4:5 (allowed: ...)".
Facts the contract does not carry (cost table, Kling's max 15 s, the 24 fps one real Kling
job came back at) live in `fixtures/higgsfield/observed.json`.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from ..graph.types import Cost
from ..store.paths import store_root

FAKE_PROVIDERS_ENV = "POST3_FAKE_PROVIDERS"
FIXTURES_DIR = Path(__file__).with_name("fixtures") / "higgsfield" / "models"
OBSERVED_FIXTURE = FIXTURES_DIR.parent / "observed.json"


class ModelNotFound(KeyError):
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        super().__init__(f"no Higgsfield model contract for {model_id!r}")


def fake_mode() -> bool:
    return os.environ.get(FAKE_PROVIDERS_ENV) == "1"


def _cache_path(project_root: str | Path, model_id: str) -> Path:
    return store_root(project_root) / "cache" / "higgsfield" / "models" / f"{model_id}.json"


def _observed(model_id: str) -> dict:
    """This model's entry in `observed.json` (recorded facts the contract lacks), or {}."""
    if not OBSERVED_FIXTURE.is_file():
        return {}
    entry = json.loads(OBSERVED_FIXTURE.read_text(encoding="utf-8")).get(model_id)
    return entry if isinstance(entry, dict) else {}


def _normalise(model_id: str, raw: dict) -> dict:
    """The real `model get` shape -> the dict callers use: `params` keyed by name, `id` the
    id that was asked for, `max_duration_seconds` from `observed.json` when recorded."""
    params = raw.get("params", {})
    if isinstance(params, list):
        params = {p["name"]: {k: v for k, v in p.items() if k != "name"} for p in params if "name" in p}
    info = {
        "id": model_id, "job_type": raw.get("job_type", model_id), "display_name": raw.get("display_name"),
        "type": raw.get("type"), "params": params, "rules": raw.get("rules", []),
    }
    max_duration = _observed(model_id).get("max_duration_seconds")
    if max_duration is not None:
        info["max_duration_seconds"] = max_duration
    info["pricing"] = _pricing_summary(model_id, params)
    return info


def _pricing_summary(model_id: str, params: dict) -> dict:
    """A price-label dict for the model picker from the recorded cost table: per call at
    the model's default tier, or per second at Post3's video default (mode pro, sound on)."""
    credits = _observed(model_id).get("credits", {})
    if "per_second" in credits:
        return {"credits_per_second": credits["per_second"]["pro"]["on"], "unit": "credits", "mode": "pro"}
    per_call = credits.get("per_call", {})
    tier = params.get("resolution", params.get("quality", {})).get("default")
    if tier in per_call:
        return {"credits_per_call": per_call[tier], "unit": "credits"}
    return {}


def model_get(model_id: str, project_root: Optional[str | Path] = None) -> dict:
    """The model's normalised param contract. Fixture in fake mode (never shells out); a
    disk-cached real CLI call otherwise (cached only when `project_root` is given)."""
    if fake_mode():
        fixture = FIXTURES_DIR / f"{model_id}.json"
        if not fixture.is_file():
            raise ModelNotFound(model_id)
        return _normalise(model_id, json.loads(fixture.read_text(encoding="utf-8")))

    if project_root is not None:
        cache = _cache_path(project_root, model_id)
        if cache.is_file():
            return _normalise(model_id, json.loads(cache.read_text(encoding="utf-8")))

    out = subprocess.run(
        ["higgsfield", "model", "get", model_id, "--json"],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    if project_root is not None:
        cache = _cache_path(project_root, model_id)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data), encoding="utf-8")
    return _normalise(model_id, data)


def _flag(cli_args: list[str], name: str) -> Optional[str]:
    for i, arg in enumerate(cli_args[:-1]):
        if arg == name:
            return cli_args[i + 1]
    return None


def _fake_credits(model_id: str, cli_args: list[str], units: float) -> float:
    """The recorded `generate cost` for these args (observed.json), defaults as the CLI's
    own (`model get` defaults: Kling mode std, sound on; still resolution 2k / quality basic)."""
    info = model_get(model_id)
    credits = _observed(model_id).get("credits", {})

    def arg(name: str) -> Optional[str]:
        given = _flag(cli_args, f"--{name}")
        return given if given is not None else info["params"].get(name, {}).get("default")

    if "per_second" in credits:
        by_sound = credits["per_second"][arg("mode") or "std"]
        return float(by_sound[arg("sound") or "on"]) * units
    per_call = credits.get("per_call", {})
    tier = arg("resolution") or arg("quality")
    return float(per_call.get(tier, max(per_call.values(), default=1.0)))


def estimate_cost(
    model_id: str, cli_args: list[str], *, units: float = 1.0, project_root: Optional[str | Path] = None,
) -> Optional[Cost]:
    """One call's estimated spend in credits. Fake mode: the recorded real cost table in
    `observed.json` (`units` = duration seconds for video). Real mode: `higgsfield generate
    cost <model> <cli_args> --json` -> `{"credits": N}`."""
    if fake_mode():
        return Cost(amount=_fake_credits(model_id, cli_args, units), unit="credits", provider="higgsfield")

    out = subprocess.run(
        ["higgsfield", "generate", "cost", model_id, *cli_args, "--json"],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    return Cost(amount=float(data["credits"]), unit="credits", provider="higgsfield")


def estimate_still(model_id: str, aspect: str, project_root: Optional[str | Path] = None) -> Optional[Cost]:
    """One still/end-frame call's estimate -- the same args the plan (`node_types`) and the
    worker (`workers/_spend.py`) both use, so the cost recorded is the cost that was shown."""
    return estimate_cost(model_id, ["--prompt", "t", "--aspect_ratio", aspect], project_root=project_root)


def estimate_video(
    model_id: str, duration: int, mode: str, project_root: Optional[str | Path] = None,
) -> Optional[Cost]:
    """One video call's estimate (`units` = duration seconds); see `estimate_still`."""
    return estimate_cost(
        model_id, ["--prompt", "t", "--duration", str(duration), "--mode", mode],
        units=float(duration), project_root=project_root,
    )


def offered_aspects(model_id: str) -> Optional[list[str]]:
    """T37/T18: the aspect ratios `model_id` accepts (the real `model get` aspect_ratio enum,
    recorded in `observed.json`), or `None` when nothing is known (callers then assume the
    cut's own aspect is offered). Read from the bundled file in both modes, so instantiating
    a beat never shells out."""
    offered = _observed(model_id).get("aspect_ratios")
    return [str(a) for a in offered] if isinstance(offered, list) and offered else None


def observed_fps(model_id: str) -> Optional[float]:
    """The fps a real job from this model came back at, if one was measured (Kling: 24).
    Not a contract: `model get` exposes no fps parameter."""
    fps = _observed(model_id).get("fps")
    return float(fps) if isinstance(fps, (int, float)) else None


def capabilities_for(info: dict, *, offers_end_frame: bool) -> list[str]:
    """T30d: plain-word capability chips for the in-node/inspector model picker, derived
    from the same model contract dict `model_get` already returns -- no new fixture shape,
    just reading fields that were already there (`params`) plus one new optional field
    (`max_duration_seconds`, only present on video models). `offers_end_frame` comes from
    the caller (`routes/enrich.py`'s own `MODEL_OPTIONS["endframe.generate"]` membership)
    since a model contract has no notion of which *node types* a project chose to offer it
    for."""
    params = info.get("params", {})
    caps = ["start frame"]
    if offers_end_frame:
        caps.append("end frame")
    if {"image_references", "input_images"} & set(params):
        caps.append("refs")
    max_duration = info.get("max_duration_seconds")
    if isinstance(max_duration, (int, float)):
        caps.append(f"max {int(max_duration)}s")
    return caps


__all__ = [
    "fake_mode", "model_get", "estimate_cost", "estimate_still", "estimate_video",
    "capabilities_for", "offered_aspects", "observed_fps", "ModelNotFound", "FAKE_PROVIDERS_ENV",
]
