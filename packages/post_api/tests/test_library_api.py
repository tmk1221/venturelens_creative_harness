"""T39: the media library over HTTP, against a temp library (`$POST3_LIBRARY`): the company
picker's `GET /api/library`, a new project by company + project name, the company kit first
in `GET /api/brand-kits?project=`, and the model picker's refresh."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from post_core import brand

from .test_project_new_api import _recording, _wait

SHIPPED_DEMO = Path(brand.__file__).resolve().parents[2] / "brandkit" / "kits" / "_demo"
HOUSE = ["AI Generations", "Animations", "Audio", "BRolls", "Exports", "Renders", "Transcript", "Video"]


@pytest.fixture
def lib(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "Library"
    shutil.copytree(SHIPPED_DEMO, root / "Acme Co" / "brand")
    (root / "Acme Co" / "Old show" / "Video").mkdir(parents=True)
    (root / "CacheClip").mkdir()
    monkeypatch.setenv("POST3_LIBRARY", str(root))
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")
    return root


def test_library_lists_companies_and_their_projects(client, lib):
    body = client.get("/api/library").json()
    assert body == {"root": str(lib), "exists": True,
                    "companies": [{"name": "Acme Co", "has_brand": True, "projects": ["Old show"]}]}


def test_new_project_by_company_uses_the_library_layout_and_company_kit(client, lib, tmp_path):
    clip = _recording(tmp_path / "footage" / "ep.mp4")
    resp = client.post("/api/projects/new", json={"name": "Ep 9", "company": "Acme Co", "sources": [str(clip)]})
    assert resp.status_code == 202, resp.text
    pid = resp.json()["project"]["id"]
    root = lib / "Acme Co" / "Ep 9"
    assert resp.json()["project"]["root"] == str(root.resolve())
    status = _wait(client, pid)
    assert status["job"]["state"] == "ok", status
    assert status["brand_kit"] == "Acme Co"
    assert sorted(p.name for p in root.iterdir() if not p.name.startswith(".")) == HOUSE
    assert client.get(f"/api/projects/{pid}").json()["company"] == "Acme Co"
    assert sorted(p.name for p in clip.parent.iterdir()) == ["ep.mp4"]

    kits = [k["id"] for k in client.get(f"/api/brand-kits?project={pid}").json()["kits"]]
    assert kits[0] == "Acme Co" and "_demo" in kits
    assert "Acme Co" not in [k["id"] for k in client.get("/api/brand-kits").json()["kits"]]

    bad = client.post("/api/projects/new", json={"name": "a/b", "company": "Acme Co", "sources": [str(clip)]})
    assert bad.status_code == 400 and "folder name" in bad.json()["detail"]


def test_model_refresh_rewrites_the_cache(client, project, monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")
    pid, root = project["id"], Path(project["root"])
    client.get(f"/api/projects/{pid}/node-registry")
    cache = root / ".post3" / "cache" / "higgsfield" / "model_list.json"
    assert cache.is_file()
    cache.write_text('{"raw": [], "fetched_at": 1}')
    assert client.get(f"/api/projects/{pid}/node-registry").json()["models"][0]["label"] == "nano_banana_2"
    r = client.post(f"/api/projects/{pid}/models/refresh")
    assert r.status_code == 200, r.text
    assert r.json()["fetched_at"] > 1 and r.json()["models"][0]["label"] == "Nano Banana Pro"
