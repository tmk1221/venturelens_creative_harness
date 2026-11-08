"""Shared fixtures for T12 recipe tests: a minimal brand kit on disk, an initialised post3
project, the full (builtins + recipe) node registry, and a helper that runs an Executor to
completion. Every test here sets `POST3_FAKE_PROVIDERS=1` (autouse) -- no test in this repo
may shell out to Higgsfield or HyperFrames for real.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from brandkit.schema import BrandKit

from post_core import store
from post_core.graph.hashing import compute_hashes
from post_core.graph.plan import plan as plan_fn
from post_core.graph.state import compute_states
from post_core.queue.budget import set_budget
from post_core.queue.enqueue import Authorization
from post_core.queue.enqueue import enqueue as enqueue_fn
from post_core.queue.executor import Executor
from post_core.recipes import cmd_for as cmd_for_mod
from post_core.recipes import full_registry

MARK_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'


def _minimal_kit_dict() -> dict:
    return {
        "name": "acme", "version": "1",
        "core": {
            "identity": {
                "name": {"text": "Acme", "status": "filled", "guessed": False},
                "what_they_do": {"text": "widgets", "status": "filled", "guessed": False},
                "who_they_serve": {"text": "everyone", "status": "filled", "guessed": False},
            },
            "colours": {
                "items": {
                    "light_neutral": {"name_plain": "plain white", "hex": "#F0F0F0", "status": "filled", "guessed": False},
                    "dark_neutral": {"name_plain": "near black", "hex": "#111111", "status": "filled", "guessed": False},
                    "accent": {"name_plain": "acme orange", "hex": "#FF6600", "status": "filled", "guessed": False},
                },
                "world_tone": "light",
                "dominant": "light_neutral",
            },
            "typography": {
                "heading": {"family": "Acme Sans", "source": "google", "file": None, "status": "filled", "guessed": False},
                "body": {"family": "Acme Sans", "source": "google", "file": None, "status": "filled", "guessed": False},
                "mono": {"family": "Acme Mono", "source": "google", "file": None, "status": "filled", "guessed": False},
            },
            "logos": {
                "mark": {
                    "file": "assets/mark.svg", "clear_space": 0.2, "min_size_px": 24,
                    "placements": {
                        "16:9": {"position": "top-left", "inset_px": 32, "height_px": 48},
                        "9:16": {"position": "top-center", "inset_px": 24, "height_px": 40},
                    },
                    "status": "filled", "guessed": False,
                }
            },
            "personality": {
                "is": {"items": ["bright", "friendly"], "status": "filled"},
                "voice": {"text": "Bright and friendly.", "status": "filled", "guessed": False},
            },
            "world": {
                "places": {"items": [], "status": "pending"},
                "people": {"items": [], "status": "pending"},
                "objects": {"items": [], "status": "pending"},
                "textures": {"items": [], "status": "pending"},
            },
            "names": {
                "official": {"items": ["Acme"], "status": "filled"},
                "products": {"items": [], "status": "pending"},
                "pronunciation": [],
            },
            "sources": [],
        },
        "stills": {
            "style_block": {"text": "clean digital capture, soft even light, normal lens",
                             "version": "1", "derived_from": ["deadbeef"], "status": "filled"},
            "accents": {"text": "orange may appear as a small accent.", "status": "filled", "guessed": False},
        },
        "video": {
            "camera_personality": {"text": "slow, deliberate moves", "status": "filled", "guessed": False},
            "pacing_default": {"text": "subtle", "status": "filled", "guessed": False},
        },
        "animation": {
            "grid_safe_areas": {"text": None, "status": "pending", "guessed": False},
            "easing": {"text": "matches house default", "status": "filled", "guessed": False},
            "durations": {"text": "matches house default", "status": "filled", "guessed": False},
            "colour_ratio": {"text": "60/30/10", "status": "filled", "guessed": False},
            "caption_style": {
                "font_role": "heading", "palette": {"dark": {"brand": "#FF6600"}, "light": {"brand": "#FF6600"}},
                "band": 0.9, "max_words": 6, "font_scale": 1.0, "status": "filled", "guessed": False,
            },
            "sfx_palette": {"items": [], "status": "pending"},
            "css_vars": {},
        },
        "qa_checklist_extra": [],
    }


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")


@pytest.fixture
def kit(tmp_path: Path) -> BrandKit:
    kit_dir = tmp_path / "acme_kit"
    (kit_dir / "assets").mkdir(parents=True)
    (kit_dir / "assets" / "mark.svg").write_bytes(MARK_SVG)
    (kit_dir / "brand.yaml").write_text(yaml.safe_dump(_minimal_kit_dict(), sort_keys=False), encoding="utf-8")
    return BrandKit.load(kit_dir)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    store.init_project(root)
    return root


@pytest.fixture
def registry():
    return full_registry()


def run_to_completion(project_root, workflow, registry, budget="test-budget", cap=1000.0, max_cycles=25):
    """Authorise a generous budget, enqueue whatever's runnable right now, then `run_once()`
    the executor until nothing more runs. Auto-continuation (`Executor._enqueue_ready`)
    picks up newly-ready nodes after each success, so repeated `run_once()` calls drain the
    whole graph (stopping short of anything still `needs_pick`/`needs_approval`)."""
    set_budget(project_root, budget, cap, unit="credits")
    authorization = Authorization(budget_id=budget, by="test", covers_downstream=True)
    cmd_for = cmd_for_mod.make_cmd_for(workflow, registry, project_root)
    executor = Executor(
        project_root=project_root, workflow=workflow, registry=registry,
        cmd_for=cmd_for, authorization=authorization,
    )
    enqueue_ready(project_root, workflow, registry, cmd_for, authorization)
    for _ in range(max_cycles):
        ran = executor.run_once()
        if not ran:
            break
    return executor


def enqueue_ready(project_root, workflow, registry, cmd_for, authorization):
    """Plan + enqueue everything currently `READY` (T05: the executor only auto-continues
    from a job it just ran; this is the initial kick, and also how a test re-kicks the
    queue after making a pick/approval)."""
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, project_root, hashes=hashes)
    plan = plan_fn(workflow, registry, states)
    return enqueue_fn(project_root, workflow, registry, hashes, plan, cmd_for, authorization)


__all__ = ["run_to_completion", "enqueue_ready"]
