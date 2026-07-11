"""ToolAugmentedRuntime: run a mission whose worker uses governed tools.

This makes the tool gateway load-bearing in a mission. It composes over
``DeterministicRuntime`` (no base-runtime change) by wrapping a
:class:`ContextualWorker` plus a per-mission :class:`ToolContext` into a
plain ``WorkerLike`` closure: the runtime issues a least-privilege
capability scoped to exactly the tool actions the worker is permitted,
builds the context, and runs the ordinary plan/execute/verify workflow --
except the execute node's worker now reaches tools through the gateway.

Honesty about replay: a fixture mission is replay-exact because its worker
is pure. A tool-using mission is only as reproducible as its tools; when a
tool is external it is not replay-exact, and that is expected. The gateway
receipts every call, so the mission is still fully *auditable* even when it
is not reproducible.
"""

from __future__ import annotations

from typing import Any

from foundry.contracts import (
    ArtifactStoreLike,
    EventTypes,
    LedgerLike,
    MissionSpec,
    SystemBundle,
)
from foundry.policy import CapabilityIssuer
from foundry.runtime import DeterministicRuntime

from .context import ContextualWorker, ToolContext

_DEFAULT_TTL = 3600


class _BoundContextualWorker:
    """Adapts a ContextualWorker + ToolContext to the ``WorkerLike`` shape the
    execute node calls, so the contextual worker composes over the runtime."""

    def __init__(self, worker: ContextualWorker, context: ToolContext) -> None:
        self._worker = worker
        self._context = context

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        return self._worker.invoke(task_input, config, seed, self._context)


class ToolAugmentedRuntime:
    """RuntimeAdapter that runs a ContextualWorker under a governed tool context."""

    def __init__(
        self,
        ledger: LedgerLike,
        gateway: Any,
        worker: ContextualWorker,
        *,
        subject: str,
        tool_actions: list[str],
        tool_scopes: list[str] | None = None,
        issuer: CapabilityIssuer | None = None,
        artifact_store: ArtifactStoreLike | None = None,
        ttl_seconds: int = _DEFAULT_TTL,
    ) -> None:
        self._ledger = ledger
        self._gateway = gateway
        self._worker = worker
        self._subject = subject
        self._tool_actions = list(tool_actions)
        self._tool_scopes = list(tool_scopes or [])
        self._issuer = issuer or CapabilityIssuer()
        self._artifact_store = artifact_store
        self._ttl = ttl_seconds

    def _runtime_for(self, mission_id: str | None) -> DeterministicRuntime:
        # A least-privilege, per-mission grant: exactly the tool actions the
        # worker is permitted, nothing more (report 14: scoped capabilities).
        capability = self._issuer.issue(
            self._subject,
            actions=self._tool_actions,
            resource_scopes=self._tool_scopes,
            ttl_seconds=self._ttl,
            mission_id=mission_id,
        )
        context = ToolContext(self._gateway, capability, self._subject, mission_id)
        bound = _BoundContextualWorker(self._worker, context)
        return DeterministicRuntime(self._ledger, bound, self._artifact_store)

    def start(self, spec: MissionSpec, bundle: SystemBundle) -> str:
        return self._runtime_for(spec.mission_id).start(spec, bundle)

    def resume(self, run_id: str) -> str:
        started = self._ledger.query(run_id=run_id, event_type=EventTypes.MISSION_STARTED)
        if not started:
            raise KeyError(f"unknown run {run_id!r}")
        mission_id = started[0].mission_id
        return self._runtime_for(mission_id).resume(run_id)

    def cancel(self, run_id: str) -> None:
        self._runtime_for(None).cancel(run_id)

    def status(self, run_id: str) -> str:
        return self._runtime_for(None).status(run_id)
