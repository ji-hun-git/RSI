"""Tests for the deterministic oracle, evaluation harness and G0-G9 promotion gate.

Covers the invariants of report sections 13.1-13.4, Appendix B and the
no-self-approval rule of section 8.1.
"""

from __future__ import annotations

import pytest

from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    AutonomyLevel,
    BundleDiff,
    ChangeTarget,
    DecisionAction,
    FieldChange,
    GateId,
    ImprovementProposal,
    MetricVector,
    ModuleRef,
    PairedAnalysis,
    SystemBundle,
    TaskSetRole,
)
from foundry.evaluation import DeterministicOracle, EvaluationHarness, exact_match
from foundry.promotion import (
    PromotionGate,
    g0_integrity,
    g1_static,
    g2_dev_replay,
    g3_holdout,
    g4_retention,
    g5_adversarial,
    g6_resource,
    g7_reproducibility,
    g8_human,
    g9_canary,
    required_approval_tier,
    tier_meets,
    verify_decision_signature,
)
from foundry.registry import HMACSigner

PROPOSER = ModuleRef(id="agent.improver", version="0.1.0")
CHANGE = FieldChange(field_path="/config/strategy", old_value="baseline", new_value="improved")
ALLOWED = ["/config"]
GATE_ORDER = [
    GateId.G0_INTEGRITY_AND_SCOPE,
    GateId.G1_STATIC_CHECKS,
    GateId.G2_DEVELOPMENT_REPLAY,
    GateId.G3_PROTECTED_HOLDOUT,
    GateId.G4_CAPABILITY_RETENTION,
    GateId.G5_ADVERSARIAL_SAFETY,
    GateId.G6_RESOURCE_MAINTAINABILITY,
    GateId.G7_REPRODUCIBILITY,
    GateId.G8_HUMAN_AUTHORIZATION,
    GateId.G9_CANARY_MONITORING,
]


def make_parent() -> SystemBundle:
    return SystemBundle(workflow_ref="wf://fixture/v1", config={"strategy": "baseline"})


def make_candidate(parent: SystemBundle) -> SystemBundle:
    return SystemBundle(
        workflow_ref="wf://fixture/v1",
        parent_bundle_id=parent.bundle_id,
        config={"strategy": "improved"},
    )


def make_diff(
    parent: SystemBundle, candidate: SystemBundle, changes: list[FieldChange] | None = None
) -> BundleDiff:
    return BundleDiff(
        parent_bundle_id=parent.bundle_id,
        child_bundle_id=candidate.bundle_id,
        changes=[CHANGE] if changes is None else changes,
    )


def make_proposal(parent: SystemBundle, **overrides) -> ImprovementProposal:
    kwargs = dict(
        parent_bundle_id=parent.bundle_id,
        target=ChangeTarget(field_path="/config/strategy"),
        hypothesis="switching strategy improves task success",
        changes=[CHANGE],
        autonomy_level=AutonomyLevel.PROMPT_SKILL_ROUTING,
        experiment_plan_ref="artifact://sha256:" + "b" * 64,
        retention_set_ref="corpus://fixture/retention",
        minimum_practical_effect=0.0,
        retention_floor=0.0,
        rollback_condition="task_success drops below parent mean",
        proposer=PROPOSER,
    )
    kwargs.update(overrides)
    return ImprovementProposal(**kwargs)


def analysis(
    role: TaskSetRole,
    *,
    mean_delta: float = 0.2,
    ci_low: float = 0.05,
    ci_high: float = 0.35,
    wins: int = 6,
    losses: int = 0,
    ties: int = 4,
    n_pairs: int = 10,
) -> PairedAnalysis:
    return PairedAnalysis(
        experiment_id="exp_fixture",
        arm_id="candidate_a",
        task_set_role=role,
        n_pairs=n_pairs,
        mean_delta=mean_delta,
        ci_low=ci_low,
        ci_high=ci_high,
        wins=wins,
        losses=losses,
        ties=ties,
    )


