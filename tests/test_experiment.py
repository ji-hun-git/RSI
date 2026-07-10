"""Tests for foundry.experiment: vault blinding, paired analysis, controller.

Covers the invariants of report sections 10.4 (design validation, missing
control, unequal budgets, leakage), 13.4 (pairing, identical order/seeds,
deterministic bootstrap) and 14.1 (holdout contents hidden behind blind
handles). Uses an in-memory fake LedgerLike; no other foundry packages.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import pytest

from foundry.contracts import (
    ChangeTarget,
    Event,
    EventTypes,
    ExperimentBudget,
    ImprovementProposal,
    Integrity,
    LedgerLike,
    SystemBundle,
    TaskSetRefs,
    TaskSetRole,
)
from foundry.experiment import (
    BlindTaskView,
    ExperimentController,
    HoldoutVault,
    bootstrap_ci,
    paired_deltas,
    summarize,
)

SECRET = b"test-vault-secret"
SEED = 1234


@dataclass(frozen=True)
class Task:
    task_id: str
    input_text: str
    difficulty: float = 0.5


class FakeLedger:
    """In-memory LedgerLike: append fills integrity and preserves order."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> Event:
        recorded = event.with_integrity(
            Integrity(
                producer="test-ledger",
                digest=event.payload_digest(),
                prev_digest=None,
                sequence=len(self.events),
            ),
            recorded_at=event.occurred_at,
        )
        self.events.append(recorded)
        return recorded

    def query(
        self,
        *,
        mission_id: str | None = None,
        run_id: str | None = None,
        experiment_id: str | None = None,
        event_type: str | None = None,
    ) -> list[Event]:
        out = self.events
        if mission_id is not None:
            out = [e for e in out if e.mission_id == mission_id]
        if run_id is not None:
            out = [e for e in out if e.run_id == run_id]
        if experiment_id is not None:
            out = [e for e in out if e.experiment_id == experiment_id]
        if event_type is not None:
            out = [e for e in out if e.event_type == event_type]
        return list(out)

    def types(self) -> list[str]:
        return [e.event_type for e in self.events]


def make_control() -> SystemBundle:
    return SystemBundle(workflow_ref="wf://fixture/v1", config={"boost": 0.0})


def make_candidate(control: SystemBundle, boost: float) -> SystemBundle:
    return SystemBundle(
        workflow_ref="wf://fixture/v1",
        parent_bundle_id=control.bundle_id,
        config={"boost": boost},
    )


def make_proposal(control: SystemBundle, hypothesis: str = "Boost improves scores") -> ImprovementProposal:
    return ImprovementProposal(
        parent_bundle_id=control.bundle_id,
        target=ChangeTarget(field_path="/config/boost"),
        hypothesis=hypothesis,
    )


def run_arm(bundle: SystemBundle, task: Any, seed: int) -> str:
    return f"{bundle.config['boost']}|{task.task_id}|{seed}"


def score(task: Any, output: str) -> float:
    boost = float(output.split("|", 1)[0])
    return max(0.0, min(1.0, task.difficulty + boost))


def dev_tasks(n: int = 4) -> list[Task]:
    return [Task(f"dev-{i:02d}", f"development input text {i:02d}") for i in range(n)]


def holdout_tasks(n: int = 6) -> list[Task]:
    return [Task(f"hold-{i:02d}", f"protected secret text {i:02d}", 0.4) for i in range(n)]


