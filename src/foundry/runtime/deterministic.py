"""DeterministicRuntime: the Stage-1 no-model sample workflow (report 19.5).

This is the reference implementation behind the :class:`RuntimeAdapter`
boundary, used to validate crash, resume, cancel and duplicate suppression
before the LangGraph adapter exists (report 5.1, 9.3, 10.2). It executes
the fixed workflow ``workflow://fixture/v1`` -- plan, execute, verify --
and keeps NO private durable state: every transition is a canonical event,
and recovery reconstructs progress exclusively from the ledger. The
MISSION_STARTED payload carries the frozen spec and bundle, so a fresh
runtime process holding only the ledger can resume any run.

Idempotency (report 5.1, 15.2): re-delivering a node execution whose
NODE_COMPLETED event already exists emits DUPLICATE_SUPPRESSED and skips;
a node is therefore executed at most once per run.
"""

from __future__ import annotations

from typing import Any

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
    sha256_hex,
)

FIXTURE_WORKFLOW_REF = "workflow://fixture/v1"
FIXTURE_NODES: tuple[str, ...] = ("plan", "execute", "verify")

_ACTOR = "deterministic-runtime"


def derive_node_seed(mission_id: str, node_id: str) -> int:
    """Deterministic worker seed: first 64 bits of sha256(mission_id+node_id)."""
    return int(sha256_hex(f"{mission_id}:{node_id}".encode())[:16], 16)


class DeterministicRuntime:
    """RuntimeAdapter implementation for the fixture workflow."""

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
                f"DeterministicRuntime only executes {FIXTURE_WORKFLOW_REF!r}, "
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

    # -- internal ------------------------------------------------------------

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

    def _advance(self, run_id: str, spec: MissionSpec, bundle: SystemBundle) -> None:
        outputs = self._completed_outputs(run_id)
        for node_id in FIXTURE_NODES:
            if node_id in outputs:
                self._emit(
                    EventTypes.DUPLICATE_SUPPRESSED,
                    spec.mission_id,
                    run_id,
                    bundle.bundle_id,
                    node_id=node_id,
                    payload={"reason": "node already completed; execution skipped"},
                )
                continue
            self._emit(
                EventTypes.NODE_STARTED,
                spec.mission_id,
                run_id,
                bundle.bundle_id,
                node_id=node_id,
            )
            try:
                output = self._run_node(node_id, spec, bundle, outputs)
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

    def _run_node(
        self,
        node_id: str,
        spec: MissionSpec,
        bundle: SystemBundle,
        outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        if node_id == "plan":
            task_input = {
                "task_id": str(spec.inputs.get("task_id", spec.mission_id)),
                "text": spec.inputs["text"],
                "family": str(spec.inputs.get("family", "slugify")),
            }
            return {"task_input": task_input}
        if node_id == "execute":
            seed = derive_node_seed(spec.mission_id, node_id)
            return self._worker.invoke(
                outputs["plan"]["task_input"], bundle.config, seed
            )
        if node_id == "verify":
            return {"output_digest": content_digest(outputs["execute"])}
        raise ValueError(f"unknown fixture node {node_id!r}")

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
                actor=_ACTOR,
                payload=payload or {},
                output_refs=output_refs or [],
            )
        )