def good_analyses() -> dict[TaskSetRole, PairedAnalysis]:
    return {
        TaskSetRole.DEVELOPMENT: analysis(TaskSetRole.DEVELOPMENT),
        TaskSetRole.PROTECTED_HOLDOUT: analysis(
            TaskSetRole.PROTECTED_HOLDOUT, mean_delta=0.15, ci_low=0.02, ci_high=0.28
        ),
        TaskSetRole.RETENTION: analysis(
            TaskSetRole.RETENTION, mean_delta=0.01, ci_low=0.0, ci_high=0.02, wins=1, ties=9
        ),
    }


def approval_for(
    candidate: SystemBundle,
    *,
    approver: str = "human:owner",
    tier: ApprovalTier = ApprovalTier.A1_SINGLE_REVIEWER,
    decision: str = "approved",
    bundle_id: str | None = None,
) -> ApprovalRecord:
    return ApprovalRecord(
        approver=approver,
        tier=tier,
        candidate_bundle_id=candidate.bundle_id if bundle_id is None else bundle_id,
        decision=decision,
    )


def tampered_copy(candidate: SystemBundle) -> SystemBundle:
    """A bundle whose bundle_id no longer matches its content (bypasses validation)."""
    payload = candidate.model_dump(exclude={"bundle_id"})
    return SystemBundle.model_construct(bundle_id="sha256:" + "0" * 64, **payload)


def full_run(**overrides):
    """Run the whole gate with a green fixture, overriding selected inputs."""
    parent = overrides.pop("parent", make_parent())
    candidate = overrides.pop("candidate", make_candidate(parent))
    proposal = overrides.pop("proposal", make_proposal(parent))
    diff = overrides.pop("diff", make_diff(parent, candidate))
    analyses = overrides.pop("analyses", good_analyses())
    metrics = overrides.pop("metrics", MetricVector(task_success=0.9))
    approvals = overrides.pop("approvals", [approval_for(candidate)])
    signer = overrides.pop("signer", None)
    decision = PromotionGate(signer=signer).run(
        proposal,
        parent,
        candidate,
        diff,
        analyses,
        metrics,
        approvals,
        allowed_path_prefixes=ALLOWED,
        **overrides,
    )
    return decision, parent, candidate


class TestOracle:
    def test_exact_match_scores_one(self) -> None:
        result = DeterministicOracle().score("task-1", "42", "42", subject_run_id="run_1")
        assert result.value == 1.0
        assert result.metric == "task_success"

    def test_mismatch_scores_zero(self) -> None:
        result = DeterministicOracle().score("task-1", "42", "43", subject_run_id="run_1")
        assert result.value == 0.0

    def test_result_carries_identity_and_handles(self) -> None:
        result = DeterministicOracle().score(
            "task-7",
            "a",
            "a",
            subject_run_id="run_9",
            bundle_id="sha256:" + "a" * 64,
            dataset_item_handle="blind-07",
        )
        assert result.evaluator.id == "eval.exact_match"
        assert result.evaluator.version == "1.0.0"
        assert result.subject_run_id == "run_9"
        assert result.subject_bundle_id == "sha256:" + "a" * 64
        assert result.dataset_item_handle == "blind-07"
        assert result.detail["task_id"] == "task-7"

    def test_exact_match_helper(self) -> None:
        assert exact_match("x", "x") == 1.0
        assert exact_match("x", "y") == 0.0
        assert exact_match("x", "x ") == 0.0  # whitespace matters: exact means exact

    def test_result_carries_integrity_digest(self) -> None:
        """17.4: every evaluation result carries an integrity block."""
        result = DeterministicOracle().score("task-1", "42", "42", subject_run_id="run_1")
        assert result.integrity is not None
        assert result.integrity.digest == result.digest()
        assert result.integrity.signature is None  # unsigned oracle: digest only
        # Tampering with a recorded field is detectable via the stored digest.
        tampered = result.model_copy(update={"value": 0.0})
        assert tampered.digest() != tampered.integrity.digest

    def test_signed_oracle_fills_signature(self) -> None:
        signer = HMACSigner("oracle-key", b"oracle-secret")
        result = DeterministicOracle(signer=signer).score(
            "task-1", "42", "42", subject_run_id="run_1"
        )
        assert result.integrity is not None
        assert result.integrity.signer == "oracle-key"
        assert signer.verify(
            result.integrity.digest.encode("utf-8"), result.integrity.signature
        )


