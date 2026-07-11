"""Capability-bound tool gateway (report sections 10.2, 14.3, 14.4) and the
contextual-worker layer that lets a mission use tools under governance.

Every tool call -- native or MCP -- is terminated in one internal model:
discovery is separate from authorization, a scoped non-transferable
capability token gates each call (deny-by-default), a named resource is
egress-checked before the tool runs, output is size-bounded and flagged
untrusted, and a receipt with digests, latency and side-effect class is
written to the append-only ledger. A repeated side-effecting call carrying
the same idempotency key returns the recorded receipt instead of running
the effect twice. `register_conformant` admits tools only after a
side-effect-aware conformance suite; `ToolAugmentedRuntime` runs a
`ContextualWorker` whose tool use flows through the gateway.

    from foundry.tools import ToolGateway, EgressPolicy, ToolAugmentedRuntime
"""

from .conformance import (
    TOOL_SUITE,
    TOOL_WORKER_SUITE,
    ContextualWorkerConformanceHarness,
    ToolCheck,
    ToolConformanceError,
    ToolConformanceEvidence,
    ToolConformanceHarness,
)
from .context import ContextualWorker, ToolContext
from .egress import EgressDecision, EgressPolicy, system_resolver
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
    SlugifyConfirmWorker,
    tool_manifest,
)
from .runtime import ToolAugmentedRuntime

__all__ = [
    "TOOL_SUITE",
    "TOOL_WORKER_SUITE",
    "AppendLogTool",
    "ContextualWorker",
    "ContextualWorkerConformanceHarness",
    "EchoTool",
    "EgressDecision",
    "EgressPolicy",
    "FetchTool",
    "OversizeTool",
    "SlugifyConfirmWorker",
    "ToolAugmentedRuntime",
    "ToolCheck",
    "ToolConformanceError",
    "ToolConformanceEvidence",
    "ToolConformanceHarness",
    "ToolContext",
    "ToolDenied",
    "ToolExecutionError",
    "ToolGateway",
    "ToolGatewayError",
    "ToolProvider",
    "ToolReceipt",
    "ToolResult",
    "system_resolver",
    "tool_manifest",
]
