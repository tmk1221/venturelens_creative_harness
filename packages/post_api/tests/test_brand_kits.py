"""T33: the brand kit is chosen per project. `GET /api/brand-kits`, `PATCH /api/projects/{pid}`
with `brand_kit`, and enrich/suggest building from the project's kit -- all against a temp
`$POST3_KITS_DIR` (two copies of the demo kit, one renamed), never the shipped kits."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from post_core import brand
from post_core.store import store as store_module

from .test_enrich import _cut_with_beat_span
from .test_suggest import _build_project

SHIPPED_DEMO = Path(brand.__file__).resolve().parents[2] / "brandkit" / "kits" / "_demo"


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")


@pytest.fixture
def kits_dir(tmp_path, monkeypatch) -> Path:
    kits = tmp_path / "kits"
    shutil.copytree(SHIPPED_DEMO, kits / "_demo")
    shutil.copytree(SHIPPED_DEMO, kits / "other")
    meta_path = kits / "other" / "design-system" / "brand-kit.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["identity"] = {**meta["identity"], "name": "Otherco", "what_they_do": "Bicycle repair"}
    meta["guessed"] = True
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    monkeypatch.setenv(brand.KITS_DIR_ENV, str(kits))
    return kits


def test_brand_kits_lists_each_kit_with_its_status(client, kits_dir):
    r = client.get("/api/brand-kits")
    assert r.status_code == 200, r.text
    kits = {k["id"]: k for k in r.json()["kits"]}
    assert set(kits) == {"_demo", "other"}
    assert kits["_demo"]["name"] == "Kestrel Demo Co." and kits["_demo"]["status"] == "filled"
    assert kits["other"]["name"] == "Otherco" and kits["other"]["status"] == "guessed"
    assert kits["other"]["counts"]["guessed"] > 0 and kits["other"]["counts"]["filled"] == 0


def test_patch_project_brand_kit(client, project, kits_dir):
    pid = project["id"]
    assert client.get(f"/api/projects/{pid}").json()["brand_kit"] == "_demo"

    r = client.patch(f"/api/projects/{pid}", json={"brand_kit": "nope"})
    assert r.status_code == 400
    assert "available: _demo, other" in r.json()["error"]

    r = client.patch(f"/api/projects/{pid}", json={"brand_kit": "other"})
    assert r.status_code == 200, r.text
    assert r.json()["brand_kit"] == "other"
    assert client.get(f"/api/projects/{pid}").json()["brand_kit"] == "other"


@pytest.mark.parametrize("picture_kind", ["live_action", "motion_graphic"])
def test_enrich_builds_from_the_projects_kit(client, project, kits_dir, lavfi_clip, tmp_path, picture_kind):
    pid, root = project["id"], Path(project["root"])
    assert client.patch(f"/api/projects/{pid}", json={"brand_kit": "other"}).status_code == 200
    cut_id, span_id = _cut_with_beat_span(client, pid, lavfi_clip, tmp_path, picture_kind)

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow")
    assert r.status_code == 200, r.text
    workflow, _rev = store_module.read(root, "workflow", r.json()["workflow_id"])
    assert workflow.brand_kit_hash == brand.load_kit("other").kit_hash()
    assert workflow.brand_kit_hash != brand.load_kit("_demo").kit_hash()
    if picture_kind == "live_action":
        assert workflow.node(f"{span_id}-motion").params["kit_dir"] == str(kits_dir / "other")
    else:
        assert "Bicycle repair" in workflow.node(f"{span_id}-brief").params["writer_context"]["identity"]


def test_suggest_reads_the_projects_kit(client, project, kits_dir, monkeypatch):
    from post_api.routes import suggest as suggest_route

    pid, root = project["id"], Path(project["root"])
    ids = _build_project(root)
    assert client.patch(f"/api/projects/{pid}", json={"brand_kit": "other"}).status_code == 200
    seen: dict = {}

    def capture(*_args, writer_context=None, **_kwargs):
        seen["writer_context"] = writer_context
        return []

    monkeypatch.setattr(suggest_route.suggest_mod, "suggest_visuals", capture)
    r = client.post(f"/api/projects/{pid}/cuts/{ids['cut_id']}/suggested-visuals", json={"scope": "cut"})
    assert r.status_code == 200, r.text
    assert "Bicycle repair" in seen["writer_context"]["identity"]
