"""T31: what a spending worker records as its cost, and when it refuses to start.

Every spending worker (`still_generate`, `endframe_generate`, `video_generate`) estimates
first, in both modes, with the same args the plan used (`models.estimate_still`/
`estimate_video`), so the cost recorded is the cost the person was shown:
  - no estimate (none returned, zero, or the cost lookup itself failed) -> the worker exits
    2 with a one-sentence reason and never calls the provider: nothing spends blind;
  - the provider reports what the call actually cost -> that amount is recorded;
  - otherwise the estimate is recorded, marked `"estimated": true`. A real call is never
    recorded as costing 0.
"""
from __future__ import annotations

from typing import Callable, Optional

from ...graph.types import Cost
from ...workers.contract import EXIT_USAGE, emit

__all__ = ["estimate_or_refuse", "cost_event", "EXIT_USAGE"]


def estimate_or_refuse(worker: str, model: str, estimate: Callable[[], Optional[Cost]]) -> Optional[Cost]:
    """The pre-call estimate, or None after emitting a failed `result` -- the caller then
    returns `EXIT_USAGE` (2) without touching the provider."""
    try:
        cost = estimate()
        problem = None if cost is not None and cost.amount > 0 else "no cost estimate is available"
    except Exception as exc:  # noqa: BLE001 -- a failed cost lookup is "no estimate", never "free"
        cost, problem = None, f"the cost estimate failed ({exc})"
    if problem is not None:
        emit("result", ok=False, detail=f"{worker}: {problem} for {model}, so it will not spend blind.")
        return None
    return cost


def cost_event(estimate: Cost, actual: Optional[float] = None) -> dict:
    """The `cost` event fields: the provider's own amount if it reported one, else the
    estimate marked as such."""
    if actual is not None and actual > 0:
        return {"amount": float(actual), "unit": estimate.unit, "provider": estimate.provider, "estimated": False}
    return {"amount": estimate.amount, "unit": estimate.unit, "provider": estimate.provider, "estimated": True}
