import json

import pytest
import yaml

from brandkit.derive import (
    DeriveError, accept_style, derive_style, draft_path, find_images,
    lint_style_block_purity, parse_vision_response,
)
from brandkit.vision import FakeVisionProvider
from .conftest import write_minimal_kit

CLEAN_STYLE = ("clean digital capture, soft even daylight, normal focal length with "
               "moderate depth of field, minimal uncluttered interiors, relaxed unposed energy")
DIRTY_STYLE = "a person in an office wearing #FF6600 with the sign reading 'Kestrel'"


def _images_folder(tmp_path):
    folder = tmp_path / "refs"
    folder.mkdir()
    for i in range(3):
        (folder / f"hero-{i}.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
    return folder


def _response(style_block: str) -> str:
    return json.dumps({"axes": {"colour": "warm neutral hues"}, "style_block": style_block})


def test_find_images_requires_at_least_one(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    with pytest.raises(DeriveError, match="no images"):
        find_images(folder)


def test_parse_vision_response_extracts_json_even_with_prose_around_it():
    raw = "Sure, here you go:\n" + _response(CLEAN_STYLE) + "\nHope that helps!"
    data = parse_vision_response(raw)
    assert data["style_block"] == CLEAN_STYLE


def test_parse_vision_response_rejects_missing_keys():
    with pytest.raises(DeriveError, match="missing"):
        parse_vision_response(json.dumps({"axes": {}}))


def test_purity_lint_clean_text_passes():
    assert lint_style_block_purity(CLEAN_STYLE) == []


def test_purity_lint_flags_hex_quotes_and_subjects():
    violations = lint_style_block_purity(DIRTY_STYLE)
    assert any("hex" in v for v in violations)
    assert any("quoted" in v for v in violations)
    assert any("subject" in v for v in violations)


def test_purity_lint_flags_over_word_cap():
    long_text = " ".join(["word"] * 91)
    violations = lint_style_block_purity(long_text)
    assert any("word" in v for v in violations)


# ---- derive_style: draft written, purity enforced, subjects stripped ------------------

def test_derive_style_writes_draft_with_clean_response(tmp_path):
    kit_dir = write_minimal_kit(tmp_path)
    images = _images_folder(tmp_path)
    provider = FakeVisionProvider(_response(CLEAN_STYLE))
    draft = derive_style(images, kit_dir, provider)
    assert draft["text"] == CLEAN_STYLE
    assert draft["status"] == "draft"
    assert len(draft["derived_from"]) == 3
    dpath = draft_path(kit_dir)
    assert dpath.is_file()
    on_disk = yaml.safe_load(dpath.read_text())
    assert on_disk["text"] == CLEAN_STYLE
    # the provider was actually given the image paths and a prompt
    assert len(provider.calls) == 1
    called_paths, called_prompt = provider.calls[0]
    assert len(called_paths) == 3
    assert "ignore" in called_prompt.lower()


def test_derive_style_raises_and_still_writes_draft_when_dirty(tmp_path):
    kit_dir = write_minimal_kit(tmp_path)
    images = _images_folder(tmp_path)
    provider = FakeVisionProvider(_response(DIRTY_STYLE))
    with pytest.raises(DeriveError, match="purity lint"):
        derive_style(images, kit_dir, provider)
    dpath = draft_path(kit_dir)
    assert dpath.is_file()
    on_disk = yaml.safe_load(dpath.read_text())
    assert on_disk["purity_violations"]


def test_derive_style_for_a_look_writes_a_suffixed_draft(tmp_path):
    kit_dir = write_minimal_kit(tmp_path)
    (kit_dir / "looks").mkdir()
    look_path = kit_dir / "looks" / "episode-1.yaml"
    look_path.write_text(yaml.safe_dump({"name": "episode-1"}), encoding="utf-8")
    images = _images_folder(tmp_path)
    provider = FakeVisionProvider(_response(CLEAN_STYLE))
    derive_style(images, kit_dir, provider, look_path)
    dpath = draft_path(kit_dir, look_path)
    assert dpath.name == "episode-1.style_block.draft.yaml"
    assert dpath.parent == look_path.parent


# ---- accept_style: versioning ----------------------------------------------------------

def test_accept_style_bumps_version_and_records_hashes(tmp_path):
    kit_dir = write_minimal_kit(tmp_path)
    images = _images_folder(tmp_path)
    provider = FakeVisionProvider(_response(CLEAN_STYLE))
    derive_style(images, kit_dir, provider)

    before = yaml.safe_load((kit_dir / "brand.yaml").read_text())
    assert before["stills"]["style_block"]["version"] == "1"  # from the fixture

    accept_style(kit_dir)

    after = yaml.safe_load((kit_dir / "brand.yaml").read_text())
    sb = after["stills"]["style_block"]
    assert sb["text"] == CLEAN_STYLE
    assert sb["version"] == "2"
    assert sb["status"] == "filled"
    assert len(sb["derived_from"]) == 3
    assert not draft_path(kit_dir).exists()


def test_accept_style_without_draft_raises(tmp_path):
    kit_dir = write_minimal_kit(tmp_path)
    with pytest.raises(DeriveError, match="no draft"):
        accept_style(kit_dir)


def test_accept_style_for_a_look_writes_flat_style_block_key(tmp_path):
    kit_dir = write_minimal_kit(tmp_path)
    (kit_dir / "looks").mkdir()
    look_path = kit_dir / "looks" / "episode-1.yaml"
    look_path.write_text(yaml.safe_dump({"name": "episode-1"}), encoding="utf-8")
    images = _images_folder(tmp_path)
    provider = FakeVisionProvider(_response(CLEAN_STYLE))
    derive_style(images, kit_dir, provider, look_path)

    accept_style(kit_dir, look_path)

    after = yaml.safe_load(look_path.read_text())
    assert after["style_block"] == CLEAN_STYLE
