"""Tests for the mission compiler, deterministic runtime, fixture worker
and fixture task corpus (report 10.2, 19.1, 19.5 weeks 3-4).

Uses an in-memory fake ledger conforming to LedgerLike; the real ledger
package is built independently and is deliberately not imported.
"""

from __future__ import annotations

from typing import Any

import pydantic
import pytest

from foundry.compiler import EXACT_MATCH_ORACLE_REF, MissionCompiler
from foundry.contracts import (
    Event,
    EventTypes,
    Integrity,
    LedgerLike,
    MissionRequest,
    MissionSpec,
    MissionState,
    PromotionStatus,
    SystemBundle,
    WorkerLike,
    content_digest,
    utcnow,
)
from foundry.runtime import (
    FIXTURE_NODES,
    FIXTURE_WORKFLOW_REF,
    DeterministicRuntime,
    RuntimeAdapter,
    derive_node_seed,
)
from foundry.workers import (
    FixtureTask,
    FixtureWorker,
    generate_task_sets,
    naive_slugify,
    robust_slugify,
)

# -- fakes --------------------------------------------------------------------


class FakeLedger:
    """Minimal in-memory LedgerLike: append-only list plus filters."""

    def __init__(self, events: list[Event] | None = None) -> None:
        self.events: list[Event] = events if events is not None else []
        self._by_id: dict[str, Event] = {e.event_id: e for e in self.events}

    def append(self, event: Event) -> Event:
        if event.event_id in self._by_id:
            return self._by_id[event.event_id]
        prev = self.events[-1].integrity if self.events else None
        recorded = event.with_integrity(
            Integrity(
                producer="fake-ledger",
                digest=event.payload_digest(),
                prev_digest=prev.digest if prev else None,
                sequence=len(self.events),
            ),
            utcnow(),
        )
        self.events.append(recorded)
        self._by_id[recorded.event_id] = recorded
        return recorded

    def query(
        self,
        *,
        mission_id: str | None = None,
        run_id: str | None = None,
        experiment_id: str | None = None,
        event_type: str | None = None,
    ) -> list[Event]:
        return [
            e
            for e in self.events
            if (mission_id is None or e.mission_id == mission_id)
            and (run_id is None or e.run_id == run_id)
            and (experiment_id is None or e.experiment_id == experiment_id)
            and (event_type is None or e.event_type == event_type)
        ]


class CrashingLedger(FakeLedger):
    """Simulates process death at a chosen transition: append raises before
    recording, exactly like a crash between two ledger writes."""

    def __init__(
        self, events: list[Event] | None = None, *, crash_on: tuple[str, str | None] | None = None
    ) -> None:
        super().__init__(events)
        self.crash_on = crash_on  # (event_type, node_id)

    def append(self, event: Event) -> Event:
        if self.crash_on is not None and (event.event_type, event.node_id) == self.crash_on:
            raise RuntimeError("simulated crash")
        return super().append(event)


class CountingWorker:
    """WorkerLike wrapper counting invocations per node input."""

    def __init__(self, inner: WorkerLike) -> None:
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    def invoke(
        self, task_input: dict[str, Any], config: dict[str, Any], seed: int
    ) -> dict[str, Any]:
        self.calls.append({"task_input": task_input, "seed": seed})
        return self.inner.invoke(task_input, config, seed)


class CrashingWorker:
    """WorkerLike that always raises, simulating a crash during execute."""

    def invoke(
        self, task_input: dict[str, Any], config: dict[str, Any], seed: int
    ) -> dict[str, Any]:
        raise RuntimeError("worker died mid-execution")


# -- helpers ------------------------------------------------------------------


def make_bundle(strategy: str = "robust", status: PromotionStatus = PromotionStatus.DRAFT) -> SystemBundle:
    return SystemBundle(
        workflow_ref=FIXTURE_WORKFLOW_REF,
        config={"strategy": strategy},
        status=status,
    )


def make_request(text: str = "Hello  World—Test!", task_id: str = "t-001") -> MissionRequest:
    return MissionRequest(
        description="Slugify the provided text.",
        inputs={"task_id": task_id, "text": text, "family": "slugify"},
    )


