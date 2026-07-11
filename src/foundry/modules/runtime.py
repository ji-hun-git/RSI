"""ModuleResolvingRuntime: run a mission under the module the bundle declares.

This is the integration that makes the module registry load-bearing. A
``SystemBundle`` pins its worker by ``module_id@version`` in ``module_refs``;
until now nothing resolved that reference, so the runtime ran whatever
worker it was handed. This adapter instead resolves the worker from the
bundle through a conformance-gated :class:`~foundry.modules.ModuleRegistry`,
so a mission runs the exact module its bundle names, and only if that
module was admitted (passed its conformance suite). A bundle that declares
an unregistered or unconformant module cannot run at all -- execution is
gated on admission, not merely on having some callable.

It is a pure composition over the existing runtime (report 9.3: the
canonical events stay the record). For a given spec, bundle and resolved
worker it produces the same canonical event stream as running
``DeterministicRuntime`` on that worker directly, so resolving through the
registry changes admission, never the evidence.
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
from foundry.runtime import DeterministicRuntime

from .swap import resolve_worker


class _UnresolvedWorker:
    """Placeholder for the worker-free operations (cancel/status), which read
    the ledger and must never invoke a worker."""

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        raise RuntimeError("cancel/status must not invoke a worker")


class ModuleResolvingRuntime:
    """RuntimeAdapter that resolves the worker from the bundle's module_refs."""

    def __init__(
        self,
        ledger: LedgerLike,
        registry: Any,
        artifact_store: ArtifactStoreLike | None = None,
        *,
        slot: str = "worker",
    ) -> None:
        self._ledger = ledger
        self._registry = registry
        self._artifact_store = artifact_store
        self._slot = slot

    def _runtime_for(self, bundle: SystemBundle) -> DeterministicRuntime:
        worker = resolve_worker(bundle, self._registry, self._slot)
        return DeterministicRuntime(self._ledger, worker, self._artifact_store)

    def start(self, spec: MissionSpec, bundle: SystemBundle) -> str:
        """Resolve the declared worker, then run the mission under it."""
        return self._runtime_for(bundle).start(spec, bundle)

    def resume(self, run_id: str) -> str:
        started = self._ledger.query(
            run_id=run_id, event_type=EventTypes.MISSION_STARTED
        )
        if not started:
            raise KeyError(f"unknown run {run_id!r}")
        bundle = SystemBundle.model_validate(started[0].payload["bundle"])
        return self._runtime_for(bundle).resume(run_id)

    def cancel(self, run_id: str) -> None:
        self._worker_free().cancel(run_id)

    def status(self, run_id: str) -> str:
        return self._worker_free().status(run_id)

    def _worker_free(self) -> DeterministicRuntime:
        return DeterministicRuntime(self._ledger, _UnresolvedWorker(), self._artifact_store)
