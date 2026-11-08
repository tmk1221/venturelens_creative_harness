"""T39: projects in the media library (`<library>/<Company>/<Project>/`), against a temp
library -- never the real one. Layout creation, sources referenced read-only or copied with
`copy=True`, kit lookup order (company `brand/` first, then the repo kits), `Exports/` and
`AI Generations/`, the company listing and the rc file."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from post_core import brand, library
from post_core.export.otio_export import _exports_dir
from post_core.model.project import Project
from post_core.project_new import NewProjectError, new_project
from post_core.store import store as store_module

from .conftest import SHIPPED_DEMO, requires_ffmpeg


@pytest.fixture
def lib(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "Library"
    root.mkdir()
    monkeypatch.setenv(library.LIBRARY_ENV, str(root))
    return root


def _company_with_kit(lib: Path, company: str) -> Path:
    brand_dir = lib / company / "brand"
    shutil.copytree(SHIPPED_DEMO, brand_dir)
    return brand_dir


def test_library_root_env_then_rc_then_default(tmp_path, monkeypatch):
    monkeypatch.delenv(library.LIBRARY_ENV, raising=False)
    rc = tmp_path / "rc"
    monkeypatch.setenv(library.RC_ENV, str(rc))
    assert library.library_root() == library.DEFAULT_LIBRARY
    rc.write_text("# where media lives\nlibrary = /tmp/elsewhere  # the drive\n")
    assert library.library_root() == Path("/tmp/elsewhere")
    monkeypatch.setenv(library.LIBRARY_ENV, str(tmp_path / "env"))
    assert library.library_root() == tmp_path / "env"


@pytest.mark.parametrize("bad", ["", "  ", "a/b", "..", ".hidden"])
def test_names_must_be_one_folder_name(lib, bad):
    with pytest.raises(library.LibraryError):
        library.project_dir(bad, "P")
    with pytest.raises(library.LibraryError):
        library.project_dir("Co", bad)


@requires_ffmpeg
def test_new_library_project_makes_the_house_layout_and_references_the_source(lib, clip, kits):
    before = sorted(p.name for p in clip.parent.iterdir())
    out = new_project(None, "Ep 1", [clip], company="Acme Co")

    root = lib / "Acme Co" / "Ep 1"
    assert out["root"] == str(root.resolve()) and out["company"] == "Acme Co"
    for sub in library.HOUSE_FOLDERS:
        assert (root / sub).is_dir(), sub
    project, _ = store_module.read(root, "project")
    assert (project.name, project.company, project.brand_kit) == ("Ep 1", "Acme Co", "_demo")
    assert [s["path"] for s in out["sources"]] == [str(clip.resolve())]  # referenced, not copied
    assert list((root / library.SOURCE_FOLDER).iterdir()) == []
    assert sorted(p.name for p in clip.parent.iterdir()) == before  # nothing written by the footage
    assert [s["step"] for s in out["steps"]][:3] == ["check", "init", "layout"]
    assert _exports_dir(root) == (root / "Exports").resolve()

    again = new_project(None, "Ep 1", [clip], company="Acme Co")
    assert all(s["status"] == "skipped" for s in again["steps"][1:])


@requires_ffmpeg
def test_copy_puts_the_recording_in_video_source(lib, clip, kits):
    out = new_project(None, "Ep 2", [clip], company="Acme Co", copy=True)
    copied = lib / "Acme Co" / "Ep 2" / "Video" / "source" / clip.name
    assert copied.is_file() and clip.is_file()  # copied, never moved
    assert out["sources"][0]["path"] == str(copied.resolve())
    assert not list(copied.parent.glob(".*.part"))
    again = new_project(None, "Ep 2", [clip], company="Acme Co", copy=True)
    assert next(s for s in again["steps"] if s["step"] == "copy:0")["status"] == "skipped"


@requires_ffmpeg
def test_a_recording_already_in_video_source_is_used_in_place(lib, kits):
    from .conftest import make_recording
    clip = make_recording(lib / "Acme Co" / "Ep 3" / "Video" / "source" / "take.mp4")
    out = new_project(None, "Ep 3", [clip], company="Acme Co", copy=True)
    assert out["sources"][0]["path"] == str(clip.resolve())
    assert sorted(p.name for p in clip.parent.iterdir()) == ["take.mp4"]


@requires_ffmpeg
def test_a_project_inside_video_source_is_refused(lib, clip, kits):
    with pytest.raises(NewProjectError, match="inside the footage folder"):
        new_project(lib / "Acme Co" / "Ep" / "Video" / "source" / "oops", "oops", [clip])


@requires_ffmpeg
def test_company_kit_comes_first_and_is_the_default(lib, clip, kits):
    brand_dir = _company_with_kit(lib, "Acme Co")
    out = new_project(None, "Ep 4", [clip], company="Acme Co")
    root = Path(out["root"])
    assert out["brand_kit"] == "Acme Co"
    assert brand.available_kits(root) == ["Acme Co", "_demo", "show"]
    assert brand.load_project_kit(root).path == brand_dir
    # The repo kits are still there to choose, and the company kit can be chosen back.
    brand.set_project_kit(root, "_demo")
    assert brand.load_project_kit(root).path == kits / "_demo"
    brand.set_project_kit(root, "Acme Co")
    assert brand.kit_summary("Acme Co", root)["name"] == "Kestrel Demo Co."
    # A project outside the library never sees a company kit.
    assert "Acme Co" not in brand.available_kits()


def test_list_companies_and_publish_generated(lib, tmp_path):
    _company_with_kit(lib, "Acme Co")
    (lib / "Acme Co" / "Ep" / "Video").mkdir(parents=True)
    (lib / "Acme Co" / "notes").mkdir()
    (lib / "Resolve Project Library").mkdir()
    (lib / "Beta").mkdir()
    assert library.list_companies() == [
        {"name": "Acme Co", "has_brand": True, "projects": ["Ep"]},
        {"name": "Beta", "has_brand": False, "projects": []},
    ]

    root = lib / "Acme Co" / "Ep"
    store_module.init_project(root)
    store_module.write(root, "project", Project(name="Ep", root=str(root), company="Acme Co"), expected_rev=0)
    clip = tmp_path / "video.mp4"
    clip.write_bytes(b"fake")
    written = library.publish_generated(root, "video.generate", "b1-video", "abcdef1234", [clip])
    assert written == [str(root.resolve() / "AI Generations" / "b1-video_abcdef12_video.mp4")]
    assert Path(written[0]).read_bytes() == b"fake" and clip.is_file()
    assert library.publish_generated(root, "brief.write", "b1-brief", "abcdef1234", [clip]) == []
