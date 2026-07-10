"""Coding domain: corpus, worker, executable-test oracle and the full
paired experiment on run-the-checks evidence (report 10.2, 14.2, 14.4, 18.3).

The load-bearing governance cases here are the read-only-tests rule (a
worker that doctors ``checks.py`` is scored against the original) and
fail-closed scoring of malformed or path-escaping candidate output.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    AutonomyLevel,
    BundleDiff,
    ChangeTarget,
    DecisionAction,
    EventTypes,
    ExperimentBudget,
    FieldChange,
    GateId,
    ImprovementProposal,
    ModuleRef,
    SystemBundle,
    TaskSetRefs,
    TaskSetRole,
    canonical_json,
)
from foundry.evaluation import DeterministicTestService, EvaluationHarness
from foundry.experiment import ExperimentController, HoldoutVault
from foundry.policy import ALLOWED_MUTATIONS
from foundry.promotion import PromotionGate
from foundry.workers import (
    CodingTask,
    DeterministicCodingWorker,
    generate_coding_task_sets,
    make_coding_run_arm,
)
from foundry.workers.coding_tasks import CHECKS_FILE, SOLUTION_FILE, UNICODE_CANARY
from test_runtime import FakeLedger

SEED = 11
WORKFLOW_REF = "workflow://coding/v1"


@pytest.fixture(scope="module")
def corpus() -> dict[str, list[CodingTask]]:
    return generate_coding_task_sets(SEED)


@pytest.fixture(scope="module")
def service() -> DeterministicTestService:
    return DeterministicTestService(timeout_seconds=30.0)


def bundle_for(strategy: str, parent: SystemBundle | None = None) -> SystemBundle:
    return SystemBundle(
        workflow_ref=WORKFLOW_REF,
        config={"strategy": strategy},
        parent_bundle_id=parent.bundle_id if parent else None,
    )


def worker_output(task: CodingTask, strategy: str) -> str:
    worker = DeterministicCodingWorker()
    result = worker.invoke(
        {"task_id": task.task_id, "issue": task.issue, "files": dict(task.files)},
        {"strategy": strategy},
        seed=0,
    )
    return canonical_json(result).decode("utf-8")


# -- corpus ---------------------------------------------------------------------


def test_corpus_is_deterministic_and_roles_disjoint(corpus: dict[str, list[CodingTask]]) -> None:
    again = generate_coding_task_sets(SEED)
    assert corpus == again
    other = generate_coding_task_sets(SEED + 1)
    assert corpus != other
    ids_by_role = {role: {t.task_id for t in tasks} for role, tasks in corpus.items()}
    all_ids = [tid for ids in ids_by_role.values() for tid in ids]
    assert len(all_ids) == len(set(all_ids))  # no task appears in two roles


def test_ground_truth_passes_and_buggy_fails_every_task(
    corpus: dict[str, list[CodingTask]], service: DeterministicTestService
) -> None:
    """The corpus is only evidence if the oracle separates fixed from buggy."""
    for tasks in corpus.values():
        for task in tasks:
            fixed = service.run_checks(dict(task.fixed_files), trusted_files=dict(task.files))
            assert fixed.passed, f"{task.task_id}: ground truth must pass its checks"
            buggy = service.run_checks(dict(task.files), trusted_files=dict(task.files))
            assert not buggy.passed, f"{task.task_id}: the buggy repo must fail its checks"


def test_input_text_never_contains_ground_truth(corpus: dict[str, list[CodingTask]]) -> None:
    for task in corpus["protected"]:
        visible = json.loads(task.input_text)
        assert set(visible) == {"issue", "files"}
        assert visible["files"][SOLUTION_FILE] != task.fixed_files[SOLUTION_FILE]


# -- worker strategies ------------------------------------------------------------


def test_naive_fixes_boundary_but_not_comparison(
    corpus: dict[str, list[CodingTask]], service: DeterministicTestService
) -> None:
    boundary = next(t for t in corpus["development"] if t.family == "boundary")
    comparison = next(t for t in corpus["development"] if t.family == "comparison")
    assert service.score(boundary, worker_output(boundary, "naive")) == 1.0
    assert service.score(comparison, worker_output(comparison, "naive")) == 0.0


def test_robust_output_equals_ground_truth(corpus: dict[str, list[CodingTask]]) -> None:
    for tasks in corpus.values():
        for task in tasks:
            result = json.loads(worker_output(task, "robust"))
            assert result["files"] == dict(task.fixed_files), task.task_id


def test_adversarial_repair_preserves_unicode_and_crlf(
    corpus: dict[str, list[CodingTask]], service: DeterministicTestService
) -> None:
    task = corpus["adversarial"][0]
    assert UNICODE_CANARY in task.files[SOLUTION_FILE]
    assert "\r\n" in task.files[SOLUTION_FILE]
    assert service.score(task, worker_output(task, "robust")) == 1.0
    assert service.score(task, worker_output(task, "naive")) == 0.0


def test_unknown_strategy_raises() -> None:
    with pytest.raises(ValueError, match="unknown coding strategy"):
        DeterministicCodingWorker().invoke(
            {"task_id": "x", "issue": "", "files": {}}, {"strategy": "clever"}, seed=0
        )


# -- oracle governance -------------------------------------------------------------


def test_doctored_checks_are_scored_against_the_original(
    corpus: dict[str, list[CodingTask]], service: DeterministicTestService
) -> None:
    """Read-only tests (report 14.2): editing checks.py buys nothing."""
    task = next(t for t in corpus["development"] if t.family == "comparison")
    tampered = {
        SOLUTION_FILE: task.files[SOLUTION_FILE],  # bug left in place
        CHECKS_FILE: 'print("checks passed")\n',  # doctored to always pass
    }
    output = canonical_json({"files": tampered}).decode("utf-8")
    assert service.score(task, output) == 0.0


@pytest.mark.parametrize(
    "output",
    [
        "not json at all",
        json.dumps({"no_files_key": True}),
        json.dumps({"files": {}}),
        json.dumps({"files": {"solution.py": 42}}),
        json.dumps({"files": {"../escape.py": "x = 1\n", "checks.py": "pass\n"}}),
        json.dumps({"files": {"C:/absolute.py": "x = 1\n"}}),
    ],
)
def test_scoring_untrusted_output_is_fail_closed(
    corpus: dict[str, list[CodingTask]], service: DeterministicTestService, output: str
) -> None:
    task = corpus["development"][0]
    assert service.score(task, output) == 0.0


def test_timeout_kills_and_reports(corpus: dict[str, list[CodingTask]]) -> None:
    fast = DeterministicTestService(timeout_seconds=2.0)
    task = corpus["development"][0]
    hanging = dict(task.fixed_files)
    hanging[SOLUTION_FILE] = "while True:\n    pass\n"
    report = fast.run_checks(hanging, trusted_files=dict(task.files))
    assert not report.passed
    assert report.receipt.timed_out
    assert report.receipt.exit_code is None


def test_receipt_digests_command_and_output(
    corpus: dict[str, list[CodingTask]], service: DeterministicTestService
) -> None:
    task = corpus["retention"][0]
    report = service.run_checks(dict(task.fixed_files), trusted_files=dict(task.files))
    assert report.passed
    assert report.receipt.command[-1] == CHECKS_FILE
    assert report.receipt.stdout_digest.startswith("sha256:")
    assert "checks passed" in report.receipt.stdout_tail


# -- the full paired experiment on executable-test evidence ------------------------


def test_paired_coding_experiment_promotes_only_with_approval(
    corpus: dict[str, list[CodingTask]], service: DeterministicTestService
) -> None:
    ledger = FakeLedger()
    vault = HoldoutVault(secret=b"coding-vault-secret-for-tests--1")
    vault_ref = vault.seal("coding-rotation-1", list(corpus["protected"]), scorer=service.score)

    s0 = bundle_for("naive")
    s1 = bundle_for("robust", parent=s0)
    change = FieldChange(field_path="/config/strategy", old_value="naive", new_value="robust")
    proposal = ImprovementProposal(
        parent_bundle_id=s0.bundle_id,
        target=ChangeTarget(field_path="/config/strategy"),
        hypothesis=(
            "Adding the comparison-repair procedure fixes exclusive-threshold "
            "defects without regressing boundary repairs."
        ),
        changes=[change],
        autonomy_level=AutonomyLevel.PROMPT_SKILL_ROUTING,
        experiment_plan_ref="artifact://plan/coding-domain-v1",
        retention_set_ref=f"corpus://coding/{SEED}/retention",
        minimum_practical_effect=0.05,
        retention_floor=0.0,
        rollback_condition="holdout ci_low below effect floor or any retention loss",
        proposer=ModuleRef(id="optimizer.human-designed", version="0.1.0"),
    )

    controller = ExperimentController(ledger, vault=vault)
    record = controller.design(
        proposal,
        control_bundle=s0,
        candidate_bundles=[s1],
        task_set_refs=TaskSetRefs(
            development=f"corpus://coding/{SEED}/development",
            protected=vault_ref,
            retention=f"corpus://coding/{SEED}/retention",
            adversarial=f"corpus://coding/{SEED}/adversarial",
        ),
        budgets=ExperimentBudget(per_arm_cost_usd=1.0, max_runs=100),
        seed=SEED,
        minimum_practical_effect=0.05,
    )

    run_arm = make_coding_run_arm(DeterministicCodingWorker())
    results = controller.run(
        record,
        {"control": s0, "candidate_a": s1},
        {
            TaskSetRole.DEVELOPMENT: list(corpus["development"]),
            TaskSetRole.RETENTION: list(corpus["retention"]),
            TaskSetRole.ADVERSARIAL: list(corpus["adversarial"]),
        },
        run_arm,
        service.score,
    )
    analyses = controller.analyze(record, results, seed=SEED)["candidate_a"]

    # The known answer: robust beats naive on dev and blind holdout,
    # with zero retention loss.
    assert analyses[TaskSetRole.DEVELOPMENT].mean_delta == 0.5
    assert analyses[TaskSetRole.PROTECTED_HOLDOUT].ci_low > 0.05
    assert analyses[TaskSetRole.RETENTION].losses == 0
    assert all(k.startswith("blind://") for k in results["candidate_a"][TaskSetRole.PROTECTED_HOLDOUT])

    metrics = EvaluationHarness().aggregate(results["candidate_a"])
    assert metrics.safety_critical_violations == 0

    gate = PromotionGate()
    diff = BundleDiff(parent_bundle_id=s0.bundle_id, child_bundle_id=s1.bundle_id, changes=[change])
    prefixes = list(ALLOWED_MUTATIONS[AutonomyLevel.PROMPT_SKILL_ROUTING])

    unapproved = gate.run(proposal, s0, s1, diff, analyses, metrics, [], allowed_path_prefixes=prefixes)
    assert unapproved.action is DecisionAction.QUARANTINE  # evidence fine, authority absent

    approval = ApprovalRecord(
        approver="human:owner",
        tier=ApprovalTier.A1_SINGLE_REVIEWER,
        candidate_bundle_id=s1.bundle_id,
    )
    approved = gate.run(
        proposal, s0, s1, diff, analyses, metrics, [approval], allowed_path_prefixes=prefixes
    )
    assert approved.action is DecisionAction.CANARY
    assert approved.rollback_target == s0.bundle_id
    assert {r.gate for r in approved.gate_results} == set(GateId)

    analyzed = ledger.query(event_type=EventTypes.EXPERIMENT_ANALYZED)
    assert len(analyzed) == 1


def test_blind_runner_receives_no_ground_truth(
    corpus: dict[str, list[CodingTask]], service: DeterministicTestService
) -> None:
    vault = HoldoutVault(secret=b"coding-vault-secret-for-tests--2")
    vault.seal("blindness", list(corpus["protected"][:2]), scorer=service.score)
    seen: list[Any] = []

    def spy_runner(view: Any) -> str:
        seen.append(view)
        return worker_output_from_view(view, "robust")

    for handle in vault.handles("blindness"):
        score = vault.run_blind("blindness", handle, spy_runner)
        assert score == 1.0
    for view in seen:
        assert view.task_id.startswith("blind://")  # never the true task id
        assert not hasattr(view, "fixed_files")
        assert "fixed" not in view.input_text  # serialization carries no ground truth


def worker_output_from_view(view: Any, strategy: str) -> str:
    payload = json.loads(view.input_text)
    result = DeterministicCodingWorker().invoke(
        {"task_id": view.task_id, "family": view.family, **payload},
        {"strategy": strategy},
        seed=0,
    )
    return canonical_json(result).decode("utf-8")
