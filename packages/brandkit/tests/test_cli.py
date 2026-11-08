import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "brandkit", *args],
        cwd=cwd or REPO_ROOT, capture_output=True, text=True,
    )


def test_status_command_on_the_demo_kit():
    proc = _run("status", "_demo")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["kit"] == "_demo"
    assert data["counts"]["pending"] >= 0
    assert "stills.style_block" in data["filled"]


def test_test_style_command_refuses_a_fresh_brand_system(tmp_path):
    # `init` copies the shipped _template design system into a throwaway client; its
    # imagery.md style block is still the template's placeholder, so no prompt is printed
    client = "zz_test_style_client"
    dest = REPO_ROOT / "kits" / client
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    try:
        proc = _run("init", client)
        assert proc.returncode == 0, proc.stderr
        # style_block is pending in a freshly-inited kit -> test-style must refuse
        proc = _run("test-style", client)
        assert proc.returncode == 1
        assert "pending" in proc.stderr and "stills.style_block" in proc.stderr
        assert proc.stdout == ""
    finally:
        import shutil
        if dest.exists():
            shutil.rmtree(dest)


def test_init_command_starts_a_brand_system_from_the_template(tmp_path, monkeypatch):
    # init writes under packages/brandkit/kits/<client>/ (KITS_ROOT is fixed relative to
    # the package), so use a throwaway client name and clean up afterwards.
    client = "zz_test_client"
    dest = REPO_ROOT / "kits" / client
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    try:
        proc = _run("init", client)
        assert proc.returncode == 0, proc.stderr
        assert (dest / "design-system" / "design-system.json").is_file()
        assert not (dest / "brand.yaml").exists()
        meta = json.loads((dest / "design-system" / "brand-kit.json").read_text())
        assert meta["identity"]["name"] == client.capitalize()
        assert "[Client]" not in (dest / "design-system" / "README.md").read_text()

        status = _run("status", client)
        assert status.returncode == 0, status.stderr
        report = json.loads(status.stdout)
        assert report["kit"] == client
        assert report["counts"]["guessed"] == 0
        assert "core.identity.name" in report["filled"]
        assert "stills.style_block" in {p["field"] for p in report["pending"]}
    finally:
        import shutil
        if dest.exists():
            shutil.rmtree(dest)
