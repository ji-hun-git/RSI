"""Contextual workers: governed tool use inside a mission (report 9.2, 14).

A ContextualWorker reaches side effects only through the gateway. The
load-bearing points: a tool call inside a mission is authorized and
receipted (a unified audit trail), a denied call is handled gracefully,
and ToolAugmentedRuntime issues a least-privilege per-mission capability
so the worker can call exactly the tools it is permitted and no others.
"""

from __future__ import annotations

from foundry.compiler import MissionCompiler
from foundry.contracts import EventTypes, MissionRequest, SystemBundle
from foundry.ledger import EventLedger
from foundry.runtime import FIXTURE_WORKFLOW_REF, RuntimeAdapter
from foundry.tools import (
    ContextualWorkerConformanceHarness,
    EchoTool,
    SlugifyConfirmWorker,
    ToolAugmentedRuntime,
    ToolContext,
    ToolGateway,
    tool_manifest,
)

SUBJECT = "agent.builder"


def bundle() -> SystemBundle:
    return SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "robust"})


def spec_for(ledger: EventLedger, b: SystemBundle, text: str = "Hello  World--Ctx!"):
    return MissionCompiler(ledger).compile(
        MissionRequest(inputs={"task_id": "t1", "text": text, "family": "slugify"}), b
    )


def gateway_with_echo(ledger: EventLedger) -> ToolGateway:
    gw = ToolGateway(ledger)
    gw.register(tool_manifest("echo"), EchoTool())
    return gw


# -- governed tool use inside a mission ---------------------------------------


def test_satisfies_runtime_adapter_protocol() -> None:
    ledger = EventLedger(":memory:")
    runtime = ToolAugmentedRuntime(
        ledger, gateway_with_echo(ledger), SlugifyConfirmWorker(),
        subject=SUBJECT, tool_actions=["tool.echo"],
    )
    assert isinstance(runtime, RuntimeAdapter)


def test_mission_tool_call_is_authorized_and_receipted() -> None:
    ledger = EventLedger(":memory:")
    gw = gateway_with_echo(ledger)
    b = bundle()
    spec = spec_for(ledger, b)
    runtime = ToolAugmentedRuntime(
        ledger, gw, SlugifyConfirmWorker(), subject=SUBJECT, tool_actions=["tool.echo"]
    )
    run_id = runtime.start(spec, b)

    completed = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)[0]
    out = completed.payload["final_output"]
    assert out["output"] == "hello-world-ctx" and out["confirmed_via"] == "tool"
    # unified audit trail: the mission's ledger holds the tool call events
    authorized = ledger.query(event_type=EventTypes.TOOL_AUTHORIZED)
    results = ledger.query(event_type=EventTypes.TOOL_RESULT)
    assert authorized and results
    # the tool call carries the mission id (correlated to the run)
    assert authorized[0].mission_id == spec.mission_id


def test_worker_degrades_gracefully_when_the_tool_is_denied() -> None:
    ledger = EventLedger(":memory:")
    gw = gateway_with_echo(ledger)
    b = bundle()
    spec = spec_for(ledger, b)
    # the runtime grants NO tool actions: the echo call is denied, and the
    # worker degrades to the local slug instead of crashing.
    runtime = ToolAugmentedRuntime(
        ledger, gw, SlugifyConfirmWorker(), subject=SUBJECT, tool_actions=[]
    )
    run_id = runtime.start(spec, b)
    out = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)[0].payload[
        "final_output"
    ]
    assert out["output"] == "hello-world-ctx" and out["confirmed_via"] == "local"
    assert ledger.query(event_type=EventTypes.TOOL_DENIED)


def test_least_privilege_capability_scopes_the_mission() -> None:
    # a worker granted only tool.echo cannot call a different tool
    ledger = EventLedger(":memory:")
    gw = ToolGateway(ledger)
    gw.register(tool_manifest("echo"), EchoTool())

    class TwoToolWorker:
        def invoke(self, task_input, config, seed, tools):
            from foundry.tools import ToolDenied

            denied = False
            try:
                tools.call("echo", {"x": 1}, action="tool.other")  # not the granted action
            except ToolDenied:
                denied = True
            return {"output": "ok", "other_denied": denied}

    b = bundle()
    spec = spec_for(ledger, b)
    runtime = ToolAugmentedRuntime(
        ledger, gw, TwoToolWorker(), subject=SUBJECT, tool_actions=["tool.echo"]
    )
    run_id = runtime.start(spec, b)
    out = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)[0].payload[
        "final_output"
    ]
    assert out["other_denied"] is True  # the ungranted action was refused


# -- contextual-worker conformance --------------------------------------------


def test_graceful_worker_passes_conformance() -> None:
    harness = ContextualWorkerConformanceHarness()
    evidence = harness.evidence(
        SlugifyConfirmWorker(), [({"text": "A B", "task_id": "t"}, {}, 0)]
    )
    assert evidence.passed
    assert evidence.suite == "contextual-worker/1"


def test_worker_that_ignores_denial_fails_conformance() -> None:
    class RecklessWorker:
        def invoke(self, task_input, config, seed, tools):
            # does not catch ToolDenied: crashes when the tool is refused
            result = tools.call("echo", {"x": 1}, action="tool.echo")
            return {"output": result.output}

    harness = ContextualWorkerConformanceHarness()
    evidence = harness.evidence(RecklessWorker(), [({"text": "x", "task_id": "t"}, {}, 0)])
    assert not evidence.passed
    assert evidence.checks[0].name == "graceful_denial"


# -- ToolContext directly -----------------------------------------------------


def test_tool_context_call_threads_subject_and_mission() -> None:
    from foundry.contracts import CapabilityToken

    ledger = EventLedger(":memory:")
    gw = gateway_with_echo(ledger)
    cap = CapabilityToken(subject=SUBJECT, actions=["tool.echo"], resource_scopes=[])
    ctx = ToolContext(gw, cap, SUBJECT, mission_id="mis_x")
    result = ctx.call("echo", {"a": 1}, action="tool.echo")
    assert result.output == {"echo": {"a": 1}}
    assert result.receipt.mission_id == "mis_x" and result.receipt.subject == SUBJECT
