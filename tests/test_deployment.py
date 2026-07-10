"""Tests for the deployment / canary / rollback controller.

Covers the governance refusals of report 10.4/8.1 (only gate-signed
decisions with complete passing gate coverage, exactly the G8-vetted
approvals, no self-approval, and signed bundles deploy; canary precedes
production), rollback-to-parent semantics, and the event-sourcing
invariant: state is a pure projection of ledger events, so a second
controller over the same ledger sees identical state.
"""

from __future__ import annotations

import random

import pytest

from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    DecisionAction,
    DeploymentRecord,
    Event,
    EventTypes,
    GateId,
    GateResult,
    Integrity,
    PromotionDecision,
    RollbackRecord,
    SignatureRecord,
    SystemBundle,
    utcnow,
)
from foundry.deployment import (
    DeploymentController,
    GovernanceError,
    rebuild_state,
)
from foundry.promotion import sign_decision, verify_decision_signature
from foundry.registry import HMACSigner

GATE_SIGNER = HMACSigner("promotion-gate-test", b"gate-signing-secret")
PROPOSER = "optimizer.gepa"


class FakeLedger:
    """Minimal in-memory LedgerLike: append-only, idempotent, fills integrity."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> Event:
        for existing in self.events:
            if existing.event_id == event.event_id:
                return existing
        integrity = Integrity(
            producer="test-ledger",
            digest=event.payload_digest(),
            prev_digest=self.events[-1].integrity.digest if self.events else None,
            sequence=len(self.events),
        )
        recorded = event.with_integrity(integrity, utcnow())
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
        results = list(self.events)
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        return results


def make_bundle(
    workflow_ref: str,
    parent: str | None = None,
    signed: bool = True,
) -> SystemBundle:
    signatures = (
        [SignatureRecord(signer="human:owner", signature="deadbeef")] if signed else []
    )
    return SystemBundle(
        workflow_ref=workflow_ref,
        parent_bundle_id=parent,
        signature_set=signatures,
    )


def full_gate_results(*, gates_pass: bool = True, drop: GateId | None = None) -> list[GateResult]:
    """All ten gates present and passed (G3 failed when gates_pass=False)."""
    results = []
    for gate in GateId:
        if gate is drop:
            continue
        passed = gates_pass or gate is not GateId.G3_PROTECTED_HOLDOUT
        results.append(
            GateResult(gate=gate, passed=passed, reason="" if passed else "holdout regression")
        )
    return results


def make_decision(
    candidate: SystemBundle,
    *,
    action: DecisionAction = DecisionAction.CANARY,
    tier: ApprovalTier = ApprovalTier.A1_SINGLE_REVIEWER,
    gates_pass: bool = True,
    drop_gate: GateId | None = None,
    gate_results: list[GateResult] | None = None,
    approvals: list[ApprovalRecord] | None = None,
    scope: dict | None = None,
    candidate_id: str | None = None,
    proposer: str = PROPOSER,
    sign: bool = True,
) -> PromotionDecision:
    decision = PromotionDecision(
        candidate_bundle_id=candidate_id or candidate.bundle_id,
        parent_bundle_id=candidate.parent_bundle_id or "",
        action=action,
        required_approval_tier=tier,
        proposer=proposer,
        gate_results=(
            gate_results
            if gate_results is not None
            else full_gate_results(gates_pass=gates_pass, drop=drop_gate)
        ),
        approvals=[approval.approval_id for approval in approvals or []],
        scope=scope or {},
    )
    return sign_decision(decision, GATE_SIGNER) if sign else decision


def make_approval(
    candidate: SystemBundle,
    *,
    approver: str = "human:owner",
    tier: ApprovalTier = ApprovalTier.A1_SINGLE_REVIEWER,
    bundle_id: str | None = None,
    decision: str = "approved",
) -> ApprovalRecord:
    return ApprovalRecord(
        approver=approver,
        tier=tier,
        candidate_bundle_id=bundle_id or candidate.bundle_id,
        decision=decision,
    )


def verify_by_signature_set(bundle: SystemBundle) -> bool:
    return bool(bundle.signature_set)


def verify_by_gate_signer(decision: PromotionDecision) -> bool:
    return verify_decision_signature(decision, GATE_SIGNER)


def make_controller(ledger: FakeLedger) -> DeploymentController:
    return DeploymentController(
        ledger,
        verify_signatures=verify_by_signature_set,
        verify_decision=verify_by_gate_signer,
    )


@pytest.fixture
def ledger() -> FakeLedger:
    return FakeLedger()


@pytest.fixture
def controller(ledger: FakeLedger) -> DeploymentController:
    return make_controller(ledger)


@pytest.fixture
def base() -> SystemBundle:
    return make_bundle("workflow://base/v1")


@pytest.fixture
def candidate(base: SystemBundle) -> SystemBundle:
    return make_bundle("workflow://candidate-a/v1", parent=base.bundle_id)


def canary(controller: DeploymentController, bundle: SystemBundle, **kwargs) -> DeploymentRecord:
    approval = make_approval(bundle)
    decision = make_decision(bundle, action=DecisionAction.CANARY, approvals=[approval], **kwargs)
    return controller.activate(decision, bundle, [approval], mode="canary")


def promote(controller: DeploymentController, bundle: SystemBundle, **kwargs) -> DeploymentRecord:
    approval = make_approval(bundle)
    decision = make_decision(bundle, action=DecisionAction.PROMOTE, approvals=[approval], **kwargs)
    return controller.activate(decision, bundle, [approval], mode="scoped_production")


# -- activation happy path -------------------------------------------------


def test_canary_then_scoped_production_happy_path(controller, ledger, candidate):
    scope = {"monitoring_window_missions": 10, "rollback_triggers": ["error_rate>0.05"]}
    canary_record = canary(controller, candidate, scope=scope)

    assert canary_record.mode == "canary"
    assert canary_record.bundle_id == candidate.bundle_id
    assert canary_record.parent_bundle_id == candidate.parent_bundle_id
    assert canary_record.monitoring_window_missions == 10
    assert canary_record.rollback_triggers == ["error_rate>0.05"]
    assert controller.active_bundle_id() == candidate.bundle_id
    assert ledger.events[-1].event_type == EventTypes.CANARY_STARTED

    production_record = promote(controller, candidate)

    assert production_record.mode == "scoped_production"
    assert controller.active_bundle_id() == candidate.bundle_id
    assert ledger.events[-1].event_type == EventTypes.PROMOTION

    history = controller.history()
    assert len(history) == 2
    assert [record.mode for record in history] == ["canary", "scoped_production"]


def test_canary_defaults_monitoring_window_to_50(controller, candidate):
    record = canary(controller, candidate)
    assert record.monitoring_window_missions == 50
    assert record.rollback_triggers == []


# -- activation refusals ----------------------------------------------------


def test_scoped_production_without_prior_canary_refused(controller, ledger, candidate):
    approval = make_approval(candidate)
    decision = make_decision(candidate, action=DecisionAction.PROMOTE, approvals=[approval])
    with pytest.raises(GovernanceError, match="canary precedes"):
        controller.activate(decision, candidate, [approval], mode="scoped_production")
    assert ledger.events == []
    assert controller.active_bundle_id() is None


@pytest.mark.parametrize(
    "action",
    [DecisionAction.REJECT, DecisionAction.QUARANTINE, DecisionAction.RETEST],
)
def test_non_deploying_decision_action_refused(controller, candidate, action):
    approval = make_approval(candidate)
    decision = make_decision(candidate, action=action, approvals=[approval])
    with pytest.raises(GovernanceError, match="does not authorize deployment"):
        controller.activate(decision, candidate, [approval], mode="canary")


def test_failed_gate_refused(controller, ledger, candidate):
    approval = make_approval(candidate)
    decision = make_decision(candidate, gates_pass=False, approvals=[approval])
    with pytest.raises(GovernanceError, match="failed gate"):
        controller.activate(decision, candidate, [approval], mode="canary")
    assert ledger.events == []


def test_empty_gate_results_is_refused_not_vacuously_passed(controller, ledger, candidate):
    """Absence of gate evidence is failure: a no-gates decision never deploys."""
    approval = make_approval(candidate)
    decision = make_decision(candidate, gate_results=[], approvals=[approval])
    with pytest.raises(GovernanceError, match="missing gate result"):
        controller.activate(decision, candidate, [approval], mode="canary")
    assert ledger.events == []


@pytest.mark.parametrize("gate", [GateId.G0_INTEGRITY_AND_SCOPE, GateId.G8_HUMAN_AUTHORIZATION])
def test_missing_single_gate_refused(controller, candidate, gate):
    approval = make_approval(candidate)
    decision = make_decision(candidate, drop_gate=gate, approvals=[approval])
    with pytest.raises(GovernanceError, match=f"missing gate result.*{gate.value}"):
        controller.activate(decision, candidate, [approval], mode="canary")


def test_hand_built_a0_decision_with_no_gates_cannot_deploy(controller, ledger, candidate):
    """The original exploit: A0 tier + empty gate_results + no approvals."""
    decision = make_decision(
        candidate, tier=ApprovalTier.A0_AUTOMATIC, gate_results=[], approvals=[], sign=False
    )
    with pytest.raises(GovernanceError):
        controller.activate(decision, candidate, [], mode="canary")
    assert ledger.events == []


def test_digest_mismatch_refused(controller, candidate):
    wrong_digest = "sha256:" + "0" * 64
    approval = make_approval(candidate)
    decision = make_decision(candidate, candidate_id=wrong_digest, approvals=[approval])
    with pytest.raises(GovernanceError, match="bound to bundle"):
        controller.activate(decision, candidate, [approval], mode="canary")


def test_content_id_mismatched_bundle_refused(controller, candidate):
    """A model_copy-tampered bundle (stale bundle_id) never deploys."""
    tampered = candidate.model_copy(update={"config": {"strategy": "EVIL_BACKDOOR"}})
    assert tampered.bundle_id != tampered.compute_bundle_id()
    approval = make_approval(tampered)
    decision = make_decision(tampered, approvals=[approval])
    with pytest.raises(GovernanceError, match="content digest"):
        controller.activate(decision, tampered, [approval], mode="canary")


def test_unknown_mode_refused(controller, candidate):
    approval = make_approval(candidate)
    decision = make_decision(candidate, approvals=[approval])
    with pytest.raises(GovernanceError, match="unknown deployment mode"):
        controller.activate(decision, candidate, [approval], mode="shadow")


# -- decision signature binding ------------------------------------------------


def test_unsigned_decision_refused(controller, ledger, candidate):
    approval = make_approval(candidate)
    decision = make_decision(candidate, approvals=[approval], sign=False)
    with pytest.raises(GovernanceError, match="unsigned or its signature"):
        controller.activate(decision, candidate, [approval], mode="canary")
    assert ledger.events == []


def test_tampered_decision_field_breaks_the_signature(controller, candidate):
    """Editing any signed field (here: the asserted tier) invalidates the decision."""
    approval = make_approval(candidate)
    decision = make_decision(
        candidate, tier=ApprovalTier.A1_SINGLE_REVIEWER, approvals=[approval]
    )
    downgraded = decision.model_copy(
        update={"required_approval_tier": ApprovalTier.A0_AUTOMATIC}
    )
    with pytest.raises(GovernanceError, match="unsigned or its signature"):
        controller.activate(downgraded, candidate, [approval], mode="canary")


def test_decision_signed_by_another_key_refused(controller, candidate):
    approval = make_approval(candidate)
    decision = make_decision(candidate, approvals=[approval], sign=False)
    from foundry.promotion import sign_decision as _sign

    forged = _sign(decision, HMACSigner("attacker", b"attacker-secret"))
    with pytest.raises(GovernanceError, match="unsigned or its signature"):
        controller.activate(forged, candidate, [approval], mode="canary")


def test_controller_requires_both_verifiers(ledger):
    """No fail-open default: constructing without verifiers is an error."""
    with pytest.raises(TypeError):
        DeploymentController(ledger)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        DeploymentController(ledger, verify_signatures=verify_by_signature_set)  # type: ignore[call-arg]


# -- approval coverage -------------------------------------------------------


def test_missing_approvals_refused(controller, candidate):
    decision = make_decision(candidate, tier=ApprovalTier.A1_SINGLE_REVIEWER, approvals=[])
    with pytest.raises(GovernanceError, match="requires 1 distinct"):
        controller.activate(decision, candidate, [], mode="canary")


def test_unvetted_approval_refused(controller, candidate):
    """Deploy-time approvals must be exactly the set G8 accepted."""
    vetted = make_approval(candidate)
    stray = make_approval(candidate, approver="human:extra")
    decision = make_decision(candidate, approvals=[vetted])
    with pytest.raises(GovernanceError, match="do not match the set G8 accepted"):
        controller.activate(decision, candidate, [vetted, stray], mode="canary")


def test_vetted_approval_not_presented_refused(controller, candidate):
    vetted = make_approval(candidate)
    decision = make_decision(candidate, approvals=[vetted])
    with pytest.raises(GovernanceError, match="do not match the set G8 accepted"):
        controller.activate(decision, candidate, [], mode="canary")


def test_approval_bound_to_other_digest_refused(controller, candidate):
    stray = make_approval(candidate, bundle_id="sha256:" + "f" * 64)
    decision = make_decision(candidate, approvals=[stray])
    with pytest.raises(GovernanceError, match="bound to digest"):
        controller.activate(decision, candidate, [stray], mode="canary")


def test_rejected_approval_record_does_not_count(controller, candidate):
    rejected = make_approval(candidate, decision="rejected")
    decision = make_decision(candidate, approvals=[rejected])
    with pytest.raises(GovernanceError):
        controller.activate(decision, candidate, [rejected], mode="canary")


def test_dual_control_requires_two_distinct_approvers(controller, candidate):
    duplicated = [
        make_approval(candidate, approver="human:owner", tier=ApprovalTier.A2_DUAL_CONTROL),
        make_approval(candidate, approver="human:owner", tier=ApprovalTier.A2_DUAL_CONTROL),
    ]
    decision = make_decision(candidate, tier=ApprovalTier.A2_DUAL_CONTROL, approvals=duplicated)
    with pytest.raises(GovernanceError, match="requires 2 distinct"):
        controller.activate(decision, candidate, duplicated, mode="canary")

    two_reviewers = [
        make_approval(candidate, approver="human:owner", tier=ApprovalTier.A2_DUAL_CONTROL),
        make_approval(candidate, approver="human:security", tier=ApprovalTier.A2_DUAL_CONTROL),
    ]
    decision = make_decision(candidate, tier=ApprovalTier.A2_DUAL_CONTROL, approvals=two_reviewers)
    record = controller.activate(decision, candidate, two_reviewers, mode="canary")
    assert record.bundle_id == candidate.bundle_id


def test_proposer_self_approval_never_counts_toward_dual_control(controller, candidate):
    """G8's no-self-approval rule holds at the deployment layer too (report 8.1)."""
    self_approval = make_approval(candidate, approver=PROPOSER, tier=ApprovalTier.A2_DUAL_CONTROL)
    reviewer = make_approval(candidate, approver="human:security", tier=ApprovalTier.A2_DUAL_CONTROL)
    decision = make_decision(
        candidate,
        tier=ApprovalTier.A2_DUAL_CONTROL,
        approvals=[self_approval, reviewer],
        proposer=PROPOSER,
    )
    with pytest.raises(GovernanceError, match="requires 2 distinct non-proposer"):
        controller.activate(decision, candidate, [self_approval, reviewer], mode="canary")


