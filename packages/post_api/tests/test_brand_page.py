"""T41: `GET /api/projects/{pid}/brand[/...]` -- the project's kit as a live style guide.
Against a temp `$POST3_KITS_DIR` copy of the demo kit (never the shipped or a library kit):
rendered in memory on first request, re-rendered when a kit file changes, confined to the
kit's `design-system/` folder, and never writing into the kit."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from post_core import brand

SHIPPED_DEMO = Path(brand.__file__).resolve().parents[2] / "brandkit" / "kits" / "_demo"


@pytest.fixture
def kit(tmp_path, monkeypatch) -> Path:
    kits = tmp_path / "kits"
    shutil.copytree(SHIPPED_DEMO, kits / "_demo")
    (kits / "secret").mkdir()
    (kits / "secret" / "key.txt").write_text("not for the browser", encoding="utf-8")
    monkeypatch.setenv(brand.KITS_DIR_ENV, str(kits))
    return kits / "_demo" / "design-system"


def _files(folder: Path) -> dict[str, int]:
    return {str(p.relative_to(folder)): p.stat().st_mtime_ns for p in folder.rglob("*") if p.is_file()}


def test_renders_the_kit_page_on_first_request_without_writing(client, project, kit):
    pid = project["id"]
    (kit / "assets" / "approved-look-4x5.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    before = _files(kit)

    info = client.get(f"/api/projects/{pid}/brand")
    assert info.status_code == 200, info.text
    body = info.json()
    assert body["kit_id"] == "_demo"
    assert body["page_url"] == f"/api/projects/{pid}/brand/index.html"
    assert body["approved_looks"] == ["approved-look-4x5.png"]

    page = client.get(body["page_url"])
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert page.headers["content-security-policy"] == "sandbox"
    html = page.text
    assert "Kestrel" in html and "At a glance" in html and "deep forest green" in html
    assert 'src="assets/approved-look-4x5.png"' in html
    assert "<svg" in html  # the logos, inline

    css = client.get(f"/api/projects/{pid}/brand/tokens.css")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    assert "--primary" in css.text

    look = client.get(f"/api/projects/{pid}/brand/assets/approved-look-4x5.png")
    assert look.status_code == 200 and look.content.startswith(b"\x89PNG")
    logo = client.get(f"/api/projects/{pid}/brand/assets/Logos/mark.svg")
    assert logo.status_code == 200 and b"<svg" in logo.content

    assert _files(kit) == before  # read-only: no index.html / tokens.css written into the kit
    assert not (kit / "index.html").exists() and not (kit / "tokens.css").exists()


def test_rerenders_when_a_kit_file_changes(client, project, kit):
    pid = project["id"]
    first = client.get(f"/api/projects/{pid}/brand").json()["signature"]
    assert "deep forest green" in client.get(f"/api/projects/{pid}/brand/index.html").text
    assert client.get(f"/api/projects/{pid}/brand").json()["signature"] == first  # stable when nothing changed

    meta = kit / "brand-kit.json"
    meta.write_text(meta.read_text(encoding="utf-8").replace("deep forest green", "racing green"), encoding="utf-8")
    st = meta.stat()
    os.utime(meta, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))

    second = client.get(f"/api/projects/{pid}/brand").json()["signature"]
    assert second != first
    html = client.get(f"/api/projects/{pid}/brand/index.html").text
    assert "racing green" in html and "deep forest green" not in html

    (kit / "assets" / "approved-look-16x9.png").write_bytes(b"\x89PNG\r\n\x1a\nnew")
    assert client.get(f"/api/projects/{pid}/brand").json()["approved_looks"] == ["approved-look-16x9.png"]


@pytest.mark.parametrize("rel", [
    "../../secret/key.txt",
    "..%2F..%2Fsecret%2Fkey.txt",
    "assets/../../../secret/key.txt",
    "%2Fetc%2Fpasswd",
    "assets/Logos/nope.svg",
    "assets",
])
def test_paths_are_confined_to_the_design_system_folder(client, project, kit, rel):
    r = client.get(f"/api/projects/{project['id']}/brand/{rel}")
    assert r.status_code == 404, (rel, r.status_code)
    assert b"not for the browser" not in r.content


def test_a_symlink_out_of_the_kit_is_refused(client, project, kit, tmp_path):
    (kit / "assets" / "escape.txt").symlink_to(tmp_path / "kits" / "secret" / "key.txt")
    r = client.get(f"/api/projects/{project['id']}/brand/assets/escape.txt")
    assert r.status_code == 404


def test_a_kit_without_a_design_system_is_a_clear_404(client, project, kit):
    shutil.rmtree(kit)
    (kit.parent / "brand.yaml").write_text("name: _demo\n", encoding="utf-8")
    r = client.get(f"/api/projects/{project['id']}/brand")
    assert r.status_code == 404


@pytest.mark.parametrize("rel", ["../../secret/key.txt", "assets/../../../secret/key.txt", "/etc/passwd", "..", "", ".hidden"])
def test_asset_path_refuses_anything_outside_the_folder(project, kit, rel):
    from post_core import brand_page

    with pytest.raises((brand_page.OutsideKit, FileNotFoundError)):
        brand_page.asset_path(project["root"], rel)
    assert brand_page.asset_path(project["root"], "assets/Logos/mark.svg") == (kit / "assets" / "Logos" / "mark.svg").resolve()
