"""The worker contract and the subprocess runner that enforces it.

`contract` defines the wire format (`##POST {json}` events, exit codes). `runner.run`
executes a worker speaking that contract and classifies its outcome from disk evidence,
not narration. `legacy.run_legacy` adapts scripts that do not speak the contract.
"""
from __future__ import annotations

from . import contract, legacy, runner
from .contract import EXIT_FAILED, EXIT_NEEDS_HUMAN, EXIT_OK, EXIT_RETRY_LATER, EXIT_USAGE, emit
from .legacy import run_legacy
from .runner import FAILED, INTERRUPTED, NEEDS_HUMAN, OK, RETRY_LATER, RunResult, run

__all__ = [
    "contract",
    "runner",
    "legacy",
    "run",
    "run_legacy",
    "RunResult",
    "emit",
    "OK",
    "FAILED",
    "RETRY_LATER",
    "NEEDS_HUMAN",
    "INTERRUPTED",
    "EXIT_OK",
    "EXIT_FAILED",
    "EXIT_USAGE",
    "EXIT_RETRY_LATER",
    "EXIT_NEEDS_HUMAN",
]
