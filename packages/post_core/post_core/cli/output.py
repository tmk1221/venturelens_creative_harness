"""Uniform JSON output: every `post` command prints exactly one JSON object and exits 0, or
prints `{"error": ...}` and exits non-zero. No command ever writes anything else to stdout.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable

from pydantic import BaseModel


class CLIError(Exception):
    """A refusal with a message meant for the JSON `error` field. `code` is the process
    exit code (defaults to 1; usage errors from argparse itself use 2, matching the worker
    contract's own EXIT_USAGE convention)."""

    def __init__(self, message: str, code: int = 1) -> None:
        self.code = code
        super().__init__(message)


def to_jsonable(obj: Any) -> Any:
    """Recursively turn pydantic models (and dataclasses that expose `model_dump`-less
    shapes) into plain JSON-able values; leaves everything else alone for `json.dumps`."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in obj]
    return obj


def print_json(obj: Any, pretty: bool = False) -> None:
    payload = to_jsonable(obj)
    if pretty:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps(payload, sort_keys=True, default=str))


def run_command(fn: Callable[[], Any], pretty: bool = False) -> int:
    """Call `fn()`, print its result as one JSON object, and return the process exit code.
    Any exception becomes `{"error": "<message>"}` on the same stdout stream (not stderr --
    a caller parsing JSON output should only ever have to look in one place) with a
    non-zero exit code."""
    try:
        result = fn()
    except CLIError as exc:
        print_json({"error": str(exc)}, pretty=pretty)
        return exc.code
    except Exception as exc:  # noqa: BLE001 - every failure becomes a JSON error, not a traceback
        print_json({"error": f"{type(exc).__name__}: {exc}"}, pretty=pretty)
        return 1
    print_json(result, pretty=pretty)
    return 0


__all__ = ["CLIError", "print_json", "run_command", "to_jsonable"]
