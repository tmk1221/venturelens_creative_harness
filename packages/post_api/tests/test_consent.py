"""T30e: `GET/POST /api/projects/{pid}/consent` -- the human-facing read/write for the A-roll
regen consent record `post_core.recipes.consent` already gates `aroll.regenerate`'s
`consent.gate` node on. See `packages/post_core/tests/recipes/test_t30b_recipes.py` for the
gate's own state-machine behavior; this only covers the HTTP surface."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")


def test_consent_get_with_no_record_is_not_recorded(client, project):
    pid = project["id"]
    r = client.get(f"/api/projects/{pid}/consent")
    assert r.status_code == 200, r.text
    assert r.json() == {"presenter": None, "release_path": None, "date": None, "recorded": False}


def test_consent_post_then_get_round_trips(client, project):
    pid = project["id"]
    body = {"presenter": "Presenter", "release_path": "releases/presenter.pdf", "date": "2026-09-22"}
    r = client.post(f"/api/projects/{pid}/consent", json=body)
    assert r.status_code == 200, r.text
    assert r.json() == {**body, "recorded": True}

    r = client.get(f"/api/projects/{pid}/consent")
    assert r.status_code == 200, r.text
    assert r.json() == {**body, "recorded": True}
