from pathlib import Path

from brandkit.vision import ClaudeCliVisionProvider, FakeVisionProvider


def test_fake_vision_provider_records_calls_and_never_shells_out():
    provider = FakeVisionProvider("canned response")
    result = provider.describe([Path("a.jpg"), Path("b.jpg")], "describe these")
    assert result == "canned response"
    assert provider.calls == [([Path("a.jpg"), Path("b.jpg")], "describe these")]


def test_claude_cli_vision_provider_default_command_is_claude_dash_p():
    # Constructing it does not invoke anything — no subprocess call happens here.
    provider = ClaudeCliVisionProvider()
    assert provider.command == ["claude", "-p"]


def test_claude_cli_vision_provider_accepts_custom_command():
    provider = ClaudeCliVisionProvider(command=["some-other-cli"])
    assert provider.command == ["some-other-cli"]
