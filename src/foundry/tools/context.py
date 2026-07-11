"""ToolContext and the ContextualWorker contract (report 9.2 step 4).

A ``WorkerLike`` module is a pure function -- the right contract for the
deterministic fixtures that make replay exact. A worker that *uses tools*
is a different animal: it has side effects, it is not deterministic when a
tool is external, and it must reach every effect through the capability-
bound gateway. So it is a distinct contract, not a broken ``WorkerLike``.

A :class:`ContextualWorker` receives a :class:`ToolContext` -- the gateway,
the mission's capability, and the calling subject -- and calls tools through
it. Every such call is authorized, egress-checked and receipted by the
gateway, so a tool-using mission carries a unified audit trail (its node
events and its tool events in one ledger). The worker never holds a raw
network or filesystem handle; the context is its only door to a side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from foundry.contracts import CapabilityToken

from .gateway import ToolGateway, ToolResult


@dataclass(frozen=True)
class ToolContext:
    """A worker's governed door to tools: the gateway plus its grant."""

    gateway: ToolGateway
    capability: CapabilityToken
    subject: str
    mission_id: str | None = None

    def call(
        self,
        tool_id: str,
        args: dict[str, Any],
        *,
        action: str,
        resource: str | None = None,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        """Call a tool through the gateway under this context's capability."""
        return self.gateway.call(
            tool_id,
            args,
            self.capability,
            subject=self.subject,
            action=action,
            resource=resource,
            mission_id=self.mission_id,
            idempotency_key=idempotency_key,
        )


@runtime_checkable
class ContextualWorker(Protocol):
    """A worker that reaches side effects only through a :class:`ToolContext`."""

    def invoke(
        self,
        task_input: dict[str, Any],
        config: dict[str, Any],
        seed: int,
        tools: ToolContext,
    ) -> dict[str, Any]: ...
