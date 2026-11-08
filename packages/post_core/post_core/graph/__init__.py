"""The content-addressed build graph: the app's only state system (ARCHITECTURE.md §1)."""
from __future__ import annotations

from . import approvals
from .hashing import canonical_json, compute_hashes, node_input_hash
from .plan import Plan, plan
from .registry import (
    BUILTINS,
    NodeRegistry,
    UnknownNodeType,
    builtin_registry,
    register_builtins,
)
from .state import (
    NodeState,
    artifact_dir,
    compute_states,
    read_history,
    read_manifest,
    record_history_entry,
)
from .types import (
    ANY_TYPE,
    Cost,
    HandleType,
    InputSpec,
    Kind,
    NodeType,
    NoParams,
    OutputSpec,
    types_compatible,
)
from .workflow import (
    Edge,
    GraphCycleError,
    Node,
    Workflow,
    WorkflowError,
    assert_valid,
    topo_order,
    validate,
)

__all__ = [
    "approvals",
    "canonical_json",
    "compute_hashes",
    "node_input_hash",
    "Plan",
    "plan",
    "BUILTINS",
    "NodeRegistry",
    "UnknownNodeType",
    "builtin_registry",
    "register_builtins",
    "NodeState",
    "artifact_dir",
    "compute_states",
    "read_history",
    "read_manifest",
    "record_history_entry",
    "ANY_TYPE",
    "Cost",
    "HandleType",
    "InputSpec",
    "Kind",
    "NodeType",
    "NoParams",
    "OutputSpec",
    "types_compatible",
    "Edge",
    "GraphCycleError",
    "Node",
    "Workflow",
    "WorkflowError",
    "assert_valid",
    "topo_order",
    "validate",
]
