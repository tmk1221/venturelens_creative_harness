from __future__ import annotations

import pytest

from post_core.ingest.transcribe import base


def test_deepgram_and_local_are_registered():
    assert "deepgram" in base.available()
    assert "local" in base.available()


def test_get_unknown_provider_raises_clear_error():
    with pytest.raises(KeyError):
        base.get("nonexistent-provider")


def test_local_stub_raises_not_implemented():
    provider = base.get("local")
    with pytest.raises(NotImplementedError):
        provider.transcribe("/tmp/whatever.wav", {})