def test_lower_tier_approval_does_not_cover_higher_requirement(controller, candidate):
    low_tier = [
        make_approval(candidate, approver="human:owner", tier=ApprovalTier.A1_SINGLE_REVIEWER),
        make_approval(candidate, approver="human:security", tier=ApprovalTier.A1_SINGLE_REVIEWER),
    ]
    decision = make_decision(candidate, tier=ApprovalTier.A2_DUAL_CONTROL, approvals=low_tier)
    with pytest.raises(GovernanceError, match="requires 2 distinct"):
        controller.activate(decision, candidate, low_tier, mode="canary")


def test_higher_tier_approval_covers_lower_requirement(controller, candidate):
    approval = make_approval(candidate, tier=ApprovalTier.A2_DUAL_CONTROL)
    decision = make_decision(
        candidate, tier=ApprovalTier.A1_SINGLE_REVIEWER, approvals=[approval]
    )
    record = controller.activate(decision, candidate, [approval], mode="canary")
    assert record.mode == "canary"


def test_a0_automatic_needs_no_approvals(controller, candidate):
    decision = make_decision(candidate, tier=ApprovalTier.A0_AUTOMATIC, approvals=[])
    record = controller.activate(decision, candidate, [], mode="canary")
    assert record.bundle_id == candidate.bundle_id


