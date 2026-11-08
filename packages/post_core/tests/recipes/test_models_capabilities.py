"""T30d: `capabilities_for` -- plain-word chips the in-node/inspector model picker shows,
derived straight from the fixture contract `model_get` already returns (fake-provider mode
only, per module docstring)."""
from __future__ import annotations

from post_core.recipes import models as models_mod


def test_image_model_with_refs_and_end_frame():
    info = models_mod.model_get("nano_banana_2")
    caps = models_mod.capabilities_for(info, offers_end_frame=True)
    assert caps == ["start frame", "end frame", "refs"]


def test_image_model_without_end_frame():
    info = models_mod.model_get("seedream_v4_5")
    caps = models_mod.capabilities_for(info, offers_end_frame=False)
    assert caps == ["start frame", "refs"]


def test_video_model_with_max_duration():
    info = models_mod.model_get("kling3_0")
    caps = models_mod.capabilities_for(info, offers_end_frame=False)
    # Kling's start/end images are frames, not references; 15 s is the CLI's own limit.
    assert caps == ["start frame", "max 15s"]


def test_real_contract_shape_is_normalised():
    """T18: fixtures are verbatim `model get --json`; params arrive as a list and the
    job_type can differ from the id asked for."""
    info = models_mod.model_get("nano_banana_2")
    assert info["id"] == "nano_banana_2" and info["job_type"] == "nano_banana_pro"
    assert info["params"]["prompt"]["required"] is True
    assert "4:5" in info["params"]["aspect_ratio"]["enum"]
    kling = models_mod.model_get("kling3_0")
    assert kling["params"]["sound"]["enum"] == ["on", "off"]
    assert {"start_image", "end_image"} <= set(kling["params"]) and "medias" not in kling["params"]


def test_fake_costs_match_recorded_real_costs():
    """`generate cost ... --json` -> {"credits": N}, values recorded 2026-10-13."""
    assert models_mod.estimate_still("nano_banana_2", "4:5").amount == 2.0
    assert models_mod.estimate_cost("nano_banana_2", ["--resolution", "4k"]).amount == 4.0
    assert models_mod.estimate_still("seedream_v4_5", "9:16").amount == 1.0
    assert models_mod.estimate_video("kling3_0", 5, "pro").amount == 10.0
    assert models_mod.estimate_cost("kling3_0", ["--mode", "pro", "--sound", "off"], units=5).amount == 7.5
    assert models_mod.estimate_cost("kling3_0", ["--duration", "5"], units=5).amount == 8.75  # CLI default std


def test_observed_aspects_agree_with_contract_enums():
    for model_id in ("nano_banana_2", "seedream_v4_5", "kling3_0"):
        enum = models_mod.model_get(model_id)["params"]["aspect_ratio"]["enum"]
        assert models_mod.offered_aspects(model_id) == enum
    assert models_mod.observed_fps("kling3_0") == 24.0
    assert models_mod.observed_fps("nano_banana_2") is None
