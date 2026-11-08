"""T37: an export says its format -- `<cut>_<aspect>_vNNN.otio`, a timeline named the same with
the aspect and intended resolution in its `post3` metadata, and a README beside it saying the
A-roll is 16:9 and reframed in Resolve. Whether Resolve honours the metadata is H1's call."""
from __future__ import annotations

import json

import opentimelineio as otio
import pytest

from post_core import store
from post_core.export import export_cut, patch_export
from post_core.model import Rational


def _short(fixture, aspect: Rational, label: str):
    """A short derived from the 16:9 fixture cut (same passages/spans), stored as its own Cut."""
    short = fixture.cut.model_copy(update={
        "id": f"short-{label}", "aspect": aspect, "parent_cut_id": fixture.cut.id, "variant_label": "keith-short",
    })
    store.write(fixture.project_root, "cut", short, expected_rev=0)
    return short


@pytest.mark.parametrize("aspect,token,size", [
    (Rational(num=4, den=5), "4x5", (1080, 1350)),
    (Rational(num=9, den=16), "9x16", (1080, 1920)),
    (Rational(num=16, den=9), "16x9", (1920, 1080)),
])
def test_name_and_metadata_carry_the_cuts_format(export_project, aspect, token, size):
    short = _short(export_project, aspect, token)
    path = export_cut(export_project.project_root, short.id)
    assert path.name == f"keith-short_{token}_v001.otio"

    tl = otio.adapters.read_from_file(str(path))
    assert tl.name == f"keith-short_{token}_v001"
    meta = tl.metadata["post3"]
    assert meta["aspect"] == token.replace("x", ":")
    assert (meta["resolution"]["width"], meta["resolution"]["height"]) == size
    assert meta["a_roll_aspect"] == "16:9"
    assert meta["a_roll_reframed_in"] == (None if token == "16x9" else "resolve")

    manifest = json.loads(path.with_name(f"keith-short_{token}_v001.manifest.json").read_text())
    assert manifest["aspect"] == meta["aspect"]
    assert manifest["resolution"] == meta["resolution"]


def test_readme_says_the_a_roll_is_reframed_in_resolve(export_project):
    short = _short(export_project, Rational(num=4, den=5), "4x5")
    path = export_cut(export_project.project_root, short.id)
    readme = path.with_name("keith-short_4x5_v001.README.txt").read_text()
    assert "a 4:5 timeline at 1080x1350, 23.976 fps" in readme
    assert "The A-roll is 16:9 and is reframed in Resolve to 4:5" in readme


def test_readme_for_a_same_aspect_cut_says_no_reframe(export_project):
    path = export_cut(export_project.project_root, export_project.cut.id)
    readme = path.with_name(path.stem + ".README.txt").read_text()
    assert "the same as this timeline; no reframe needed" in readme


def test_versions_count_per_aspect_and_patch_finds_its_manifest(export_project):
    four = _short(export_project, Rational(num=4, den=5), "4x5")
    nine = _short(export_project, Rational(num=9, den=16), "9x16")
    root = export_project.project_root
    assert export_cut(root, four.id).name == "keith-short_4x5_v001.otio"
    assert export_cut(root, nine.id).name == "keith-short_9x16_v001.otio"
    assert export_cut(root, four.id).name == "keith-short_4x5_v002.otio"
    patched = patch_export(root, four.id, since_version=2)
    assert patched.name == "keith-short_4x5_v003.otio"
    tl = otio.adapters.read_from_file(str(patched))  # keep a reference: OTIO frees temporaries
    assert tl.metadata["post3"]["patch_since"] == 2