def test_a4_never_deploys_autonomously(controller, candidate):
    approvals = [
        make_approval(candidate, approver=f"human:{i}", tier=ApprovalTier.A4_CONVENTIONAL_SDLC)
        for i in range(4)
    ]
    decision = make_decision(
        candidate, tier=ApprovalTier.A4_CONVENTIONAL_SDLC, approvals=approvals
    )
    with pytest.raises(GovernanceError, match="conventional SDLC"):
        controller.activate(decision, candidate, approvals, mode="canary")


# -- signature verification ---------------------------------------------------


def test_unsigned_bundle_refused(ledger, base):
    controller = make_controller(ledger)
    unsigned = make_bundle("workflow://unsigned/v1", parent=base.bundle_id, signed=False)
    approval = make_approval(unsigned)
    decision = make_decision(unsigned, approvals=[approval])
    with pytest.raises(GovernanceError, match="signature verification"):
        controller.activate(decision, unsigned, [approval], mode="canary")
    assert ledger.events == []


# -- rollback -----------------------------------------------------------------


def test_rollback_returns_to_parent(controller, ledger, base, candidate):
    canary(controller, candidate)
    record = controller.rollback(trigger="error_rate>0.05")

    assert isinstance(record, RollbackRecord)
    assert record.from_bundle_id == candidate.bundle_id
    assert record.to_bundle_id == base.bundle_id
    assert record.trigger == "error_rate>0.05"
    assert record.initiated_by == "system"
    assert controller.active_bundle_id() == base.bundle_id
    assert ledger.events[-1].event_type == EventTypes.ROLLBACK

    history = controller.history()
    assert len(history) == 2
    assert isinstance(history[-1], RollbackRecord)


