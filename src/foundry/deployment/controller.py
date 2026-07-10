"""Deployment / canary / rollback controller (report sections 10.4, 13.6, 9.2 step 8).

The controller is an event-sourced projection over the governance ledger.
Activations and rollbacks exist *only* as ledger events
(``governance.canary``, ``governance.promotion``, ``governance.rollback``);
the active-bundle state is recomputed by replaying those events in ledger
sequence order via the pure function :func:`rebuild_state`. The controller
keeps no authoritative in-memory state, so any controller constructed over
the same ledger projects the identical state.

Governance invariants enforced here (report 10.4, 14.5, 8.1):

- the decision must be signed by the promotion gate that produced it
  (verified over its canonical payload); a hand-built decision is refused;
- only decisions whose action is ``canary`` or ``promote`` may activate;
- the decision must reference the exact candidate content digest, and the
  candidate's content address must recompute (no ``model_copy`` tampering);
- every gate G0-G9 must be present in the decision AND passed -- absence
  of gate evidence is failure, never success (fail-closed);
- the approvals presented at deploy time must be exactly the set G8
  accepted (referenced by approval_id), and the required tier must be
  covered by distinct non-proposer approvers bound to that exact digest
  (no self-approval; A4 changes never deploy autonomously);
- only signed bundles deploy (the verifier is a mandatory constructor
  argument -- there is no fail-open default);
- a canary deployment must precede scoped production for the same bundle
  (report 13.6: canary serves a small scope under automatic rollback).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    DecisionAction,
    DeploymentRecord,
    Event,
    EventTypes,
    GateId,
    LedgerLike,
    PromotionDecision,
    RollbackRecord,
    SystemBundle,
)

MODE_CANARY = "canary"
MODE_SCOPED_PRODUCTION = "scoped_production"

_ALLOWED_MODES = (MODE_CANARY, MODE_SCOPED_PRODUCTION)
_ALLOWED_ACTIONS = (DecisionAction.CANARY, DecisionAction.PROMOTE)
_DEPLOYMENT_EVENT_TYPES = (
    EventTypes.CANARY_STARTED,
    EventTypes.PROMOTION,
    EventTypes.ROLLBACK,
)
_DEFAULT_MONITORING_WINDOW = 50

_TIER_RANK: dict[ApprovalTier, int] = {
    ApprovalTier.A0_AUTOMATIC: 0,
    ApprovalTier.A1_SINGLE_REVIEWER: 1,
    ApprovalTier.A2_DUAL_CONTROL: 2,
    ApprovalTier.A3_GOVERNANCE_COMMITTEE: 3,
    ApprovalTier.A4_CONVENTIONAL_SDLC: 4,
}

# Minimum count of *distinct* approvers per tier (report 14.5: A1 one
# reviewer, A2 dual control, A3 committee review). A4 is intentionally
# absent: conventional-SDLC changes have no autonomous deployment path.
_MIN_DISTINCT_APPROVERS: dict[ApprovalTier, int] = {
    ApprovalTier.A0_AUTOMATIC: 0,
    ApprovalTier.A1_SINGLE_REVIEWER: 1,
    ApprovalTier.A2_DUAL_CONTROL: 2,
    ApprovalTier.A3_GOVERNANCE_COMMITTEE: 3,
}


class GovernanceError(Exception):
    """An activation or rollback would violate deployment governance."""


@dataclass(frozen=True)
class DeploymentState:
    """Pure projection of the deployment history at one ledger position.

    ``parents`` maps every bundle that has ever been activated to the
    parent recorded on its deployment record; rollback resolves targets
    through it, so rolling back never needs state outside the ledger.
    """

    active_bundle_id: str | None = None
    active_parent_id: str | None = None
    history: tuple[DeploymentRecord | RollbackRecord, ...] = ()
    canaried_bundle_ids: frozenset[str] = frozenset()
    parents: dict[str, str | None] = field(default_factory=dict)


def _ledger_sequence(event: Event) -> int:
    integrity = event.integrity
    return integrity.sequence if integrity is not None else -1


def rebuild_state(events: Iterable[Event]) -> DeploymentState:
    """Replay deployment events into a :class:`DeploymentState`.

    Events are replayed in ledger sequence order when all carry an
    integrity block (the normal case); otherwise in the given order.
    Non-deployment event types are ignored, so callers may pass a full
    ledger dump. A newer activation supersedes the previous one; a
    rollback makes its target the active bundle. History is append-only.
    """
    ordered = list(events)
    if all(event.integrity is not None for event in ordered):
        ordered.sort(key=_ledger_sequence)

    active: str | None = None
    history: list[DeploymentRecord | RollbackRecord] = []
    canaried: set[str] = set()
    parents: dict[str, str | None] = {}

    for event in ordered:
        if event.event_type in (EventTypes.CANARY_STARTED, EventTypes.PROMOTION):
            deployment = DeploymentRecord.model_validate(event.payload["deployment"])
            history.append(deployment)
            parents[deployment.bundle_id] = deployment.parent_bundle_id
            active = deployment.bundle_id
            if event.event_type == EventTypes.CANARY_STARTED:
                canaried.add(deployment.bundle_id)
        elif event.event_type == EventTypes.ROLLBACK:
            rollback = RollbackRecord.model_validate(event.payload["rollback"])
            history.append(rollback)
            active = rollback.to_bundle_id

    return DeploymentState(
        active_bundle_id=active,
        active_parent_id=parents.get(active) if active is not None else None,
        history=tuple(history),
        canaried_bundle_ids=frozenset(canaried),
        parents=parents,
    )


class DeploymentController:
    """Deterministic activation / rollback state machine over a ledger.

    ``verify_signatures`` is the trust hook of report 10.4 ("may deploy
    only signed approved bundles") and ``verify_decision`` binds the
    presented :class:`PromotionDecision` to the gate that produced it
    (e.g. ``foundry.promotion.verify_decision_signature`` closed over the
    gate's key). Both are mandatory: a controller with no verifier would
    be fail-open, which the deployment trust boundary forbids.
    """

    def __init__(
        self,
        ledger: LedgerLike,
        verify_signatures: Callable[[SystemBundle], bool],
        verify_decision: Callable[[PromotionDecision], bool],
    ) -> None:
        self._ledger = ledger
        self._verify_signatures = verify_signatures
        self._verify_decision = verify_decision

    # -- projection -------------------------------------------------------

    def state(self) -> DeploymentState:
        """Rebuild the deployment projection from the ledger, event-sourced."""
        events: list[Event] = []
        for event_type in _DEPLOYMENT_EVENT_TYPES:
            events.extend(self._ledger.query(event_type=event_type))
        return rebuild_state(events)

    def active_bundle_id(self) -> str | None:
        return self.state().active_bundle_id

    def history(self) -> list[DeploymentRecord | RollbackRecord]:
        return list(self.state().history)

    # -- commands ---------------------------------------------------------

    def activate(
        self,
        decision: PromotionDecision,
        candidate: SystemBundle,
        approvals: list[ApprovalRecord],
        *,
        mode: str,
    ) -> DeploymentRecord:
        """Activate *candidate* under *decision*, emitting a ledger event.

        ``mode="canary"`` emits ``governance.canary``; ``mode=
        "scoped_production"`` emits ``governance.promotion`` and requires
        a prior canary deployment of the same bundle in the ledger.
        """
        if mode not in _ALLOWED_MODES:
            raise GovernanceError(
                f"unknown deployment mode {mode!r}; allowed: {list(_ALLOWED_MODES)}"
            )
        if decision.action not in _ALLOWED_ACTIONS:
            raise GovernanceError(
                f"decision {decision.decision_id} action {decision.action.value!r} "
                "does not authorize deployment (requires canary or promote)"
            )
        if decision.candidate_bundle_id != candidate.bundle_id:
            raise GovernanceError(
                f"decision {decision.decision_id} is bound to bundle "
                f"{decision.candidate_bundle_id!r}, not candidate {candidate.bundle_id!r}"
            )
        if candidate.bundle_id != candidate.compute_bundle_id():
            raise GovernanceError(
                f"candidate bundle_id {candidate.bundle_id!r} does not match its "
                f"content digest {candidate.compute_bundle_id()!r}; refusing a "
                "content/id-mismatched bundle"
            )
        if not self._verify_decision(decision):
            raise GovernanceError(
                f"decision {decision.decision_id} is unsigned or its signature does "
                "not verify; only gate-produced decisions deploy (report 8.1)"
            )
        self._check_gate_coverage(decision)
        vetted = self._vetted_approvals(decision, approvals)
        self._check_approvals(
            decision.required_approval_tier,
            candidate.bundle_id,
            vetted,
            proposer=decision.proposer,
        )
        if not self._verify_signatures(candidate):
            raise GovernanceError(
                f"bundle {candidate.bundle_id} failed signature verification; "
                "only signed approved bundles deploy (report 10.4)"
            )
        if mode == MODE_SCOPED_PRODUCTION:
            state = self.state()
            if candidate.bundle_id not in state.canaried_bundle_ids:
                raise GovernanceError(
                    f"bundle {candidate.bundle_id} has no prior canary deployment; "
                    "canary precedes scoped production (report 13.6)"
                )

        record = DeploymentRecord(
            bundle_id=candidate.bundle_id,
            parent_bundle_id=candidate.parent_bundle_id,
            decision_id=decision.decision_id,
            scope=dict(decision.scope),
            mode=mode,
            monitoring_window_missions=int(
                decision.scope.get("monitoring_window_missions", _DEFAULT_MONITORING_WINDOW)
            ),
            rollback_triggers=list(decision.scope.get("rollback_triggers", [])),
        )
        event_type = EventTypes.CANARY_STARTED if mode == MODE_CANARY else EventTypes.PROMOTION
        self._ledger.append(
            Event(
                event_type=event_type,
                system_bundle_id=candidate.bundle_id,
                actor="deployment-controller",
                subject=decision.decision_id,
                payload={"deployment": record.model_dump(mode="json")},
            )
        )
        return record

    def rollback(
        self,
        to_parent_of: str | None = None,
        *,
        trigger: str,
        initiated_by: str = "system",
    ) -> RollbackRecord:
        """Roll the current active bundle back, emitting ``governance.rollback``.

        The rollback target is the recorded parent of ``to_parent_of``
        (default: the parent of the current active bundle). Refuses when
        nothing is active, when the named bundle was never deployed, or
        when it has no recorded parent.
        """
        state = self.state()
        if state.active_bundle_id is None:
            raise GovernanceError("no active bundle; rollback refused")
        source = to_parent_of if to_parent_of is not None else state.active_bundle_id
        if source not in state.parents:
            raise GovernanceError(
                f"bundle {source} has no deployment record; rollback refused"
            )
        target = state.parents[source]
        if target is None:
            raise GovernanceError(
                f"bundle {source} has no recorded parent; rollback refused"
            )

        record = RollbackRecord(
            from_bundle_id=state.active_bundle_id,
            to_bundle_id=target,
            trigger=trigger,
            initiated_by=initiated_by,
        )
        self._ledger.append(
            Event(
                event_type=EventTypes.ROLLBACK,
                system_bundle_id=target,
                actor=initiated_by,
                subject=state.active_bundle_id,
                payload={"rollback": record.model_dump(mode="json")},
            )
        )
        return record

    # -- internals --------------------------------------------------------

    @staticmethod
    def _check_gate_coverage(decision: PromotionDecision) -> None:
        """Require every gate G0-G9 present AND passed (fail-closed).

        An empty or partial ``gate_results`` list is a refusal, never a
        vacuous pass: absence of gate evidence is not evidence of passing.
        """
        present = {result.gate for result in decision.gate_results}
        missing = [gate.value for gate in GateId if gate not in present]
        if missing:
            raise GovernanceError(
                f"decision {decision.decision_id} is missing gate result(s): "
                f"{', '.join(missing)}; every gate G0-G9 must be present and passed"
            )
        failed = decision.failed_gates()
        if failed:
            gates = ", ".join(result.gate.value for result in failed)
            raise GovernanceError(
                f"decision {decision.decision_id} carries failed gate(s): {gates}"
            )

    @staticmethod
    def _vetted_approvals(
        decision: PromotionDecision, approvals: list[ApprovalRecord]
    ) -> list[ApprovalRecord]:
        """The presented approvals must be exactly the set G8 accepted.

        The gate records the accepted approval ids on the (signed)
        decision; deployment refuses any record the gate did not vet and
        any vetted record that is not presented.
        """
        supplied = {approval.approval_id: approval for approval in approvals}
        vetted_ids = set(decision.approvals)
        if set(supplied) != vetted_ids:
            extra = sorted(set(supplied) - vetted_ids)
            absent = sorted(vetted_ids - set(supplied))
            raise GovernanceError(
                f"deploy-time approvals do not match the set G8 accepted on "
                f"decision {decision.decision_id} (unvetted: {extra}; missing: {absent})"
            )
        return [supplied[approval_id] for approval_id in sorted(vetted_ids)]

    def _check_approvals(
        self,
        required: ApprovalTier,
        bundle_id: str,
        approvals: list[ApprovalRecord],
        *,
        proposer: str | None,
    ) -> None:
        if required is ApprovalTier.A4_CONVENTIONAL_SDLC:
            raise GovernanceError(
                "tier A4 changes go through conventional SDLC only; "
                "no autonomous deployment path (report 14.5)"
            )
        needed = _MIN_DISTINCT_APPROVERS[required]
        if needed == 0:
            return
        approvers = {
            approval.approver
            for approval in approvals
            if approval.decision == "approved"
            and approval.candidate_bundle_id == bundle_id
            and _TIER_RANK[approval.tier] >= _TIER_RANK[required]
            and approval.approver != proposer  # no self-approval (report 8.1)
        }
        if len(approvers) < needed:
            raise GovernanceError(
                f"approval tier {required.value} requires {needed} distinct "
                f"non-proposer approver(s) bound to digest {bundle_id}; found {len(approvers)}"
            )
