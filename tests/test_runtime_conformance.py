"""Cross-runtime conformance suite (report 5.1, 9.3, 19.1 exit criteria).

Every RuntimeAdapter must behave identically at the evidence boundary:
same canonical event sequence, same final output digest, same crash /
resume / cancel / duplicate-suppression semantics. The suite runs against
every installed adapter (the deterministic reference always; LangGraph
when the optional dependency group is present) and additionally pins
byte-equivalence between each adapter and the deterministic reference,
because a runtime swap must never change what counts as the record.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from foundry.compiler import MissionCompiler
from foundry.contracts import (
    EventTypes,
    LedgerLike,
    MissionSpec,
    MissionState,
    SystemBundle,
    WorkerLike,
)
from foundry.runtime import (
    FIXTURE_NODES,
    DeterministicRuntime,
    LedgerBackedRuntime,
    RuntimeAdapter,
)
from foundry.workers import FixtureWorker
from test_runtime import (
    CountingWorker,
    CrashingWorker,
    FakeLedger,
    make_bundle,
    make_request,
)

RuntimeFactory = Callable[[LedgerLike, WorkerLike], LedgerBackedRuntime]


def _deterministic(ledger: LedgerLike, worker: WorkerLike) -> LedgerBackedRuntime:
    return DeterministicRuntime(ledger, worker)


def _langgraph(ledger: LedgerLike, worker: WorkerLike) -> LedgerBackedRuntime:
    pytest.importorskip("langgraph")
    from foundry.adapters.langgraph_runtime import LangGraphRuntime

    return LangGraphRuntime(ledger, worker)


RUNTIMES: dict[str, RuntimeFactory] = {
    "deterministic": _deterministic,
    "langgraph": _langgraph,
}


@pytest.fixture(params=sorted(RUNTIMES))
def runtime_factory(request: pytest.FixtureRequest) -> RuntimeFactory:
    return RUNTIMES[request.param]


def compile_on(ledger: FakeLedger, bundle: SystemBundle) -> MissionSpec:
    return MissionCompiler(ledger).compile(make_request(), bundle)


def run_sequence(ledger: FakeLedger, run_id: str) -> list[tuple[str, str | None]]:
    return [(e.event_type, e.node_id) for e in ledger.query(run_id=run_id)]


EXPECTED_FULL_RUN: list[tuple[str, str | None]] = [
    (EventTypes.MISSION_STARTED, None),
    (EventTypes.NODE_STARTED, "plan"),
    (EventTypes.NODE_COMPLETED, "plan"),
    (EventTypes.NODE_STARTED, "execute"),
    (EventTypes.NODE_COMPLETED, "execute"),
    (EventTypes.NODE_STARTED, "verify"),
    (EventTypes.NODE_COMPLETED, "verify"),
    (EventTypes.MISSION_COMPLETED, None),
]


# -- protocol and record shape -------------------------------------------------


def test_satisfies_runtime_adapter_protocol(runtime_factory: RuntimeFactory) -> None:
    runtime = runtime_factory(FakeLedger(), FixtureWorker())
    assert isinstance(runtime, RuntimeAdapter)


def test_full_run_emits_canonical_sequence(runtime_factory: RuntimeFactory) -> None:
    ledger = FakeLedger()
    bundle = make_bundle()
    spec = compile_on(ledger, bundle)
    run_id = runtime_factory(ledger, FixtureWorker()).start(spec, bundle)
    assert run_sequence(ledger, run_id) == EXPECTED_FULL_RUN


def test_rerun_is_deterministic(runtime_factory: RuntimeFactory) -> None:
    bundle = make_bundle()
    digests = []
    for _ in range(2):
        ledger = FakeLedger()
        spec = compile_on(ledger, bundle)
        run_id = runtime_factory(ledger, FixtureWorker()).start(spec, bundle)
        completed = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)
        digests.append(completed[0].payload["output_digest"])
    assert digests[0] == digests[1]


def test_equivalent_to_deterministic_reference(runtime_factory: RuntimeFactory) -> None:
    """A runtime swap must not change the evidence: same spec + bundle in,
    same event shape and final output digest out (report 9.3)."""
    bundle = make_bundle()
    results = {}
    for name, factory in (("candidate", runtime_factory), ("reference", _deterministic)):
        ledger = FakeLedger()
        spec = MissionSpec(
            system_bundle_id=bundle.bundle_id,
            inputs={"task_id": "t-conf", "text": "Hello  World--Conformance!", "family": "slugify"},
        )
        run_id = factory(ledger, FixtureWorker()).start(spec, bundle)
        completed = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)[0]
        results[name] = {
            "sequence": run_sequence(ledger, run_id),
            "final_output": completed.payload["final_output"],
        }
    assert results["candidate"]["sequence"] == results["reference"]["sequence"]
    assert results["candidate"]["final_output"] == results["reference"]["final_output"]


# -- crash, resume, duplicate suppression ---------------------------------------


def test_crash_then_resume_never_reexecutes_completed_nodes(
    runtime_factory: RuntimeFactory,
) -> None:
    ledger = FakeLedger()
    bundle = make_bundle()
    spec = compile_on(ledger, bundle)

    crashing = runtime_factory(ledger, CrashingWorker())
    with pytest.raises(RuntimeError, match="worker died"):
        crashing.start(spec, bundle)

    run_id = ledger.query(event_type=EventTypes.MISSION_STARTED)[-1].run_id
    assert run_id is not None
    assert crashing.status(run_id) == MissionState.FAILED.value
    failed = ledger.query(run_id=run_id, event_type=EventTypes.NODE_FAILED)
    assert [e.node_id for e in failed] == ["execute"]

    healthy = CountingWorker(FixtureWorker())
    resumed = runtime_factory(ledger, healthy).resume(run_id)
    assert resumed == run_id
    assert runtime_factory(ledger, healthy).status(run_id) == MissionState.COMPLETED.value

    # "plan" completed before the crash: suppressed as evidence, never re-run.
    suppressed = ledger.query(run_id=run_id, event_type=EventTypes.DUPLICATE_SUPPRESSED)
    assert "plan" in {e.node_id for e in suppressed}
    completed_nodes = [
        e.node_id for e in ledger.query(run_id=run_id, event_type=EventTypes.NODE_COMPLETED)
    ]
    assert sorted(completed_nodes) == sorted(FIXTURE_NODES)  # each node exactly once
    assert len(healthy.calls) == 1  # only "execute" reached the worker on resume


def test_resume_of_completed_run_is_idempotent(runtime_factory: RuntimeFactory) -> None:
    ledger = FakeLedger()
    bundle = make_bundle()
    spec = compile_on(ledger, bundle)
    runtime = runtime_factory(ledger, FixtureWorker())
    run_id = runtime.start(spec, bundle)
    before = len(ledger.query(run_id=run_id))
    assert runtime.resume(run_id) == run_id
    assert len(ledger.query(run_id=run_id)) == before  # no new events at all


# -- cancellation ----------------------------------------------------------------


def test_cancelled_run_cannot_resume(runtime_factory: RuntimeFactory) -> None:
    ledger = FakeLedger()
    bundle = make_bundle()
    spec = compile_on(ledger, bundle)
    runtime = runtime_factory(ledger, CrashingWorker())
    with pytest.raises(RuntimeError):
        runtime.start(spec, bundle)
    run_id = ledger.query(event_type=EventTypes.MISSION_STARTED)[-1].run_id
    assert run_id is not None

    runtime.cancel(run_id)
    runtime.cancel(run_id)  # idempotent
    assert runtime.status(run_id) == MissionState.CANCELLED.value
    with pytest.raises(RuntimeError, match="cancelled"):
        runtime_factory(ledger, FixtureWorker()).resume(run_id)


def test_completed_run_cannot_cancel(runtime_factory: RuntimeFactory) -> None:
    ledger = FakeLedger()
    bundle = make_bundle()
    spec = compile_on(ledger, bundle)
    runtime = runtime_factory(ledger, FixtureWorker())
    run_id = runtime.start(spec, bundle)
    with pytest.raises(RuntimeError, match="completed"):
        runtime.cancel(run_id)


# -- refusal paths ----------------------------------------------------------------


def test_unknown_run_raises_keyerror(runtime_factory: RuntimeFactory) -> None:
    runtime = runtime_factory(FakeLedger(), FixtureWorker())
    for method in (runtime.resume, runtime.status):
        with pytest.raises(KeyError):
            method("run_does_not_exist")
    with pytest.raises(KeyError):
        runtime.cancel("run_does_not_exist")


def test_mismatched_bundle_pinning_refused(runtime_factory: RuntimeFactory) -> None:
    ledger = FakeLedger()
    bundle = make_bundle(strategy="naive")
    other = make_bundle(strategy="robust")
    spec = compile_on(ledger, bundle)
    with pytest.raises(ValueError, match="exactly one frozen bundle"):
        runtime_factory(ledger, FixtureWorker()).start(spec, other)


def test_foreign_workflow_ref_refused(runtime_factory: RuntimeFactory) -> None:
    ledger = FakeLedger()
    foreign = SystemBundle(workflow_ref="workflow://other/v1")
    spec = MissionSpec(system_bundle_id=foreign.bundle_id, inputs={"text": "x"})
    with pytest.raises(ValueError, match="only executes"):
        runtime_factory(ledger, FixtureWorker()).start(spec, foreign)
