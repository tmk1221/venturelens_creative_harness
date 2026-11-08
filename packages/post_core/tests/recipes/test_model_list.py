"""T39: the model picker's list -- every image/video model from `higgsfield model list`
(the recorded fixture; fake mode never shells out), labelled with Higgsfield's display name,
Post3's defaults first, cached in `.post3/` and refreshed on request."""
from __future__ import annotations

import json

import pytest

from post_core.recipes import model_list


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")


def test_picker_lists_every_image_and_video_model_with_display_names():
    raw = json.loads(model_list.LIST_FIXTURE.read_text(encoding="utf-8"))
    models = model_list.picker_models(raw)
    ids = [m["id"] for m in models]
    by_id = {m["id"]: m for m in models}

    assert ids[0] == "nano_banana_2" and by_id["nano_banana_2"]["label"] == "Nano Banana Pro"
    assert "nano_banana_pro" not in ids  # nano_banana_2 stands for it
    assert by_id["seedream_v4_5"]["label"] == "Seedream 4.5"
    assert by_id["kling3_0"] == {"id": "kling3_0", "label": "Kling v3.0", "kind": "video"}
    assert {m["kind"] for m in models} == {"image", "video"}
    wanted = {r["job_type"] for r in raw if r["type"] in ("image", "video")} - {"nano_banana_pro"}
    assert set(ids) == wanted | {"nano_banana_2"}
    assert len(ids) == len(set(ids))
    assert not any(r["type"] == "3d" and r["job_type"] in ids for r in raw)
    first_video = next(i for i, m in enumerate(models) if m["kind"] == "video")
    assert models[first_video]["id"] == "kling3_0"


def test_list_is_cached_in_the_project_and_refreshes(tmp_path):
    root = tmp_path / "proj"
    first = model_list.list_models(root)
    assert first["cached"] is False and model_list.cache_path(root).is_file()
    assert model_list.cache_path(root).is_relative_to(root / ".post3")

    second = model_list.list_models(root)
    assert second["cached"] is True and second["models"] == first["models"]

    data = json.loads(model_list.cache_path(root).read_text())
    data["raw"] = [{"display_name": "Only One", "job_type": "only_one", "type": "image"}]
    model_list.cache_path(root).write_text(json.dumps(data))
    assert "only_one" in [m["id"] for m in model_list.list_models(root)["models"]]
    refreshed = model_list.list_models(root, refresh=True)
    assert refreshed["cached"] is False and "only_one" not in [m["id"] for m in refreshed["models"]]
