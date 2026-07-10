"""LedgerBackedRuntime: shared control plane for every runtime adapter.

The RuntimeAdapter rules (report 9.3) are runtime-independent: canonical
events are the record, recovery reconstructs progress exclusively from the
ledger, duplicate delivery is suppressed as evidence, and native framework
checkpoints stay opaque. This base class owns exactly that shared control
plane -- start validation, resume/cancel/status derived purely from ledger
events, the per-node event envelope and mission finalization -- so that a
concrete adapter (deterministic loop, LangGraph graph, MAF/ADK later) only
supplies *how* the workflow advances, never *what counts as the record*.

Keeping this logic in one place is also a conformance guarantee: two
adapters running the same spec and bundle must produce the same canonical
event sequence and the same final output digest, which
``tests/test_runtime_conformance.py`` pins across all installed runtimes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from foundry.contracts import (
    ArtifactStoreLike,
    Event,
    EventTypes,
    LedgerLike,
    MissionSpec,
    MissionState,
    SystemBundle,
    WorkerLike,
    canonical_json,
    content_digest,
    new_id,
)

from .fixture_workflow import FIXTURE_WORKFLOW_REF, run_fixture_node


class LedgerBackedRuntime(ABC):
    """Common RuntimeAdapter behavior over an append-only ledger."""

    actor: ClassVar[str] = "runtime"

    def __init__(
        self,
        ledger: LedgerLike,
        worker: WorkerLike,
        artifact_store: ArtifactStoreLike | None = None,
    ) -> None:
        self._ledger = ledger
        self._worker = worker
        self._artifact_store = artifact_store

    # -- RuntimeAdapter interface -------------------------------------------

    def start(self, spec: MissionSpec, bundle: SystemBundle) -> str:
        """Run *spec* under its pinned *bundle* from the beginning."""
        if bundle.workflow_ref != FIXTURE_WORKFLOW_REF:
            raise ValueError(
                f"{type(self).__name__} only executes {FIXTURE_WORKFLOW_REF!r}, "
                f"got {bundle.workflow_ref!r}"
            )
        if spec.system_bundle_id != bundle.bundle_id:
            raise ValueError(
                f"spec is pinned to bundle {spec.system_bundle_id!r} but "
                f"{bundle.bundle_id!r} was supplied; missions run under "
                "exactly one frozen bundle"
            )
        run_id = new_id("run")
        self._emit(
            EventTypes.MISSION_STARTED,
            spec.mission_id,
            run_id,
            bundle.bundle_id,
            payload={
                "workflow_ref": bundle.workflow_ref,
                "spec": spec.model_dump(mode="json"),
                "bundle": bundle.model_dump(mode="json"),
            },
        )
        self._advance(run_id, spec, bundle)
        return run_id

    def resume(self, run_id: str) -> str:
        """Continue *run_id* from ledger-reconstructed state."""
        started = self._require_started(run_id)
        if self._ledger.query(run_id=run_id, event_type=EventTypes.MISSION_CANCELLED):
            raise RuntimeError(f"run {run_id!r} was cancelled and cannot be resumed")
        if self._ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED):
            return run_id  # idempotent: nothing left to do
        spec = MissionSpec.model_validate(started.payload["spec"])
        bundle = SystemBundle.model_validate(started.payload["bundle"])
        self._emit(EventTypes.MISSION_RESUMED, spec.mission_id, run_id, bundle.bundle_id)
        self._advance(run_id, spec, bundle)
        return run_id

    def cancel(self, run_id: str) -> None:
        """Terminally cancel *run_id*; idempotent, but a completed run refuses."""
        started = self._require_started(run_id)
        if self._ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED):
            raise RuntimeError(f"run {run_id!r} already completed and cannot be cancelled")
        if self._ledger.query(run_id=run_id, event_type=EventTypes.MISSION_CANCELLED):
            return
        self._emit(
            EventTypes.MISSION_CANCELLED,
            started.mission_id,
            run_id,
            started.system_bundle_id,
        )

    def status(self, run_id: str) -> str:
        """MissionState value derived purely from the ledger."""
        events = self._ledger.query(run_id=run_id)
        if not events:
            raise KeyError(f"unknown run {run_id!r}")
        types = {event.event_type for event in events}
        if EventTypes.MISSION_CANCELLED in types:
            return MissionState.CANCELLED.value
        if EventTypes.MISSION_COMPLETED in types:
            return MissionState.COMPLETED.value
        if EventTypes.NODE_FAILED in types:
            return MissionState.FAILED.value
        return MissionState.STARTED.value

    # -- adapter hook ---------------------------------------------------------

    @abstractmethod
    def _advance(self, run_id: str, spec: MissionSpec, bundle: SystemBundle) -> None:
        """Drive the workflow to completion, calling :meth:`_execute_node`
        for every node in workflow order and :meth:`_finalize` at the end.

        How the adapter schedules the calls (a plain loop, a LangGraph
        graph, a remote engine) is its own business; the events those two
        helpers emit are the canonical record either way.
        """

    # -- shared helpers -------------------------------------------------------

    def _require_started(self, run_id: str) -> Event:
        started = self._ledger.query(
            run_id=run_id, event_type=EventTypes.MISSION_STARTED
        )
        if not started:
            raise KeyError(f"unknown run {run_id!r}")
        return started[0]

    def _completed_outputs(self, run_id: str) -> dict[str, dict[str, Any]]:
        """Node outputs recovered from NODE_COMPLETED events (the only state)."""
        outputs: dict[str, dict[str, Any]] = {}
        for event in self._ledger.query(
            run_id=run_id, event_type=EventTypes.NODE_COMPLETED
        ):
            assert event.node_id is not None
            outputs[event.node_id] = event.payload["output"]
        return outputs

    def _execute_node(
        self,
        run_id: str,
        spec: MissionSpec,
        bundle: SystemBundle,
        node_id: str,
        outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Execute one node at most once, wrapped in the canonical envelope.

        A node whose NODE_COMPLETED already exists is suppressed as
        evidence (DUPLICATE_SUPPRESSED) and its recorded output reused; a
        failing node becomes NODE_FAILED evidence before the exception
        propagates to the caller (crash-shaped, deliberately).
        """
        if node_id in outputs:
            self._emit(
                EventTypes.DUPLICATE_SUPPRESSED,
                spec.mission_id,
                run_id,
                bundle.bundle_id,
                node_id=node_id,
                payload={"reason": "node already completed; execution skipped"},
            )
            return outputs[node_id]
        self._emit(
            EventTypes.NODE_STARTED,
            spec.mission_id,
            run_id,
            bundle.bundle_id,
            node_id=node_id,
        )
        try:
            output = run_fixture_node(node_id, spec, bundle, outputs, self._worker)
        except Exception as exc:
            # Not defensive: convert the failure into evidence, then crash.
            self._emit(
                EventTypes.NODE_FAILED,
                spec.mission_id,
                run_id,
                bundle.bundle_id,
                node_id=node_id,
                payload={"error": str(exc)},
            )
            raise
        outputs[node_id] = output
        self._emit(
            EventTypes.NODE_COMPLETED,
            spec.mission_id,
            run_id,
            bundle.bundle_id,
            node_id=node_id,
            payload={"output": output, "output_digest": content_digest(output)},
        )
        return output

    def _finalize(
        self,
        run_id: str,
        spec: MissionSpec,
        bundle: SystemBundle,
        outputs: dict[str, dict[str, Any]],
    ) -> None:
        final_output = outputs["execute"]
        output_refs: list[str] = []
        if self._artifact_store is not None:
            output_refs.append(
                self._artifact_store.put(canonical_json(final_output), "application/json")
            )
        self._emit(
            EventTypes.MISSION_COMPLETED,
            spec.mission_id,
            run_id,
            bundle.bundle_id,
            payload={
                "final_output": final_output,
                "output_digest": outputs["verify"]["output_digest"],
            },
            output_refs=output_refs,
        )

    def _emit(
        self,
        event_type: str,
        mission_id: str | None,
        run_id: str,
        system_bundle_id: str | None,
        *,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
        output_refs: list[str] | None = None,
    ) -> Event:
        return self._ledger.append(
            Event(
                event_type=event_type,
                mission_id=mission_id,
                run_id=run_id,
                node_id=node_id,
                system_bundle_id=system_bundle_id,
                actor=self.actor,
                payload=payload or {},
                output_refs=output_refs or [],
            )
        )
