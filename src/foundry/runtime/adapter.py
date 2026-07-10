"""RuntimeAdapter: the runtime boundary protocol (report 9.3, 19.5 weeks 3-4).

Every workflow runtime -- the Stage-1 deterministic sample runtime, the
LangGraph adapter later, MAF/ADK adapters after that -- plugs in behind
this one interface. Compilation happens upstream (the MissionCompiler
produces the frozen MissionSpec); the adapter owns start, resume, cancel
and status observation for a compiled spec.

Two rules keep adapters honest (report 5.1, 9.3):

* Native checkpoints stay opaque. Whatever recovery objects the underlying
  framework persists are internal artifacts; an adapter must never expose
  them to downstream modules or treat them as scientific records.
* Canonical events are the record. Every state transition is emitted to
  the append-only ledger in the canonical envelope, and crash recovery is
  reconstructed from those events -- so conformance is testable under
  crash, replay and duplicated delivery regardless of the runtime inside.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from foundry.contracts import MissionSpec, SystemBundle


@runtime_checkable
class RuntimeAdapter(Protocol):
    """Minimal runtime interface every workflow adapter must implement."""

    def start(self, spec: MissionSpec, bundle: SystemBundle) -> str:
        """Begin executing *spec* under its pinned *bundle*; return a run id."""
        ...

    def resume(self, run_id: str) -> str:
        """Continue an interrupted run from ledger-reconstructed state.

        Completed nodes are never re-executed (duplicate delivery is
        suppressed as evidence). Resuming a cancelled run raises.
        """
        ...

    def cancel(self, run_id: str) -> None:
        """Terminally cancel a run; a cancelled run can never be resumed."""
        ...

    def status(self, run_id: str) -> str:
        """Current MissionState value for the run, derived from the ledger."""
        ...