def expected_handle(name: str, task_id: str) -> str:
    mac = hmac.new(SECRET, task_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"blind://{name}/{mac[:16]}"


def build(
    boosts: tuple[float, ...] = (0.2,),
    with_holdout: bool = True,
    seed: int = SEED,
) -> dict[str, Any]:
    """Design a standard experiment; returns every piece needed by tests."""
    ledger = FakeLedger()
    vault = HoldoutVault(SECRET)
    control = make_control()
    candidates = [make_candidate(control, b) for b in boosts]
    refs = {"development": "dataset://dev/v1"}
    protected = holdout_tasks()
    if with_holdout:
        refs["protected"] = vault.seal("rotation-1", protected, scorer=score)
    controller = ExperimentController(ledger, vault=vault)
    proposal = make_proposal(control)
    record = controller.design(
        proposal, control, candidates, TaskSetRefs(**refs), ExperimentBudget(), seed=seed
    )
    bundles = {"control": control}
    for arm in record.arms:
        if not arm.is_control:
            bundles[arm.arm_id] = next(c for c in candidates if c.bundle_id == arm.bundle_id)
    return {
        "ledger": ledger,
        "vault": vault,
        "control": control,
        "candidates": candidates,
        "controller": controller,
        "proposal": proposal,
        "record": record,
        "bundles": bundles,
        "dev_tasks": dev_tasks(),
        "holdout_tasks": protected,
    }


class TestDesign:
    def test_always_injects_control_arm_first(self) -> None:
        ctx = build(boosts=(0.2, 0.3))
        arms = ctx["record"].arms
        assert arms[0].arm_id == "control"
        assert arms[0].is_control is True
        assert arms[0].bundle_id == ctx["control"].bundle_id
        assert [a.arm_id for a in arms[1:]] == ["candidate_a", "candidate_b"]
        assert all(not a.is_control for a in arms[1:])
        assert [a.bundle_id for a in arms[1:]] == [c.bundle_id for c in ctx["candidates"]]

    def test_record_carries_seed_and_pairing(self) -> None:
        ctx = build()
        record = ctx["record"]
        assert record.randomization.seed == SEED
        assert record.randomization.paired is True
        assert record.randomization.unit == "task"
        assert record.proposal_id == ctx["proposal"].proposal_id
        assert record.budgets.equalized is True

    def test_rejects_candidate_with_wrong_parent(self) -> None:
        ledger = FakeLedger()
        controller = ExperimentController(ledger)
        control = make_control()
        stranger = SystemBundle(workflow_ref="wf://other/v1")  # parent_bundle_id is None
        with pytest.raises(ValueError, match="lineage"):
            controller.design(
                make_proposal(control),
                control,
                [stranger],
                TaskSetRefs(development="dataset://dev/v1"),
                ExperimentBudget(),
                seed=SEED,
            )

    def test_rejects_proposal_with_wrong_parent(self) -> None:
        ledger = FakeLedger()
        controller = ExperimentController(ledger)
        control = make_control()
        other = SystemBundle(workflow_ref="wf://other/v1")
        with pytest.raises(ValueError, match="proposal parent"):
            controller.design(
                make_proposal(other),
                control,
                [make_candidate(control, 0.2)],
                TaskSetRefs(development="dataset://dev/v1"),
                ExperimentBudget(),
                seed=SEED,
            )

    def test_rejects_unequalized_budgets(self) -> None:
        ledger = FakeLedger()
        controller = ExperimentController(ledger)
        control = make_control()
        with pytest.raises(ValueError, match="equalized"):
            controller.design(
                make_proposal(control),
                control,
                [make_candidate(control, 0.2)],
                TaskSetRefs(development="dataset://dev/v1"),
                ExperimentBudget(equalized=False),
                seed=SEED,
            )

    def test_rejects_empty_candidate_list(self) -> None:
        ledger = FakeLedger()
        controller = ExperimentController(ledger)
        control = make_control()
        with pytest.raises(ValueError, match="candidate"):
            controller.design(
                make_proposal(control),
                control,
                [],
                TaskSetRefs(development="dataset://dev/v1"),
                ExperimentBudget(),
                seed=SEED,
            )

    def test_emits_designed_then_randomized(self) -> None:
        ctx = build()
        types = ctx["ledger"].types()
        assert types == [EventTypes.EXPERIMENT_DESIGNED, EventTypes.EXPERIMENT_RANDOMIZED]
        designed, randomized = ctx["ledger"].events
        assert designed.experiment_id == ctx["record"].experiment_id
        assert randomized.experiment_id == ctx["record"].experiment_id
        assert designed.payload["proposal_id"] == ctx["proposal"].proposal_id
        assert [a["arm_id"] for a in designed.payload["arms"]] == ["control", "candidate_a"]
        assert randomized.payload["seed"] == SEED
        assert randomized.payload["paired"] is True


class TestRun:
    def test_identical_task_order_and_seeds_across_arms(self) -> None:
        ctx = build()
        calls: dict[str, list[tuple[str, int]]] = {}

        def spy_run_arm(bundle: SystemBundle, task: Any, seed: int) -> str:
            calls.setdefault(bundle.bundle_id, []).append((task.task_id, seed))
            return run_arm(bundle, task, seed)

        ctx["controller"].run(
            ctx["record"],
            ctx["bundles"],
            {TaskSetRole.DEVELOPMENT: ctx["dev_tasks"]},
            spy_run_arm,
            score,
        )
        sequences = list(calls.values())
        assert len(sequences) == 2  # control + candidate_a
        assert sequences[0] == sequences[1]
        # 4 dev + 6 protected tasks per arm, every task with a distinct seed
        assert len(sequences[0]) == 10
        seeds = [s for _, s in sequences[0]]
        assert len(set(seeds)) == len(seeds)

    def test_rejects_protected_tasks_passed_in_the_clear(self) -> None:
        ctx = build()
        with pytest.raises(ValueError, match="vault"):
            ctx["controller"].run(
                ctx["record"],
                ctx["bundles"],
                {TaskSetRole.PROTECTED_HOLDOUT: ctx["holdout_tasks"]},
                run_arm,
                score,
            )

    def test_rejects_bundle_arm_mismatch(self) -> None:
        ctx = build()
        swapped = {
            "control": ctx["bundles"]["candidate_a"],
            "candidate_a": ctx["bundles"]["control"],
        }
        with pytest.raises(ValueError, match="does not match"):
            ctx["controller"].run(
                ctx["record"],
                swapped,
                {TaskSetRole.DEVELOPMENT: ctx["dev_tasks"]},
                run_arm,
                score,
            )

    def test_protected_results_keyed_by_blind_handles(self) -> None:
        ctx = build()
        results = ctx["controller"].run(
            ctx["record"],
            ctx["bundles"],
            {TaskSetRole.DEVELOPMENT: ctx["dev_tasks"]},
            run_arm,
            score,
        )
        raw_ids = {t.task_id for t in ctx["holdout_tasks"]}
        for arm_id in ("control", "candidate_a"):
            protected_scores = results[arm_id][TaskSetRole.PROTECTED_HOLDOUT]
            assert len(protected_scores) == len(raw_ids)
            for handle in protected_scores:
                assert handle.startswith("blind://rotation-1/")
                suffix = handle.rsplit("/", 1)[1]
                assert len(suffix) == 16
                assert not any(raw in handle for raw in raw_ids)
            # development results stay keyed by task id
            assert set(results[arm_id][TaskSetRole.DEVELOPMENT]) == {
                t.task_id for t in ctx["dev_tasks"]
            }

    def test_run_is_deterministic(self) -> None:
        results = []
        for _ in range(2):
            ctx = build()
            results.append(
                ctx["controller"].run(
                    ctx["record"],
                    ctx["bundles"],
                    {TaskSetRole.DEVELOPMENT: dev_tasks()},
                    run_arm,
                    score,
                )
            )
        assert results[0] == results[1]

    def test_run_event_order_and_metric_payloads(self) -> None:
        ctx = build()
        ledger: FakeLedger = ctx["ledger"]
        before = len(ledger.events)
        ctx["controller"].run(
            ctx["record"],
            ctx["bundles"],
            {TaskSetRole.DEVELOPMENT: ctx["dev_tasks"]},
            run_arm,
            score,
        )
        run_events = ledger.events[before:]
        assert [e.event_type for e in run_events] == [
            EventTypes.ARM_STARTED,
            EventTypes.METRIC_COMPUTED,  # development
            EventTypes.METRIC_COMPUTED,  # protected
            EventTypes.ARM_COMPLETED,
            EventTypes.ARM_STARTED,
            EventTypes.METRIC_COMPUTED,
            EventTypes.METRIC_COMPUTED,
            EventTypes.ARM_COMPLETED,
        ]
        assert [e.arm_id for e in run_events] == ["control"] * 4 + ["candidate_a"] * 4
        control_dev_metric = run_events[1]
        assert control_dev_metric.payload["role"] == TaskSetRole.DEVELOPMENT.value
        assert control_dev_metric.payload["value"] == pytest.approx(0.5)
        candidate_dev_metric = run_events[5]
        assert candidate_dev_metric.payload["value"] == pytest.approx(0.7)
        completed = run_events[3]
        assert completed.payload["runs"] == 10
        assert completed.payload["tasks_per_role"] == {"development": 4, "protected": 6}


class TestVault:
    def test_no_public_accessor_returns_tasks(self) -> None:
        vault = HoldoutVault(SECRET)
        vault.seal("rotation-1", holdout_tasks(), scorer=score)
        public = sorted(name for name in dir(vault) if not name.startswith("_"))
        assert public == ["handles", "leakage_check", "run_blind", "seal"]
        assert not hasattr(vault, "get_task")
        assert not hasattr(vault, "tasks")
        # internal storage is underscore-private
        assert "_sets" in vars(vault) and "_secret" in vars(vault)

    def test_handles_deterministic_blind_and_shuffled(self) -> None:
        tasks = holdout_tasks()
        vault_a = HoldoutVault(SECRET)
        vault_a.seal("rotation-1", tasks, scorer=score)
        vault_b = HoldoutVault(SECRET)
        vault_b.seal("rotation-1", tasks, scorer=score)
        handles = vault_a.handles("rotation-1")
        assert handles == vault_a.handles("rotation-1")  # stable across calls
        assert handles == vault_b.handles("rotation-1")  # stable across instances
        insertion_order = [expected_handle("rotation-1", t.task_id) for t in tasks]
        assert sorted(insertion_order) == handles
        assert insertion_order != handles  # keyed shuffle permutes insertion order
        for task, handle in zip(tasks, insertion_order, strict=True):
            assert task.task_id not in handle
            assert task.input_text not in handle
        # a different secret yields different handles
        other = HoldoutVault(b"other-secret")
        other.seal("rotation-1", tasks, scorer=score)
        assert set(other.handles("rotation-1")).isdisjoint(handles)

    def test_seal_returns_vault_ref_and_is_immutable(self) -> None:
        vault = HoldoutVault(SECRET)
        assert vault.seal("rotation-1", holdout_tasks(), scorer=score) == "blind://vault/rotation-1"
        with pytest.raises(ValueError, match="already sealed"):
            vault.seal("rotation-1", holdout_tasks(), scorer=score)
        with pytest.raises(ValueError, match="duplicate"):
            vault.seal("rotation-2", [Task("t", "x"), Task("t", "y")], scorer=score)
        with pytest.raises(ValueError, match="invalid"):
            vault.seal("bad/name", holdout_tasks(), scorer=score)

    def test_run_blind_passes_only_a_redacted_view(self) -> None:
        """The candidate callback never sees the task: only a BlindTaskView."""
        tasks = holdout_tasks()
        vault = HoldoutVault(SECRET)
        vault.seal("rotation-1", tasks, scorer=score)
        captured: list[BlindTaskView] = []

        def candidate(view: BlindTaskView) -> str:
            captured.append(view)
            return "0.0|whatever|1"

        result = vault.run_blind("rotation-1", vault.handles("rotation-1")[0], candidate)
        assert isinstance(result, float)  # only the score leaves the vault
        (view,) = captured
        assert isinstance(view, BlindTaskView)
        assert view.task_id.startswith("blind://rotation-1/")  # blind handle, not a task id
        assert view.task_id not in {t.task_id for t in tasks}
        assert not hasattr(view, "expected_output")
        assert not hasattr(view, "difficulty")

    def test_run_blind_cannot_exfiltrate_task_ids_via_the_callback(self) -> None:
        """The pre-fix exploit: an identity-style callback saw the real task."""
        tasks = holdout_tasks()
        vault = HoldoutVault(SECRET)
        vault.seal("rotation-1", tasks, scorer=score)
        seen: list[str] = []
        for handle in vault.handles("rotation-1"):
            vault.run_blind("rotation-1", handle, lambda view: seen.append(view.task_id) or "0.0|x|1")
        real_ids = {t.task_id for t in tasks}
        assert real_ids.isdisjoint(seen)

    def test_run_blind_scores_internally_against_hidden_ground_truth(self) -> None:
        """The sealed scorer sees the TRUE task (hidden fields included)."""
        tasks = holdout_tasks()  # difficulty 0.4, hidden from the candidate
        vault = HoldoutVault(SECRET)
        vault.seal("rotation-1", tasks, scorer=score)
        value = vault.run_blind(
            "rotation-1", vault.handles("rotation-1")[0], lambda view: "0.25|x|1"
        )
        assert value == pytest.approx(0.4 + 0.25)

    def test_candidate_cannot_echo_the_expected_output(self) -> None:
        """A candidate returning task.expected_output can no longer score 1.0."""

        @dataclass(frozen=True)
        class AnswerTask:
            task_id: str
            input_text: str
            expected_output: str

        tasks = [AnswerTask(f"t-{i}", f"question {i}", f"secret answer {i}") for i in range(3)]
        vault = HoldoutVault(SECRET)
        vault.seal(
            "answers",
            tasks,  # type: ignore[arg-type]
            scorer=lambda task, output: 1.0 if output == task.expected_output else 0.0,
        )

        def cheating_candidate(view: BlindTaskView) -> str:
            return getattr(view, "expected_output", "no ground truth available")

        for handle in vault.handles("answers"):
            assert vault.run_blind("answers", handle, cheating_candidate) == 0.0

    def test_leakage_check_finds_planted_and_misses_clean(self) -> None:
        tasks = holdout_tasks()
        vault = HoldoutVault(SECRET)
        vault.seal("rotation-1", tasks, scorer=score)
        planted = f"evidence quoting: {tasks[2].input_text} verbatim"
        hits = vault.leakage_check("rotation-1", ["clean text", planted])
        assert hits == [expected_handle("rotation-1", tasks[2].task_id)]
        assert vault.leakage_check("rotation-1", ["nothing protected here"]) == []


class TestAnalysis:
    def test_paired_deltas_is_b_minus_a(self) -> None:
        deltas = paired_deltas({"t1": 0.5, "t2": 0.8}, {"t1": 0.7, "t2": 0.6})
        assert deltas == {"t1": pytest.approx(0.2), "t2": pytest.approx(-0.2)}

    def test_paired_deltas_rejects_mismatched_task_sets(self) -> None:
        with pytest.raises(ValueError, match="identical task sets"):
            paired_deltas({"t1": 0.5}, {"t1": 0.5, "t2": 0.6})
        with pytest.raises(ValueError, match="identical task sets"):
            paired_deltas({"t1": 0.5, "t3": 0.1}, {"t1": 0.5, "t2": 0.6})

    def test_bootstrap_ci_deterministic_in_seed(self) -> None:
        deltas = [0.1, -0.05, 0.2, 0.0, 0.15, -0.1, 0.05, 0.3]
        assert bootstrap_ci(deltas, seed=7) == bootstrap_ci(deltas, seed=7)
        assert bootstrap_ci(deltas, seed=7) != bootstrap_ci(deltas, seed=8)

    def test_bootstrap_ci_positive_for_all_positive_deltas(self) -> None:
        deltas = [0.05 + 0.01 * i for i in range(20)]
        low, high = bootstrap_ci(deltas, seed=42)
        assert low > 0.0
        assert low <= high

    def test_bootstrap_ci_brackets_the_mean(self) -> None:
        deltas = [0.1, -0.05, 0.2, 0.0, 0.15, -0.1, 0.05, 0.3]
        low, high = bootstrap_ci(deltas, seed=3)
        mean = sum(deltas) / len(deltas)
        assert low <= mean <= high

    def test_bootstrap_ci_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            bootstrap_ci([], seed=1)

    def test_summarize_wins_losses_ties(self) -> None:
        control = {"t1": 0.5, "t2": 0.5, "t3": 0.5, "t4": 0.2}
        candidate = {"t1": 0.7, "t2": 0.3, "t3": 0.5, "t4": 0.9}
        analysis = summarize("exp_x", "candidate_a", TaskSetRole.DEVELOPMENT, control, candidate, seed=5)
        assert analysis.n_pairs == 4
        assert analysis.wins == 2
        assert analysis.losses == 1
        assert analysis.ties == 1
        assert analysis.mean_delta == pytest.approx((0.2 - 0.2 + 0.0 + 0.7) / 4)
        assert analysis.per_task_deltas == {
            "t1": pytest.approx(0.2),
            "t2": pytest.approx(-0.2),
            "t3": pytest.approx(0.0),
            "t4": pytest.approx(0.7),
        }
        assert analysis.experiment_id == "exp_x"
        assert analysis.arm_id == "candidate_a"
        assert analysis.task_set_role is TaskSetRole.DEVELOPMENT

    def test_summarize_deterministic(self) -> None:
        control = {"t1": 0.5, "t2": 0.4, "t3": 0.9}
        candidate = {"t1": 0.6, "t2": 0.7, "t3": 0.8}
        first = summarize("exp_x", "candidate_a", TaskSetRole.RETENTION, control, candidate, seed=11)
        second = summarize("exp_x", "candidate_a", TaskSetRole.RETENTION, control, candidate, seed=11)
        assert first == second

    def test_bootstrap_ci_is_order_canonical(self) -> None:
        """The CI is a function of the delta VALUES and seed, never their order."""
        deltas = [0.1, -0.05, 0.2, 0.0, 0.15, -0.1, 0.05, 0.3]
        for permutation_seed in range(5):
            shuffled = list(deltas)
            import random as _random

            _random.Random(permutation_seed).shuffle(shuffled)
            assert bootstrap_ci(shuffled, seed=7) == bootstrap_ci(deltas, seed=7)

    def test_summarize_statistics_independent_of_key_naming(self) -> None:
        """Renaming score keys (e.g. re-keyed blind handles under a different
        vault secret) must not change any recorded statistic (report 22.2)."""
        control = {"t1": 0.5, "t2": 0.4, "t3": 0.9, "t4": 0.1}
        candidate = {"t1": 0.6, "t2": 0.7, "t3": 0.8, "t4": 0.35}
        renames = {"t1": "blind://x/aaaa", "t2": "blind://x/zzzz", "t3": "blind://x/mmmm", "t4": "blind://x/bbbb"}
        renamed_control = {renames[k]: v for k, v in control.items()}
        renamed_candidate = {renames[k]: v for k, v in candidate.items()}
        original = summarize("exp_x", "candidate_a", TaskSetRole.RETENTION, control, candidate, seed=11)
        renamed = summarize(
            "exp_x", "candidate_a", TaskSetRole.RETENTION, renamed_control, renamed_candidate, seed=11
        )
        assert renamed.mean_delta == original.mean_delta
        assert (renamed.ci_low, renamed.ci_high) == (original.ci_low, original.ci_high)
        assert (renamed.wins, renamed.losses, renamed.ties) == (
            original.wins,
            original.losses,
            original.ties,
        )
        assert sorted(renamed.per_task_deltas.values()) == sorted(original.per_task_deltas.values())


class TestAnalyzeAndLeakage:
    def run_full(self, ctx: dict[str, Any]) -> dict[str, Any]:
        results = ctx["controller"].run(
            ctx["record"],
            ctx["bundles"],
            {TaskSetRole.DEVELOPMENT: ctx["dev_tasks"]},
            run_arm,
            score,
        )
        analyses = ctx["controller"].analyze(ctx["record"], results, seed=99)
        return {"results": results, "analyses": analyses}

    def test_analyze_compares_candidates_to_control(self) -> None:
        ctx = build(boosts=(0.2, 0.3))
        out = self.run_full(ctx)
        analyses = out["analyses"]
        assert sorted(analyses) == ["candidate_a", "candidate_b"]  # control excluded
        dev_a = analyses["candidate_a"][TaskSetRole.DEVELOPMENT]
        assert dev_a.n_pairs == 4
        assert dev_a.mean_delta == pytest.approx(0.2)
        assert dev_a.wins == 4 and dev_a.losses == 0 and dev_a.ties == 0
        assert dev_a.ci_low == pytest.approx(0.2) and dev_a.ci_high == pytest.approx(0.2)
        dev_b = analyses["candidate_b"][TaskSetRole.DEVELOPMENT]
        assert dev_b.mean_delta == pytest.approx(0.3)
        protected_a = analyses["candidate_a"][TaskSetRole.PROTECTED_HOLDOUT]
        assert protected_a.n_pairs == 6
        assert all(key.startswith("blind://rotation-1/") for key in protected_a.per_task_deltas)

    def test_analyze_is_deterministic(self) -> None:
        first = self.run_full(build())
        second = self.run_full(build())
        assert first["results"] == second["results"]
        # identical statistical content; only the opaque experiment_id differs
        for arm_id, per_role in first["analyses"].items():
            for role, analysis in per_role.items():
                other = second["analyses"][arm_id][role]
                assert analysis.model_dump(exclude={"experiment_id"}) == other.model_dump(
                    exclude={"experiment_id"}
                )

    def test_analyze_emits_summary_event(self) -> None:
        ctx = build()
        self.run_full(ctx)
        analyzed = ctx["ledger"].query(event_type=EventTypes.EXPERIMENT_ANALYZED)
        assert len(analyzed) == 1
        payload = analyzed[0].payload
        assert payload["seed"] == 99
        summary = payload["arms"]["candidate_a"][TaskSetRole.DEVELOPMENT.value]
        assert summary["n_pairs"] == 4
        assert summary["mean_delta"] == pytest.approx(0.2)
        assert summary["wins"] == 4

    def test_check_leakage_detects_planted_text_and_emits_event(self) -> None:
        ctx = build()
        leaked_task = ctx["holdout_tasks"][1]
        dirty = ImprovementProposal(
            parent_bundle_id=ctx["control"].bundle_id,
            target=ChangeTarget(field_path="/config/boost"),
            hypothesis=f"Improve outputs like {leaked_task.input_text} by boosting",
        )
        hits = ctx["controller"].check_leakage(ctx["record"], dirty)
        assert hits == [expected_handle("rotation-1", leaked_task.task_id)]
        leak_events = ctx["ledger"].query(event_type=EventTypes.LEAKAGE_DETECTED)
        assert len(leak_events) == 1
        assert leak_events[0].payload["handles"] == hits
        assert leak_events[0].payload["proposal_id"] == dirty.proposal_id

    def test_check_leakage_clean_proposal_emits_nothing(self) -> None:
        ctx = build()
        hits = ctx["controller"].check_leakage(ctx["record"], ctx["proposal"])
        assert hits == []
        assert ctx["ledger"].query(event_type=EventTypes.LEAKAGE_DETECTED) == []

    def test_check_leakage_without_protected_set_is_noop(self) -> None:
        ctx = build(with_holdout=False)
        assert ctx["controller"].check_leakage(ctx["record"], ctx["proposal"]) == []


class TestFullFlowEvents:
    def test_ledger_records_expected_event_sequence(self) -> None:
        ctx = build()
        assert isinstance(ctx["ledger"], LedgerLike)
        results = ctx["controller"].run(
            ctx["record"],
            ctx["bundles"],
            {TaskSetRole.DEVELOPMENT: ctx["dev_tasks"]},
            run_arm,
            score,
        )
        ctx["controller"].analyze(ctx["record"], results, seed=99)
        assert ctx["ledger"].types() == [
            EventTypes.EXPERIMENT_DESIGNED,
            EventTypes.EXPERIMENT_RANDOMIZED,
            EventTypes.ARM_STARTED,
            EventTypes.METRIC_COMPUTED,
            EventTypes.METRIC_COMPUTED,
            EventTypes.ARM_COMPLETED,
            EventTypes.ARM_STARTED,
            EventTypes.METRIC_COMPUTED,
            EventTypes.METRIC_COMPUTED,
            EventTypes.ARM_COMPLETED,
            EventTypes.EXPERIMENT_ANALYZED,
        ]
        experiment_ids = {e.experiment_id for e in ctx["ledger"].events}
        assert experiment_ids == {ctx["record"].experiment_id}