class TestHarness:
    def test_role_mapping(self) -> None:
        metrics = EvaluationHarness().aggregate(
            {
                TaskSetRole.DEVELOPMENT: {"t1": 1.0, "t2": 0.0},
                TaskSetRole.RETENTION: {"r1": 1.0, "r2": 1.0},
                TaskSetRole.PROTECTED_HOLDOUT: {"p1": 1.0},
                TaskSetRole.ADVERSARIAL: {"a1": 1.0, "a2": 1.0},
            }
        )
        assert metrics.task_success == 0.5
        assert metrics.capability_retention == 1.0
        assert metrics.generalization == 1.0
        assert metrics.safety_critical_violations == 0

    def test_adversarial_violations_counted_below_one(self) -> None:
        metrics = EvaluationHarness().aggregate(
            {TaskSetRole.ADVERSARIAL: {"a1": 1.0, "a2": 0.0, "a3": 0.5}}
        )
        assert metrics.safety_critical_violations == 2

    def test_empty_role_yields_none_not_zero(self) -> None:
        metrics = EvaluationHarness().aggregate({TaskSetRole.DEVELOPMENT: {}})
        assert metrics.task_success is None
        assert metrics.capability_retention is None
        assert metrics.generalization is None
        assert metrics.safety_critical_violations == 0
        assert metrics.subgroup_minima == {}

    def test_missing_roles_yield_none(self) -> None:
        metrics = EvaluationHarness().aggregate({TaskSetRole.DEVELOPMENT: {"t1": 0.0}})
        assert metrics.task_success == 0.0  # measured at zero is NOT None
        assert metrics.capability_retention is None  # not measured IS None
        assert metrics.generalization is None

    def test_subgroup_minima_per_role(self) -> None:
        metrics = EvaluationHarness().aggregate(
            {
                TaskSetRole.DEVELOPMENT: {"t1": 1.0, "t2": 0.25},
                TaskSetRole.RETENTION: {"r1": 0.75},
            }
        )
        assert metrics.subgroup_minima == {"development": 0.25, "retention": 0.75}

    def test_passthrough_fields(self) -> None:
        metrics = EvaluationHarness().aggregate(
            {}, cost_usd=1.5, latency_p95_ms=200.0, reproducibility=0.9
        )
        assert metrics.cost_usd == 1.5
        assert metrics.latency_p95_ms == 200.0
        assert metrics.reproducibility == 0.9


class TestRequiredApprovalTier:
    @pytest.mark.parametrize(
        ("level", "tier"),
        [
            (0, ApprovalTier.A0_AUTOMATIC),
            (1, ApprovalTier.A0_AUTOMATIC),
            (2, ApprovalTier.A1_SINGLE_REVIEWER),
            (3, ApprovalTier.A2_DUAL_CONTROL),
            (4, ApprovalTier.A3_GOVERNANCE_COMMITTEE),
            (5, ApprovalTier.A4_CONVENTIONAL_SDLC),  # report 14.5: never A3
        ],
    )
    def test_report_14_5_mapping(self, level: int, tier: ApprovalTier) -> None:
        assert required_approval_tier(level) is tier
        assert required_approval_tier(AutonomyLevel(level)) is tier

    def test_tier_ordering(self) -> None:
        assert tier_meets(ApprovalTier.A1_SINGLE_REVIEWER, ApprovalTier.A1_SINGLE_REVIEWER)
        assert tier_meets(ApprovalTier.A4_CONVENTIONAL_SDLC, ApprovalTier.A0_AUTOMATIC)
        assert not tier_meets(ApprovalTier.A0_AUTOMATIC, ApprovalTier.A1_SINGLE_REVIEWER)
        assert not tier_meets(ApprovalTier.A2_DUAL_CONTROL, ApprovalTier.A3_GOVERNANCE_COMMITTEE)


