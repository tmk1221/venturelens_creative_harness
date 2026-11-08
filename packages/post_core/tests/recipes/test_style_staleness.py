"""Acceptance: bumping the kit's style block marks a still `stale`, not `blocked`/`ready`
from scratch -- and the old output stays on disk and stays valid at its own (old) hash."""
from __future__ import annotations

import yaml
from brandkit.schema import BrandKit

from post_core.graph.hashing import compute_hashes
from post_core.graph.state import NodeState, compute_states
from post_core.recipes.instantiate import SpanSpec, instantiate

from conftest import run_to_completion


def test_style_block_change_marks_stills_stale(project_root, registry, kit, tmp_path):
    span = SpanSpec(id="beat1", variants=1)
    workflow = instantiate("live_action", span, kit, None, project_root)
    run_to_completion(project_root, workflow, registry)

    old_hashes = compute_hashes(workflow, registry)
    old_states = compute_states(workflow, registry, project_root, hashes=old_hashes)
    assert old_states["beat1-still0"] == NodeState.DONE
    old_hash = old_hashes["beat1-still0"]

    # Bump the style block's text/version on a copy of the kit dir.
    data = yaml.safe_load((kit.path / "brand.yaml").read_text())
    data["stills"]["style_block"]["text"] += ", now with a second light source"
    data["stills"]["style_block"]["version"] = "2"
    (kit.path / "brand.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    new_kit = BrandKit.load(kit.path)

    new_workflow = instantiate("live_action", span, new_kit, None, project_root)
    new_hashes = compute_hashes(new_workflow, registry)
    new_states = compute_states(new_workflow, registry, project_root, hashes=new_hashes)

    assert new_hashes["beat1-still0"] != old_hash
    assert new_states["beat1-still0"] == NodeState.STALE

    from post_core.graph.state import artifact_dir

    old_dir = artifact_dir(project_root, "still.generate", old_hash)
    assert (old_dir / "manifest.json").is_file()
    assert (old_dir / "image.png").is_file()