def compile_spec(ledger: FakeLedger, bundle: SystemBundle, **request_kwargs: Any) -> MissionSpec:
    return MissionCompiler(ledger).compile(make_request(**request_kwargs), bundle)


def event_types_for_run(ledger: FakeLedger, run_id: str) -> list[str]:
    return [e.event_type for e in ledger.query(run_id=run_id)]


def final_payload(ledger: FakeLedger, run_id: str) -> dict[str, Any]:
    completed = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)
    assert len(completed) == 1
    return completed[0].payload


# -- compiler -----------------------------------------------------------------


class TestMissionCompiler:
    def test_spec_is_pinned_frozen_and_derived(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle()
        spec = compile_spec(ledger, bundle)

        assert spec.system_bundle_id == bundle.bundle_id
        assert len(spec.objectives) == 1
        assert spec.objectives[0].id == "obj:t-001:primary"
        assert len(spec.acceptance_criteria) == 1
        criterion = spec.acceptance_criteria[0]
        assert criterion.id == "ac:t-001:exact-match"
        assert criterion.oracle == EXACT_MATCH_ORACLE_REF
        assert spec.inputs["text"] == "Hello  World—Test!"
        with pytest.raises(pydantic.ValidationError):
            spec.task_type = "changed"  # type: ignore[misc]

    def test_emits_mission_compiled_with_spec_digest(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle()
        spec = compile_spec(ledger, bundle)

        events = ledger.query(
            mission_id=spec.mission_id, event_type=EventTypes.MISSION_COMPILED
        )
        assert len(events) == 1
        event = events[0]
        assert event.system_bundle_id == bundle.bundle_id
        assert event.payload["spec_digest"] == content_digest(spec)
        assert event.payload["request_id"] == spec.request_ref
        assert event.integrity is not None

    def test_derivation_is_deterministic(self) -> None:
        bundle = make_bundle()
        spec_a = compile_spec(FakeLedger(), bundle)
        spec_b = compile_spec(FakeLedger(), bundle)
        exclude = {"mission_id", "request_ref", "created_at"}
        assert spec_a.model_dump(exclude=exclude) == spec_b.model_dump(exclude=exclude)

    @pytest.mark.parametrize(
        "status", [PromotionStatus.DEPRECATED, PromotionStatus.REVOKED]
    )
    def test_refuses_retired_bundles(self, status: PromotionStatus) -> None:
        ledger = FakeLedger()
        bundle = make_bundle(status=status)
        with pytest.raises(ValueError, match=status.value):
            compile_spec(ledger, bundle)
        assert ledger.events == []


# -- runtime: happy path ------------------------------------------------------


class TestRuntimeHappyPath:
    def test_conforms_to_runtime_adapter_protocol(self) -> None:
        runtime = DeterministicRuntime(FakeLedger(), FixtureWorker())
        assert isinstance(runtime, RuntimeAdapter)
        assert isinstance(FakeLedger(), LedgerLike)
        assert isinstance(FixtureWorker(), WorkerLike)

    def test_full_run_emits_complete_ordered_event_sequence(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle()
        spec = compile_spec(ledger, bundle)
        run_id = DeterministicRuntime(ledger, FixtureWorker()).start(spec, bundle)

        assert event_types_for_run(ledger, run_id) == [
            EventTypes.MISSION_STARTED,
            EventTypes.NODE_STARTED,
            EventTypes.NODE_COMPLETED,
            EventTypes.NODE_STARTED,
            EventTypes.NODE_COMPLETED,
            EventTypes.NODE_STARTED,
            EventTypes.NODE_COMPLETED,
            EventTypes.MISSION_COMPLETED,
        ]
        node_events = [
            e for e in ledger.query(run_id=run_id) if e.node_id is not None
        ]
        assert [e.node_id for e in node_events] == [
            "plan", "plan", "execute", "execute", "verify", "verify"
        ]
        for event in ledger.query(run_id=run_id):
            assert event.mission_id == spec.mission_id
            assert event.run_id == run_id
            assert event.system_bundle_id == bundle.bundle_id
        for event in ledger.query(run_id=run_id, event_type=EventTypes.NODE_COMPLETED):
            assert event.payload["output_digest"] == content_digest(event.payload["output"])

    def test_final_output_is_robust_slug(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle("robust")
        spec = compile_spec(ledger, bundle, text="Hello  World—Test!")
        run_id = DeterministicRuntime(ledger, FixtureWorker()).start(spec, bundle)

        payload = final_payload(ledger, run_id)
        assert payload["final_output"]["output"] == "hello-world-test"
        assert payload["output_digest"] == content_digest(payload["final_output"])
        runtime = DeterministicRuntime(ledger, FixtureWorker())
        assert runtime.status(run_id) == MissionState.COMPLETED.value

    def test_two_fresh_runs_produce_identical_final_output(self) -> None:
        bundle = make_bundle()
        spec = compile_spec(FakeLedger(), bundle)
        ledger_a, ledger_b = FakeLedger(), FakeLedger()
        run_a = DeterministicRuntime(ledger_a, FixtureWorker()).start(spec, bundle)
        run_b = DeterministicRuntime(ledger_b, FixtureWorker()).start(spec, bundle)

        payload_a = final_payload(ledger_a, run_a)
        payload_b = final_payload(ledger_b, run_b)
        assert payload_a["output_digest"] == payload_b["output_digest"]
        assert payload_a["final_output"] == payload_b["final_output"]

    def test_worker_seed_is_derived_from_mission_and_node(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle()
        spec = compile_spec(ledger, bundle)
        worker = CountingWorker(FixtureWorker())
        DeterministicRuntime(ledger, worker).start(spec, bundle)

        assert len(worker.calls) == 1
        assert worker.calls[0]["seed"] == derive_node_seed(spec.mission_id, "execute")

    def test_start_rejects_mismatched_bundle_and_unknown_workflow(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle()
        other = SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "naive"})
        spec = compile_spec(ledger, bundle)
        runtime = DeterministicRuntime(ledger, FixtureWorker())
        with pytest.raises(ValueError, match="pinned"):
            runtime.start(spec, other)
        alien = SystemBundle(workflow_ref="workflow://other/v9")
        with pytest.raises(ValueError, match="workflow"):
            runtime.start(spec, alien)


# -- runtime: crash, resume, duplicate suppression, cancel --------------------


class TestCrashAndResume:
    def test_crash_during_execute_then_resume_completes(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle()
        spec = compile_spec(ledger, bundle)
        crashed = DeterministicRuntime(ledger, CrashingWorker())
        with pytest.raises(RuntimeError, match="worker died"):
            crashed.start(spec, bundle)

        run_id = ledger.query(event_type=EventTypes.MISSION_STARTED)[0].run_id
        assert run_id is not None
        failed = ledger.query(run_id=run_id, event_type=EventTypes.NODE_FAILED)
        assert [e.node_id for e in failed] == ["execute"]
        healthy = DeterministicRuntime(FakeLedger(ledger.events), FixtureWorker())
        assert healthy.resume(run_id) == run_id

        completed = ledger.query(run_id=run_id, event_type=EventTypes.NODE_COMPLETED)
        assert sorted(e.node_id for e in completed) == sorted(FIXTURE_NODES)
        suppressed = ledger.query(
            run_id=run_id, event_type=EventTypes.DUPLICATE_SUPPRESSED
        )
        assert [e.node_id for e in suppressed] == ["plan"]
        assert len(ledger.query(run_id=run_id, event_type=EventTypes.MISSION_RESUMED)) == 1
        assert final_payload(ledger, run_id)["final_output"]["output"] == "hello-world-test"

    def test_crash_after_execute_resume_skips_plan_and_execute(self) -> None:
        events: list[Event] = []
        crash_ledger = CrashingLedger(
            events, crash_on=(EventTypes.NODE_STARTED, "verify")
        )
        bundle = make_bundle()
        spec = compile_spec(crash_ledger, bundle)
        worker = CountingWorker(FixtureWorker())
        with pytest.raises(RuntimeError, match="simulated crash"):
            DeterministicRuntime(crash_ledger, worker).start(spec, bundle)
        assert len(worker.calls) == 1

        ledger = FakeLedger(events)  # healthy ledger over the surviving events
        run_id = ledger.query(event_type=EventTypes.MISSION_STARTED)[0].run_id
        assert run_id is not None
        resumed_worker = CountingWorker(FixtureWorker())
        DeterministicRuntime(ledger, resumed_worker).resume(run_id)

        assert resumed_worker.calls == []  # execute was NOT re-run
        completed = ledger.query(run_id=run_id, event_type=EventTypes.NODE_COMPLETED)
        assert sorted(e.node_id for e in completed) == sorted(FIXTURE_NODES)
        assert len({e.node_id for e in completed}) == len(completed)  # no duplicates
        suppressed = ledger.query(
            run_id=run_id, event_type=EventTypes.DUPLICATE_SUPPRESSED
        )
        assert [e.node_id for e in suppressed] == ["plan", "execute"]
        # Resumed run's final output matches a from-scratch run (determinism).
        fresh_ledger = FakeLedger()
        fresh_run = DeterministicRuntime(fresh_ledger, FixtureWorker()).start(spec, bundle)
        assert (
            final_payload(ledger, run_id)["output_digest"]
            == final_payload(fresh_ledger, fresh_run)["output_digest"]
        )

    def test_resume_of_completed_run_is_idempotent(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle()
        spec = compile_spec(ledger, bundle)
        runtime = DeterministicRuntime(ledger, FixtureWorker())
        run_id = runtime.start(spec, bundle)
        before = len(ledger.events)
        assert runtime.resume(run_id) == run_id
        assert len(ledger.events) == before  # nothing re-emitted

    def test_resume_unknown_run_raises(self) -> None:
        runtime = DeterministicRuntime(FakeLedger(), FixtureWorker())
        with pytest.raises(KeyError):
            runtime.resume("run_missing")
        with pytest.raises(KeyError):
            runtime.status("run_missing")

    def test_cancel_then_resume_raises(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle()
        spec = compile_spec(ledger, bundle)
        with pytest.raises(RuntimeError):
            DeterministicRuntime(ledger, CrashingWorker()).start(spec, bundle)
        run_id = ledger.query(event_type=EventTypes.MISSION_STARTED)[0].run_id
        assert run_id is not None

        runtime = DeterministicRuntime(ledger, FixtureWorker())
        runtime.cancel(run_id)
        cancelled = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_CANCELLED)
        assert len(cancelled) == 1
        assert runtime.status(run_id) == MissionState.CANCELLED.value
        with pytest.raises(RuntimeError, match="cancelled"):
            runtime.resume(run_id)
        runtime.cancel(run_id)  # idempotent
        assert len(ledger.query(run_id=run_id, event_type=EventTypes.MISSION_CANCELLED)) == 1

    def test_cancel_of_completed_run_raises(self) -> None:
        ledger = FakeLedger()
        bundle = make_bundle()
        spec = compile_spec(ledger, bundle)
        runtime = DeterministicRuntime(ledger, FixtureWorker())
        run_id = runtime.start(spec, bundle)
        with pytest.raises(RuntimeError, match="completed"):
            runtime.cancel(run_id)


# -- fixture worker -----------------------------------------------------------


class TestFixtureWorker:
    def test_unknown_strategy_raises(self) -> None:
        worker = FixtureWorker()
        with pytest.raises(ValueError, match="unknown fixture strategy"):
            worker.invoke({"text": "a b"}, {"strategy": "psychic"}, seed=0)

    def test_strategies_match_module_functions(self) -> None:
        worker = FixtureWorker()
        text = "Alpha,  Bravo—charlie!"
        naive = worker.invoke({"text": text}, {"strategy": "naive"}, seed=1)
        robust = worker.invoke({"text": text}, {"strategy": "robust"}, seed=1)
        assert naive == {"output": naive_slugify(text), "strategy": "naive"}
        assert robust == {"output": robust_slugify(text), "strategy": "robust"}

    def test_naive_agrees_on_easy_and_differs_on_hard(self) -> None:
        worker = FixtureWorker()
        sets = generate_task_sets(seed=42)
        for task in [t for t in sets["development"] if t.difficulty == "easy"]:
            naive = worker.invoke({"text": task.input_text}, {"strategy": "naive"}, 0)
            assert naive["output"] == task.expected_output
        for task in [t for t in sets["development"] if t.difficulty == "hard"]:
            naive = worker.invoke({"text": task.input_text}, {"strategy": "naive"}, 0)
            robust = worker.invoke({"text": task.input_text}, {"strategy": "robust"}, 0)
            assert robust["output"] == task.expected_output
            assert naive["output"] != robust["output"]

    def test_robust_slugify_edge_cases(self) -> None:
        assert robust_slugify("Hello,   World!") == "hello-world"
        assert robust_slugify("em—dash–test") == "em-dash-test"
        assert robust_slugify("!!!...???") == ""
        assert robust_slugify("  spaced  out  ") == "spaced-out"
        assert robust_slugify("a --- b") == "a-b"
        assert robust_slugify("ctrl\x00char\x07s") == "ctrlchars"


# -- fixture task corpus ------------------------------------------------------


class TestFixtureTaskCorpus:
    def test_shape_and_difficulties(self) -> None:
        sets = generate_task_sets(seed=7)
        assert set(sets) == {"development", "protected", "retention", "adversarial"}
        dev = sets["development"]
        assert len(dev) == 20
        assert sum(1 for t in dev if t.difficulty == "easy") == 10
        assert sum(1 for t in dev if t.difficulty == "hard") == 10
        assert len(sets["protected"]) == 12
        assert all(t.difficulty == "hard" for t in sets["protected"])
        assert len(sets["retention"]) == 10
        assert all(t.difficulty == "easy" for t in sets["retention"])
        assert len(sets["adversarial"]) == 6
        assert all(t.difficulty == "adversarial" for t in sets["adversarial"])
        all_tasks = [t for tasks in sets.values() for t in tasks]
        assert all(isinstance(t, FixtureTask) and t.family == "slugify" for t in all_tasks)
        task_ids = [t.task_id for t in all_tasks]
        assert len(set(task_ids)) == len(task_ids)

    def test_same_seed_identical_different_seed_different(self) -> None:
        assert generate_task_sets(seed=7) == generate_task_sets(seed=7)
        assert generate_task_sets(seed=7) != generate_task_sets(seed=8)

    def test_development_and_protected_disjoint(self) -> None:
        sets = generate_task_sets(seed=7)
        dev_inputs = {t.input_text for t in sets["development"]}
        protected_inputs = {t.input_text for t in sets["protected"]}
        assert dev_inputs.isdisjoint(protected_inputs)
        assert len(protected_inputs) == 12

    def test_expected_output_always_robust(self) -> None:
        sets = generate_task_sets(seed=13)
        for tasks in sets.values():
            for task in tasks:
                assert task.expected_output == robust_slugify(task.input_text)

    def test_retention_tasks_solved_by_naive(self) -> None:
        for task in generate_task_sets(seed=7)["retention"]:
            assert naive_slugify(task.input_text) == task.expected_output

    def test_hard_tasks_break_naive(self) -> None:
        sets = generate_task_sets(seed=7)
        hard = [t for t in sets["development"] if t.difficulty == "hard"]
        hard += sets["protected"]
        for task in hard:
            assert naive_slugify(task.input_text) != task.expected_output

    def test_adversarial_covers_required_nastiness(self) -> None:
        adversarial = generate_task_sets(seed=7)["adversarial"]
        inputs = [t.input_text for t in adversarial]
        assert any(len(text) > 1000 for text in inputs)  # very long
        assert any(any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text) for text in inputs)
        only_punct = [t for t in adversarial if t.expected_output == ""]
        assert only_punct  # only-punctuation input slugs to empty
        assert any("—" in text for text in inputs)  # unicode em-dash
        assert any(text != text.strip() for text in inputs)  # edge whitespace


# -- end-to-end: corpus through the runtime ------------------------------------


class TestEndToEnd:
    def test_naive_and_robust_bundles_disagree_on_hard_task(self) -> None:
        task = next(
            t for t in generate_task_sets(seed=7)["development"] if t.difficulty == "hard"
        )
        outputs: dict[str, str] = {}
        for strategy in ("naive", "robust"):
            ledger = FakeLedger()
            bundle = make_bundle(strategy)
            spec = compile_spec(ledger, bundle, text=task.input_text, task_id=task.task_id)
            run_id = DeterministicRuntime(ledger, FixtureWorker()).start(spec, bundle)
            outputs[strategy] = final_payload(ledger, run_id)["final_output"]["output"]
        assert outputs["robust"] == task.expected_output
        assert outputs["naive"] != outputs["robust"]