def test_rollback_with_nothing_active_refused(controller, ledger):
    with pytest.raises(GovernanceError, match="no active bundle"):
        controller.rollback(trigger="drill")
    assert ledger.events == []


def test_rollback_without_recorded_parent_refused(controller):
    root = make_bundle("workflow://root/v1", parent=None)
    canary(controller, root)
    with pytest.raises(GovernanceError, match="no recorded parent"):
        controller.rollback(trigger="drill")


def test_rollback_to_parent_of_explicit_bundle(controller, base, candidate):
    canary(controller, candidate)
    child = make_bundle("workflow://candidate-b/v1", parent=candidate.bundle_id)
    canary(controller, child)

    record = controller.rollback(candidate.bundle_id, trigger="drill", initiated_by="human:owner")

    assert record.from_bundle_id == child.bundle_id
    assert record.to_bundle_id == base.bundle_id
    assert record.initiated_by == "human:owner"
    assert controller.active_bundle_id() == base.bundle_id


def test_rollback_of_never_deployed_bundle_refused(controller, candidate):
    canary(controller, candidate)
    with pytest.raises(GovernanceError, match="no deployment record"):
        controller.rollback("sha256:" + "a" * 64, trigger="drill")


# -- event sourcing -----------------------------------------------------------


def test_second_controller_over_same_ledger_projects_identical_state(
    controller, ledger, base, candidate
):
    canary(controller, candidate)
    promote(controller, candidate)
    controller.rollback(trigger="drill")

    rebuilt = make_controller(ledger)

    assert rebuilt.active_bundle_id() == controller.active_bundle_id() == base.bundle_id
    assert rebuilt.history() == controller.history()
    assert rebuilt.state() == controller.state()


