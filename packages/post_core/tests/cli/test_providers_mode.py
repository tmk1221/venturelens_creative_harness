"""T31: `post doctor` (and `GET /api/doctor`, which reuses `doctor_report`) says whether
generation is fake or real -- real is anything but an explicit `POST3_FAKE_PROVIDERS=1`."""
from __future__ import annotations

from post_core.cli import config


def test_doctor_reports_fake_only_when_fake_mode_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("POST_CORE_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")
    assert config.doctor_report()["providers"] == "fake"
    for value in ("0", "", "true"):
        monkeypatch.setenv("POST3_FAKE_PROVIDERS", value)
        assert config.doctor_report()["providers"] == "real"
    monkeypatch.delenv("POST3_FAKE_PROVIDERS")
    assert config.doctor_report()["providers"] == "real"