class TestG0Integrity:
    def test_green_fixture_passes(self) -> None:
        parent = make_parent()
        candidate = make_candidate(parent)
        result = g0_integrity(
            make_proposal(parent), parent, candidate, make_diff(parent, candidate), ALLOWED
        )
        assert result.passed
        assert result.gate is GateId.G0_INTEGRITY_AND_SCOPE

    def test_wrong_parent_fails(self) -> None:
        parent = make_parent()
        orphan = SystemBundle(
            workflow_ref="wf://fixture/v1",
            parent_bundle_id="sha256:" + "c" * 64,
            config={"strategy": "improved"},
        )
        result = g0_integrity(make_proposal(parent), parent, orphan, make_diff(parent, orphan), ALLOWED)
        assert not result.passed
        assert "parent_bundle_id" in result.reason

    def test_tampered_bundle_id_fails(self) -> None:
        parent = make_parent()
        tampered = tampered_copy(make_candidate(parent))
        result = g0_integrity(
            make_proposal(parent), parent, tampered, make_diff(parent, tampered), ALLOWED
        )
        assert not result.passed
        assert "content digest" in result.reason

    def test_disallowed_path_fails(self) -> None:
        parent = make_parent()
        candidate = make_candidate(parent)
        result = g0_integrity(
            make_proposal(parent), parent, candidate, make_diff(parent, candidate), ["/module_refs"]
        )
        assert not result.passed
        assert "allowed mutation surface" in result.reason

    def test_undeclared_diff_path_fails(self) -> None:
        parent = make_parent()
        candidate = make_candidate(parent)
        sneaky = FieldChange(field_path="/config/other", old_value=None, new_value="x")
        diff = make_diff(parent, candidate, changes=[CHANGE, sneaky])
        result = g0_integrity(make_proposal(parent), parent, candidate, diff, ALLOWED)
        assert not result.passed
        assert "undeclared" in result.reason

    def test_prefix_match_respects_segment_boundaries(self) -> None:
        """G0 uses the same segment-aware rule as fork() and the PDP: a
        declared sibling path like /config/strategy_evil must NOT pass
        under the allowed prefix /config/strategy."""
        parent = make_parent()
        candidate = make_candidate(parent)
        stage1_surface = [
            "/config/retrieval",
            "/memory_policy_ref",
            "/config/prompt",
            "/config/strategy",
            "/config/routing",
            "/module_refs",
        ]
        for sneaky_path in ("/config/strategy_evil", "/config/promptX", "/config/routing2"):
            sneaky = FieldChange(field_path=sneaky_path, old_value=None, new_value="x")
            proposal = make_proposal(parent, changes=[sneaky])
            diff = make_diff(parent, candidate, changes=[sneaky])
            result = g0_integrity(proposal, parent, candidate, diff, stage1_surface)
            assert not result.passed
            assert "outside the allowed mutation surface" in result.reason
        # The exact segment (and true children) still pass the scope check.
        result = g0_integrity(
            make_proposal(parent), parent, candidate, make_diff(parent, candidate), stage1_surface
        )
        assert result.passed

    @pytest.mark.parametrize(
        "override",
        [
            {"hypothesis": "   "},
            {"rollback_condition": ""},
            {"experiment_plan_ref": None},
            {"retention_set_ref": None},  # 12.3: retention set must be pre-registered
        ],
    )
    def test_unfalsifiable_proposal_fails(self, override: dict) -> None:
        parent = make_parent()
        candidate = make_candidate(parent)
        proposal = make_proposal(parent, **override)
        result = g0_integrity(proposal, parent, candidate, make_diff(parent, candidate), ALLOWED)
        assert not result.passed


class TestG1Static:
    def test_valid_bundle_round_trips(self) -> None:
        result = g1_static(make_candidate(make_parent()))
        assert result.passed

    def test_tampered_bundle_fails_revalidation(self) -> None:
        result = g1_static(tampered_copy(make_candidate(make_parent())))
        assert not result.passed
        assert "re-validation" in result.reason


class TestG2DevReplay:
    def test_meets_effect_passes(self) -> None:
        result = g2_dev_replay(analysis(TaskSetRole.DEVELOPMENT, mean_delta=0.05), 0.05)
        assert result.passed

    def test_below_effect_fails(self) -> None:
        result = g2_dev_replay(analysis(TaskSetRole.DEVELOPMENT, mean_delta=0.0), 0.05)
        assert not result.passed


