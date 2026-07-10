"""DeterministicRuntime: the Stage-1 no-model sample workflow (report 19.5).

This is the reference implementation behind the :class:`RuntimeAdapter`
boundary, used to validate crash, resume, cancel and duplicate suppression
before other adapters exist (report 5.1, 9.3, 10.2). It executes the fixed
workflow ``workflow://fixture/v1`` -- plan, execute, verify -- as a plain
in-order loop and keeps NO private durable state: every transition is a
canonical event, and recovery reconstructs progress exclusively from the
ledger (all of which lives in :class:`LedgerBackedRuntime`; this class
only supplies the scheduling loop). The MISSION_STARTED payload carries
the frozen spec and bundle, so a fresh runtime process holding only the
ledger can resume any run.

Idempotency (report 5.1, 15.2): re-delivering a node execution whose
NODE_COMPLETED event already exists emits DUPLICATE_SUPPRESSED and skips;
a node is therefore executed at most once per run.
"""

from __future__ import annotations

from typing import ClassVar

from foundry.contracts import MissionSpec, SystemBundle

from .base import LedgerBackedRuntime
from .fixture_workflow import (
    FIXTURE_NODES,
    FIXTURE_WORKFLOW_REF,
    derive_node_seed,
    run_fixture_node,
)

__all__ = [
    "FIXTURE_NODES",
    "FIXTURE_WORKFLOW_REF",
    "DeterministicRuntime",
    "derive_node_seed",
    "run_fixture_node",
]


class DeterministicRuntime(LedgerBackedRuntime):
    """RuntimeAdapter implementation for the fixture workflow."""

    actor: ClassVar[str] = "deterministic-runtime"

    def _advance(self, run_id: str, spec: MissionSpec, bundle: SystemBundle) -> None:
        outputs = self._completed_outputs(run_id)
        for node_id in FIXTURE_NODES:
            self._execute_node(run_id, spec, bundle, node_id, outputs)
        self._finalize(run_id, spec, bundle, outputs)
