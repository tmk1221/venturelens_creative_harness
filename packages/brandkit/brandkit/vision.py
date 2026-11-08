"""vision.py — the `VisionProvider` protocol `derive.py` builds a style block through.

Nothing in this package calls a real model directly except `ClaudeCliVisionProvider`,
and nothing in this package's tests may use it — tests always pass a `FakeVisionProvider`
(or any other stand-in satisfying the protocol). `ClaudeCliVisionProvider` shells out to
a configurable terminal-agent CLI (default: `claude -p`); the caller is responsible for
never invoking it from an automated test run.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol


class VisionError(RuntimeError):
    """A vision provider call failed."""


class VisionProvider(Protocol):
    def describe(self, image_paths: list[Path], prompt: str) -> str:
        """Return raw text (expected to contain a JSON object) describing `image_paths`
        per `prompt`."""
        ...


class ClaudeCliVisionProvider:
    """Shells out to a terminal agent CLI with the prompt and image paths. Default
    command is `claude -p`; pass `command` to point at a different CLI/wrapper. NEVER
    invoked from tests — see module docstring."""

    def __init__(self, command: list[str] | None = None):
        self.command = command or ["claude", "-p"]

    def describe(self, image_paths: list[Path], prompt: str) -> str:
        args = [*self.command, prompt, *[str(p) for p in image_paths]]
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise VisionError(f"vision provider command failed: {exc}") from exc
        return result.stdout


class FakeVisionProvider:
    """Test double — returns a canned response and records every call it received.
    Never shells out to anything."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[tuple[list[Path], str]] = []

    def describe(self, image_paths: list[Path], prompt: str) -> str:
        self.calls.append((list(image_paths), prompt))
        return self.response
