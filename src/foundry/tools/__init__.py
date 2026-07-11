"""Capability-bound tool gateway (report sections 10.2, 14.3, 14.4).

Every tool call -- native or MCP -- is terminated here in one internal
model: discovery is separate from authorization, a scoped non-transferable
capability token gates each call (deny-by-default), a named resource is
egress-checked before the tool runs, output is size-bounded and flagged
untrusted, and a receipt with digests, latency and side-effect class is
written to the append-only ledger. A repeated side-effecting call carrying
the same idempotency key returns the recorded receipt instead of running
the effect twice.

    from foundry.tools import ToolGateway, EgressPolicy
"""

from .conformance import (
    TOOL_SUITE,
    ToolCheck,
    ToolConformanceError,
    ToolConformanceEvidence,
    ToolConformanceHarness,
)
from .egress import EgressDecision, EgressPolicy
from .gateway import (
    ToolDenied,
    ToolExecutionError,
    ToolGateway,
    ToolGatewayError,
    ToolProvider,
    ToolReceipt,
    ToolResult,
)
from .providers import (
    AppendLogTool,
    EchoTool,
    FetchTool,
    OversizeTool,
    tool_manifest,
)

__all__ = [
    "TOOL_SUITE",
    "AppendLogTool",
    "EchoTool",
    "EgressDecision",
    "EgressPolicy",
    "FetchTool",
    "OversizeTool",
    "ToolCheck",
    "ToolConformanceError",
    "ToolConformanceEvidence",
    "ToolConformanceHarness",
    "ToolDenied",
    "ToolExecutionError",
    "ToolGateway",
    "ToolGatewayError",
    "ToolProvider",
    "ToolReceipt",
    "ToolResult",
    "tool_manifest",
]
