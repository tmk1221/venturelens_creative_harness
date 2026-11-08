"""T33 acceptance: the brand kit is chosen per project (`post_core.brand`). A project made
before T33 loads the demo kit; `set_project_kit` refuses an unknown kit, changes the hash, and
marks branded nodes stale (old outputs kept, nothing re-run). Kits come from a temp
`$POST3_KITS_DIR` holding copies of the demo kit -- the shipped kits are never touched.
Plus the lead's T33 extra: a video beat whose kit leaves camera to the beat (the demo kit,
like Acme since 31f5cdd) still builds its motion prompt."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from post_core import brand
from post_core import store
from post_core.graph.hashing import compute_hashes
from post_core.graph.state import NodeState, compute_states
from post_core.model.project import Project
from post_core.recipes import cmd_for as cmd_for_mod
from post_core.recipes.instantiate import SpanSpec, instantiate
from post_core.recipes.rebrand import rebrand_workflow

from conftest import enqueue_ready, run_to_completion

SHIPPED_KITS = Path(brand.__file__).resolve().parents[2] / "brandkit" / "kits"
OTHER_STYLE = "Night street photography under sodium light, wet asphalt, long lens, heavy grain."


@pytest.fixture
def kits_dir(tmp_path, monkeypatch) -> Path:
    kits = tmp_path / "kits"
    shutil.copytree(SHIPPED_KITS / "_demo", kits / "_demo")
    shutil.copytree(SHIPPED_KITS / "_template", kits / "_template")
    other = kits / "other"
    shutil.copytree(SHIPPED_KITS / "_demo", other)
    meta_path = other / "design-system" / "brand-kit.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["identity"] = {**meta["identity"], "name": "Otherco", "what_they_do": "Bicycle repair"}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    imagery = other / "design-system" / "imagery.md"
    lines = imagery.read_text(encoding="utf-8").split("\n")
    first_quote = next(i for i, line in enumerate(lines) if line.startswith("> "))
    lines[first_quote] = f"> {OTHER_STYLE}"
    imagery.write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.setenv(brand.KITS_DIR_ENV, str(kits))
    return kits


@pytest.fixture
def project(project_root) -> Path:
    store.write(project_root, "project", Project(name="p", root=str(project_root)), expected_rev=0)
    return project_root


def test_available_kits_skip_the_template(kits_dir):
    assert brand.available_kits() == ["_demo", "other"]


def test_project_without_brand_kit_loads_the_demo_kit(kits_dir, project):
    path = project / ".post3" / "project.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["data"].pop("brand_kit", None)  # a project.json written before T33
    path.write_text(json.dumps(envelope), encoding="utf-8")
    assert brand.project_kit_id(project) == "_demo"
    assert brand.load_project_kit(project).path == kits_dir / "_demo"


@pytest.mark.parametrize("bad", ["nope", "../kits/_demo", "_template", ""])
def test_unknown_kit_refused_listing_available(kits_dir, project, bad):
    with pytest.raises(brand.UnknownKit, match="available: _demo, other"):
        brand.set_project_kit(project, bad)
    assert brand.project_kit_id(project) == "_demo"


def test_set_kit_changes_the_hash_and_marks_branded_nodes_stale(kits_dir, project, registry):
    workflow = instantiate("live_action", SpanSpec(id="beat1", variants=1), brand.load_project_kit(project), None, project)
    store.write(project, "workflow", workflow, expected_rev=0)
    run_to_completion(project, workflow, registry)
    before = compute_hashes(workflow, registry)
    assert compute_states(workflow, registry, project, hashes=before)["beat1-still0"] == NodeState.DONE

    result = brand.set_project_kit(project, "other")

    assert result["workflows_updated"] == [workflow.id] and result["unbranded"] == {}
    assert brand.project_kit_id(project) == "other"
    rebranded, _rev = store.read(project, "workflow", workflow.id)
    assert rebranded.brand_kit_hash == brand.load_kit("other").kit_hash() != workflow.brand_kit_hash
    assert rebranded.node("beat1-motion").params["kit_dir"] == str(kits_dir / "other")
    assert f"Style: {OTHER_STYLE}" in rebranded.node("beat1-still0").params["prompt_text"]
    after = compute_hashes(rebranded, registry)
    assert after["beat1-still0"] != before["beat1-still0"]
    assert compute_states(rebranded, registry, project, hashes=after)["beat1-still0"] == NodeState.STALE

    # Setting it again changes nothing: the same kit hashes the same.
    assert brand.set_project_kit(project, "other")["workflows_updated"] == []


def test_rebrand_reports_prompts_a_pending_style_block_cannot_brand(kits_dir, project, kit):
    workflow = instantiate("live_action", SpanSpec(id="b", variants=2), kit, None, project)
    template = brand.load_kit("_demo")
    template.stills_style_block.status = "pending"
    _new, unbranded = rebrand_workflow(workflow, template)
    assert unbranded == ["b-still0", "b-still1"]


def test_video_beat_builds_its_motion_prompt_with_no_camera_anywhere(kits_dir, project, registry):
    """The demo kit leaves camera/pacing to the beat; a beat that sets neither still gets a
    motion prompt (house neutral camera) instead of `motion.from_frame` exiting 1."""
    kit = brand.load_project_kit(project)
    assert kit.video_camera_personality.status == "pending"
    workflow = instantiate("live_action", SpanSpec(id="beat1", variants=1), kit, None, project)
    assert workflow.node("beat1-motion").params["camera"] is None
    executor = run_to_completion(project, workflow, registry)
    pick = workflow.node("beat1-pick")
    pick.selected = workflow.edges_into("beat1-pick", "options")[0].id
    cmd_for = cmd_for_mod.make_cmd_for(workflow, registry, project)
    enqueue_ready(project, workflow, registry, cmd_for, executor.authorization)
    for _ in range(25):
        if not executor.run_once():
            break
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, project, hashes=hashes)
    assert states["beat1-motion"] == NodeState.DONE
    assert states["beat1-video"] == NodeState.DONE
    from post_core.graph.state import artifact_dir

    prompt = (artifact_dir(project, "motion.from_frame", hashes["beat1-motion"]) / "motion_prompt.txt").read_text()
    assert "Camera: locked-off, steady frame." in prompt
