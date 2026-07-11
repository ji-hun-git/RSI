"""ModuleResolvingRuntime: missions run the module their bundle declares
(report 17.2 integration).

The load-bearing points: a mission resolves its worker from the bundle's
``module_refs`` through the conformance-gated registry (so execution is
gated on admission, not on merely having a callable), an unregistered or
undeclared module cannot run, and resolving through the registry does not
change the canonical event stream.
"""

from __future__ import annotations

import pytest

from foundry.compiler import MissionCompiler
from foundry.contracts import (
    EventTypes,
    MissionRequest,
    ModuleManifest,
    ModuleType,
    SystemBundle,
)
from foundry.ledger import EventLedger
from foundry.modules import ModuleRegistry, ModuleResolvingRuntime
from foundry.runtime import DeterministicRuntime, RuntimeAdapter
from foundry.workers import FixtureWorker

WORKER_REF = "worker.fixture@1.0.0"


def worker_manifest() -> ModuleManifest:
    return ModuleManifest(module_id="worker.fixture", module_type=ModuleType.AGENT, version="1.0.0")


def bundle_declaring(worker_ref: str | None) -> SystemBundle:
    module_refs = {"worker": worker_ref} if worker_ref is not None else {}
    return SystemBundle(
        workflow_ref="workflow://fixture/v1", config={"strategy": "robust"}, module_refs=module_refs
    )


def compile_spec(ledger: EventLedger, bundle: SystemBundle, text: str = "Hello  World--X"):
    request = MissionRequest(
        description="slugify", inputs={"task_id": "t1", "text": text, "family": "slugify"}
    )
    return MissionCompiler(ledger).compile(request, bundle)


def sequence(ledger: EventLedger, run_id: str) -> list[tuple[str, str | None]]:
    return [(e.event_type, e.node_id) for e in ledger.query(run_id=run_id)]


@pytest.fixture()
def registry() -> ModuleRegistry:
    reg = ModuleRegistry()
    reg.register(worker_manifest(), FixtureWorker())
    return reg


def test_satisfies_runtime_adapter_protocol(registry: ModuleRegistry) -> None:
    runtime = ModuleResolvingRuntime(EventLedger(":memory:"), registry)
    assert isinstance(runtime, RuntimeAdapter)


def test_mission_runs_the_declared_module(registry: ModuleRegistry) -> None:
    ledger = EventLedger(":memory:")
    bundle = bundle_declaring(WORKER_REF)
    spec = compile_spec(ledger, bundle)
    run_id = ModuleResolvingRuntime(ledger, registry).start(spec, bundle)
    completed = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)
    assert completed and completed[0].payload["final_output"]["output"] == "hello-world-x"


def test_execution_is_gated_on_admission(registry: ModuleRegistry) -> None:
    # a bundle pointing at a module that was never admitted cannot run
    ledger = EventLedger(":memory:")
    bundle = bundle_declaring("worker.unregistered@1.0.0")
    spec = compile_spec(ledger, bundle)
    with pytest.raises(KeyError, match="not registered"):
        ModuleResolvingRuntime(ledger, registry).start(spec, bundle)


def test_bundle_without_a_worker_slot_cannot_run(registry: ModuleRegistry) -> None:
    ledger = EventLedger(":memory:")
    bundle = bundle_declaring(None)
    spec = compile_spec(ledger, bundle)
    with pytest.raises(KeyError, match="no 'worker' module"):
        ModuleResolvingRuntime(ledger, registry).start(spec, bundle)


def test_resolving_does_not_change_the_event_stream(registry: ModuleRegistry) -> None:
    # the same spec + bundle + worker, run directly vs resolved through the
    # registry, produces the same canonical event shape and final output.
    bundle = bundle_declaring(WORKER_REF)

    direct_ledger = EventLedger(":memory:")
    spec_a = compile_spec(direct_ledger, bundle)
    run_a = DeterministicRuntime(direct_ledger, FixtureWorker()).start(spec_a, bundle)

    resolved_ledger = EventLedger(":memory:")
    spec_b = compile_spec(resolved_ledger, bundle)
    run_b = ModuleResolvingRuntime(resolved_ledger, registry).start(spec_b, bundle)

    assert sequence(direct_ledger, run_a) == sequence(resolved_ledger, run_b)
    out_a = direct_ledger.query(run_id=run_a, event_type=EventTypes.MISSION_COMPLETED)[0]
    out_b = resolved_ledger.query(run_id=run_b, event_type=EventTypes.MISSION_COMPLETED)[0]
    assert out_a.payload["final_output"] == out_b.payload["final_output"]


def test_resume_resolves_the_worker_from_the_recorded_bundle(registry: ModuleRegistry) -> None:
    ledger = EventLedger(":memory:")
    bundle = bundle_declaring(WORKER_REF)
    spec = compile_spec(ledger, bundle)
    runtime = ModuleResolvingRuntime(ledger, registry)
    run_id = runtime.start(spec, bundle)
    # resume reads the bundle from the ledger and resolves the worker from its
    # module_refs; a completed run resumes idempotently (nothing left to do).
    before = len(ledger.query(run_id=run_id))
    assert runtime.resume(run_id) == run_id
    assert len(ledger.query(run_id=run_id)) == before


def test_resume_of_an_unknown_run_raises(registry: ModuleRegistry) -> None:
    runtime = ModuleResolvingRuntime(EventLedger(":memory:"), registry)
    with pytest.raises(KeyError):
        runtime.resume("run_missing")


def test_unknown_run_status_and_cancel_do_not_need_a_worker(registry: ModuleRegistry) -> None:
    runtime = ModuleResolvingRuntime(EventLedger(":memory:"), registry)
    with pytest.raises(KeyError):
        runtime.status("run_missing")
    with pytest.raises(KeyError):
        runtime.cancel("run_missing")
