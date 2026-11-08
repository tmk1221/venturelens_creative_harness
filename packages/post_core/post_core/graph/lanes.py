"""Lane names and their concurrency limits (ARCHITECTURE.md / T05 spec).

Lives in `graph` rather than `queue` so the registry can reject a node type whose lane no
executor runs (T18 item 4) without importing the queue. A lane only controls concurrency;
`NodeType.lane` defaults to "default".
"""
from __future__ import annotations

DEFAULT_LANES: dict[str, int] = {"default": 2, "single": 1, "render": 1, "remote": 8, "design": 6}


class UnknownLane(ValueError):
    def __init__(self, type_id: str, lane: str) -> None:
        self.type_id, self.lane = type_id, lane
        super().__init__(f"node type {type_id!r} uses unknown lane {lane!r} (known: {', '.join(DEFAULT_LANES)})")


__all__ = ["DEFAULT_LANES", "UnknownLane"]