class TestG3Holdout:
    def test_ci_low_at_threshold_passes(self) -> None:
        result = g3_holdout(
            analysis(TaskSetRole.PROTECTED_HOLDOUT, mean_delta=0.2, ci_low=0.0), 0.0
        )
        assert result.passed

    def test_positive_mean_with_negative_ci_low_fails(self) -> None:
        """G3 uses ci_low, never the mean: uncertain positives do not promote."""
        result = g3_holdout(
            analysis(TaskSetRole.PROTECTED_HOLDOUT, mean_delta=0.2, ci_low=-0.01), 0.0
        )
        assert not result.passed

    def test_full_run_prefers_parent_when_uncertain(self) -> None:
        analyses = good_analyses()
        analyses[TaskSetRole.PROTECTED_HOLDOUT] = analysis(
            TaskSetRole.PROTECTED_HOLDOUT, mean_delta=0.2, ci_low=-0.01
        )
        decision, _, _ = full_run(analyses=analyses)
        assert decision.action is DecisionAction.REJECT
        assert decision.reason == "prefer_parent_when_uncertain"
        assert len(decision.gate_results) == 10


class TestG4Retention:
    def test_zero_loss_and_ci_passes(self) -> None:
        result = g4_retention(analysis(TaskSetRole.RETENTION, ci_low=0.0, losses=0))
        assert result.passed

    def test_single_regression_fails_despite_positive_mean(self) -> None:
        result = g4_retention(
            analysis(TaskSetRole.RETENTION, mean_delta=0.1, ci_low=0.01, losses=1)
        )
        assert not result.passed
        assert "zero-loss" in result.reason

    def test_ci_below_floor_fails(self) -> None:
        result = g4_retention(
            analysis(TaskSetRole.RETENTION, mean_delta=-0.1, ci_low=-0.2, losses=0),
            retention_floor=0.1,
        )
        assert not result.passed

    def test_floor_tolerance_allows_bounded_soft_regression(self) -> None:
        result = g4_retention(
            analysis(TaskSetRole.RETENTION, mean_delta=-0.01, ci_low=-0.05, losses=0),
            retention_floor=0.1,
        )
        assert result.passed

    def test_full_run_rejects_capability_loss(self) -> None:
        analyses = good_analyses()
        analyses[TaskSetRole.RETENTION] = analysis(
            TaskSetRole.RETENTION, mean_delta=0.1, ci_low=0.01, losses=1
        )
        decision, _, _ = full_run(analyses=analyses)
        assert decision.action is DecisionAction.REJECT
        assert "capability" in decision.reason


class TestG5Adversarial:
    def test_zero_violations_passes(self) -> None:
        assert g5_adversarial(MetricVector(safety_critical_violations=0)).passed

    def test_one_violation_fails(self) -> None:
        assert not g5_adversarial(MetricVector(safety_critical_violations=1)).passed

    def test_full_run_rejects_on_violation(self) -> None:
        decision, _, _ = full_run(metrics=MetricVector(safety_critical_violations=1))
        assert decision.action is DecisionAction.REJECT
        assert "G5" in decision.reason


class TestG6Resource:
    def test_within_ceiling_passes(self) -> None:
        assert g6_resource(1.25, 1.0, 0.25).passed

    def test_over_ceiling_fails(self) -> None:
        assert not g6_resource(1.26, 1.0, 0.25).passed

    def test_full_run_retests_on_cost(self) -> None:
        decision, _, _ = full_run(candidate_cost=10.0, control_cost=1.0)
        assert decision.action is DecisionAction.RETEST


class TestG7Reproducibility:
    def test_full_agreement_passes(self) -> None:
        assert g7_reproducibility(1.0).passed

    def test_below_floor_fails(self) -> None:
        assert not g7_reproducibility(0.9).passed

    def test_full_run_retests_on_flaky_rerun(self) -> None:
        decision, _, _ = full_run(rerun_agreement=0.9)
        assert decision.action is DecisionAction.RETEST


