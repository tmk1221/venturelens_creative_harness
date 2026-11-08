"""T33: `post project set-kit <kit_id>` over a temp `$POST3_KITS_DIR` (copies of the demo kit)."""
from __future__ import annotations

import shutil
from pathlib import Path

SHIPPED_DEMO = Path(__file__).resolve().parents[3] / "brandkit" / "kits" / "_demo"


def test_set_kit_refuses_unknown_and_records_known(run_cli, tmp_path):
    kits = tmp_path / "kits"
    for kit_id in ("_demo", "twin"):
        shutil.copytree(SHIPPED_DEMO, kits / kit_id)
    env = {"POST3_KITS_DIR": str(kits)}
    root = tmp_path / "proj"
    assert run_cli("init", str(root), extra_env=env)["exit_code"] == 0
    assert run_cli("project", "show", "--root", str(root), extra_env=env)["project"]["brand_kit"] == "_demo"

    refused = run_cli("project", "set-kit", "nope", "--root", str(root), extra_env=env)
    assert refused["exit_code"] == 1
    assert "available: _demo, twin" in refused["error"]

    done = run_cli("project", "set-kit", "twin", "--root", str(root), extra_env=env)
    assert done["exit_code"] == 0, done
    assert done["brand_kit"] == "twin" and done["previous"] == "_demo"
    assert run_cli("project", "show", "--root", str(root), extra_env=env)["project"]["brand_kit"] == "twin"