def test_interleaved_sequence_yields_correct_final_state(controller, ledger, candidate):
    bundle_b = make_bundle("workflow://candidate-b/v1", parent=candidate.bundle_id)

    canary(controller, candidate)
    promote(controller, candidate)
    canary(controller, bundle_b)
    assert controller.active_bundle_id() == bundle_b.bundle_id

    rollback = controller.rollback(trigger="canary_regression")

    assert rollback.from_bundle_id == bundle_b.bundle_id
    assert rollback.to_bundle_id == candidate.bundle_id
    assert controller.active_bundle_id() == candidate.bundle_id

    history = controller.history()
    assert len(history) == 4
    assert [type(record) for record in history] == [
        DeploymentRecord,
        DeploymentRecord,
        DeploymentRecord,
        RollbackRecord,
    ]
    assert controller.state().canaried_bundle_ids == {
        candidate.bundle_id,
        bundle_b.bundle_id,
    }


def test_rebuild_state_is_pure_and_order_independent(controller, ledger, base, candidate):
    bundle_b = make_bundle("workflow://candidate-b/v1", parent=candidate.bundle_id)
    canary(controller, candidate)
    promote(controller, candidate)
    canary(controller, bundle_b)
    controller.rollback(trigger="drill")

    shuffled = list(ledger.events)
    random.Random(7).shuffle(shuffled)
    state = rebuild_state(shuffled)

    assert state == rebuild_state(ledger.events) == controller.state()
    assert state.active_bundle_id == candidate.bundle_id
    assert state.active_parent_id == base.bundle_id
    assert state.parents[candidate.bundle_id] == base.bundle_id
    assert state.parents[bundle_b.bundle_id] == candidate.bundle_id


def test_rebuild_state_ignores_unrelated_events(controller, ledger, candidate):
    ledger.append(Event(event_type=EventTypes.MISSION_STARTED, mission_id="mis_x"))
    canary(controller, candidate)
    ledger.append(Event(event_type=EventTypes.METRIC_COMPUTED, run_id="run_x"))

    state = rebuild_state(ledger.events)

    assert state.active_bundle_id == candidate.bundle_id
    assert len(state.history) == 1


def test_history_is_append_only_across_supersession(controller, candidate):
    bundle_b = make_bundle("workflow://candidate-b/v1", parent=candidate.bundle_id)
    first = canary(controller, candidate)
    canary(controller, bundle_b)

    history = controller.history()
    assert history[0] == first
    assert controller.active_bundle_id() == bundle_b.bundle_id