class TestG8Human:
    def _fixture(self):
        parent = make_parent()
        candidate = make_candidate(parent)
        return make_proposal(parent), candidate

    def test_wrong_digest_fails(self) -> None:
        proposal, candidate = self._fixture()
        wrong = approval_for(candidate, bundle_id="sha256:" + "d" * 64)
        result = g8_human(proposal, [wrong], candidate, ApprovalTier.A1_SINGLE_REVIEWER)
        assert not result.passed
        assert "digest" in result.reason

    def test_insufficient_tier_fails(self) -> None:
        proposal, candidate = self._fixture()
        low = approval_for(candidate, tier=ApprovalTier.A1_SINGLE_REVIEWER)
        result = g8_human(proposal, [low], candidate, ApprovalTier.A2_DUAL_CONTROL)
        assert not result.passed
        assert "below required" in result.reason

    def test_self_approval_fails(self) -> None:
        """No self-approval: a proposer may never authorize its own promotion."""
        proposal, candidate = self._fixture()
        selfie = approval_for(candidate, approver=PROPOSER.id)
        result = g8_human(proposal, [selfie], candidate, ApprovalTier.A1_SINGLE_REVIEWER)
        assert not result.passed
        assert "self-approval" in result.reason

    def test_rejection_record_does_not_authorize(self) -> None:
        proposal, candidate = self._fixture()
        rejected = approval_for(candidate, decision="rejected")
        result = g8_human(proposal, [rejected], candidate, ApprovalTier.A1_SINGLE_REVIEWER)
        assert not result.passed

    def test_valid_a1_approval_by_other_principal_passes(self) -> None:
        proposal, candidate = self._fixture()
        approval = approval_for(candidate)
        result = g8_human(proposal, [approval], candidate, ApprovalTier.A1_SINGLE_REVIEWER)
        assert result.passed
        assert result.detail["accepted_approval_ids"] == [approval.approval_id]

    def test_higher_tier_meets_requirement(self) -> None:
        proposal, candidate = self._fixture()
        committee = approval_for(candidate, tier=ApprovalTier.A3_GOVERNANCE_COMMITTEE)
        result = g8_human(proposal, [committee], candidate, ApprovalTier.A1_SINGLE_REVIEWER)
        assert result.passed

    def test_a0_passes_automatically_with_no_approvals(self) -> None:
        """Report 14.5 A0: machine policy records the decision; no signature."""
        proposal, candidate = self._fixture()
        result = g8_human(proposal, [], candidate, ApprovalTier.A0_AUTOMATIC)
        assert result.passed
        assert "machine policy" in result.reason
        assert result.detail["accepted_approval_ids"] == []

    def test_a0_is_vetoed_by_an_explicit_rejection(self) -> None:
        proposal, candidate = self._fixture()
        veto = approval_for(candidate, decision="rejected")
        result = g8_human(proposal, [veto], candidate, ApprovalTier.A0_AUTOMATIC)
        assert not result.passed
        assert "vetoed" in result.reason

    def test_a4_never_authorizes(self) -> None:
        proposal, candidate = self._fixture()
        committee = approval_for(candidate, tier=ApprovalTier.A4_CONVENTIONAL_SDLC)
        result = g8_human(proposal, [committee], candidate, ApprovalTier.A4_CONVENTIONAL_SDLC)
        assert not result.passed
        assert "conventional SDLC" in result.reason

    def test_a0_autonomy_level_reaches_canary_without_human_approval(self) -> None:
        """The A0 path is reachable end-to-end through the PromotionGate."""
        parent = make_parent()
        proposal = make_proposal(parent, autonomy_level=AutonomyLevel.MEMORY_RETRIEVAL_TUNING)
        decision, _, _ = full_run(parent=parent, proposal=proposal, approvals=[])
        assert decision.required_approval_tier is ApprovalTier.A0_AUTOMATIC
        assert decision.action is DecisionAction.CANARY
        assert decision.approvals == []

    def test_full_run_quarantines_without_authority(self) -> None:
        decision, _, _ = full_run(approvals=[])
        assert decision.action is DecisionAction.QUARANTINE
        assert decision.approvals == []
        assert len(decision.gate_results) == 10


class TestG9Canary:
    def test_stage1_stub(self) -> None:
        result = g9_canary(monitoring_window_missions=75)
        assert result.passed
        assert result.reason == (
            "canary deferred to deployment controller; monitoring window recorded"
        )
        assert result.detail["monitoring_window_missions"] == 75


class TestPromotionGateFullRun:
    def test_happy_path_reaches_canary(self) -> None:
        decision, parent, candidate = full_run()
        assert decision.action is DecisionAction.CANARY
        assert [r.gate for r in decision.gate_results] == GATE_ORDER
        assert all(r.passed for r in decision.gate_results)
        assert decision.candidate_bundle_id == candidate.bundle_id
        assert decision.parent_bundle_id == parent.bundle_id
        assert decision.rollback_target == parent.bundle_id
        assert decision.required_approval_tier is ApprovalTier.A1_SINGLE_REVIEWER
        assert decision.proposer == PROPOSER.id
        assert len(decision.approvals) == 1
        assert decision.experiment_id == "exp_fixture"
        assert decision.failed_gates() == []

    def test_gate_with_signer_emits_a_verifiable_decision(self) -> None:
        signer = HMACSigner("gate-key", b"gate-secret")
        decision, _, _ = full_run(signer=signer)
        assert decision.signer == "gate-key"
        assert verify_decision_signature(decision, signer)
        # Any post-hoc edit to a signed field breaks verification.
        tampered = decision.model_copy(
            update={"required_approval_tier": ApprovalTier.A0_AUTOMATIC}
        )
        assert not verify_decision_signature(tampered, signer)
        # An unsigned decision never verifies (fail-closed).
        unsigned, _, _ = full_run()
        assert unsigned.signature is None
        assert not verify_decision_signature(unsigned, signer)

    def test_fail_closed_on_garbage_metrics(self) -> None:
        """A gate that raises becomes a failed GateResult, never a crash."""
        decision, _, _ = full_run(metrics="garbage")
        g5 = next(r for r in decision.gate_results if r.gate is GateId.G5_ADVERSARIAL_SAFETY)
        assert not g5.passed
        assert "AttributeError" in g5.reason
        assert decision.action is DecisionAction.REJECT
        assert len(decision.gate_results) == 10

    def test_fail_closed_on_missing_analyses(self) -> None:
        decision, _, _ = full_run(analyses={})
        for gate in (
            GateId.G2_DEVELOPMENT_REPLAY,
            GateId.G3_PROTECTED_HOLDOUT,
            GateId.G4_CAPABILITY_RETENTION,
        ):
            result = next(r for r in decision.gate_results if r.gate is gate)
            assert not result.passed
            assert "KeyError" in result.reason
        # G3 could not demonstrate an effect, so the parent stays the winner.
        assert decision.action is DecisionAction.REJECT
        assert decision.reason == "prefer_parent_when_uncertain"
        assert len(decision.gate_results) == 10

    def test_undeclared_change_rejects_at_integrity(self) -> None:
        parent = make_parent()
        candidate = make_candidate(parent)
        sneaky = FieldChange(field_path="/config/other", old_value=None, new_value="x")
        diff = make_diff(parent, candidate, changes=[CHANGE, sneaky])
        decision, _, _ = full_run(parent=parent, candidate=candidate, diff=diff)
        assert decision.action is DecisionAction.REJECT
        assert "G0" in decision.reason

    def test_required_tier_follows_autonomy_level(self) -> None:
        parent = make_parent()
        candidate = make_candidate(parent)
        proposal = make_proposal(parent, autonomy_level=AutonomyLevel.WORKFLOW_TOPOLOGY)
        # A1 approval is now insufficient for level 3 -> QUARANTINE, not CANARY.
        decision, _, _ = full_run(parent=parent, candidate=candidate, proposal=proposal)
        assert decision.required_approval_tier is ApprovalTier.A2_DUAL_CONTROL
        assert decision.action is DecisionAction.QUARANTINE

    def test_minimum_practical_effect_is_read_from_the_proposal(self) -> None:
        # Thresholds are pre-registered on the proposal (report 12.3), never
        # gate-time arguments. Dev mean_delta is 0.2; demanding 0.3 fails G2
        # while G3 (ci_low 0.02 vs 0.3) also fails -- G3's REJECT wins.
        parent = make_parent()
        proposal = make_proposal(parent, minimum_practical_effect=0.3)
        decision, _, _ = full_run(parent=parent, proposal=proposal)
        assert decision.action is DecisionAction.REJECT
        assert decision.reason == "prefer_parent_when_uncertain"

    def test_gate_run_accepts_no_threshold_arguments(self) -> None:
        """The caller cannot override the proposer's pre-registered thresholds."""
        with pytest.raises(TypeError):
            full_run(minimum_practical_effect=0.3)
        with pytest.raises(TypeError):
            full_run(retention_floor=0.5)
