"""PromotionGate: fail-closed G0-G9 gate runner (report 13.1, 13.3, 12.2).

The runner is deterministic software, not a model (report 8.1
"Deterministic by default"). It runs every gate in order, converts any
exception inside a gate into a *failed* GateResult (fail-closed: a gate
that cannot produce evidence has not passed), and maps the complete
result set onto one terminal action:

- G0/G1/G5 failure  -> REJECT (integrity/static/safety are non-negotiable)
- G3 failure        -> REJECT, reason ``prefer_parent_when_uncertain``
                       (the unchanged parent remains a valid winner, 13.3)
- G4 failure        -> REJECT (hard capability loss)
- G2/G6/G7 failure  -> RETEST (evidence insufficient or unstable)
- G8 failure        -> QUARANTINE (evidence fine, authority absent)
- all pass          -> CANARY (promotion happens after canary via the
                       deployment controller)

Every decision embeds all gate results, names the parent bundle as the
executable rollback target (report 8.1 "Rollback is executable") and,
when the gate holds a signer, is signed over its canonical payload so
downstream consumers (the deployment controller) can verify that the
decision was produced by this gate and not hand-built (report 8.1,
separation of duties). The statistical thresholds (minimum practical
effect, retention floor) are read from the *proposal* -- pre-registered
by the proposer (report 12.3, 13.4) -- never from gate-time caller
arguments.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from foundry.contracts import (
    ApprovalRecord,
    BundleDiff,
    DecisionAction,
    GateId,
    GateResult,
    ImprovementProposal,
    MetricVector,
    PairedAnalysis,
    PromotionDecision,
    SystemBundle,
    TaskSetRole,
    canonical_json,
)

from .gates import (
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
)

_REJECT_CRITICAL = (GateId.G0_INTEGRITY_AND_SCOPE, GateId.G1_STATIC_CHECKS, GateId.G5_ADVERSARIAL_SAFETY)
_RETEST_GATES = (GateId.G2_DEVELOPMENT_REPLAY, GateId.G6_RESOURCE_MAINTAINABILITY, GateId.G7_REPRODUCIBILITY)
_ROLE_ORDER = (
    TaskSetRole.DEVELOPMENT,
    TaskSetRole.PROTECTED_HOLDOUT,
    TaskSetRole.RETENTION,
    TaskSetRole.ADVERSARIAL,
)


@runtime_checkable
class DecisionSignerLike(Protocol):
    """Duck type for the gate's decision signer (e.g. ``HMACSigner``)."""

    @property
    def key_id(self) -> str: ...

    def sign(self, data: bytes) -> str: ...


@runtime_checkable
class DecisionVerifierLike(Protocol):
    """Duck type for a decision-signature verifier (e.g. ``HMACSigner``)."""

    def verify(self, data: bytes, signature: str) -> bool: ...


def sign_decision(decision: PromotionDecision, signer: DecisionSignerLike) -> PromotionDecision:
    """Sign *decision* over its canonical payload, binding it to the gate."""
    return decision.model_copy(
        update={
            "signer": signer.key_id,
            "signature": signer.sign(canonical_json(decision.signable_payload())),
        }
    )


def verify_decision_signature(
    decision: PromotionDecision, verifier: DecisionVerifierLike
) -> bool:
    """True iff *decision* carries a signature that verifies over its payload.

    An unsigned decision never verifies: absence of a signature is not
    treated as trust (fail-closed).
    """
    if not decision.signature:
        return False
    return verifier.verify(canonical_json(decision.signable_payload()), decision.signature)


def _fail_closed(gate: GateId, fn: Callable[[], GateResult]) -> GateResult:
    """Run one gate; any exception becomes a failed result, never a crash."""
    try:
        return fn()
    except Exception as exc:  # fail-closed by design (report 13.1)
        return GateResult(
            gate=gate,
            passed=False,
            reason=f"fail-closed: {type(exc).__name__}: {exc}",
            detail={"exception_type": type(exc).__name__, "exception": str(exc)},
        )


class PromotionGate:
    """Deterministic promotion gate: evidence in, one governed decision out.

    When constructed with a *signer*, every decision it emits is signed
    over its canonical payload; the deployment controller refuses any
    decision whose signature does not verify.
    """

    def __init__(self, signer: DecisionSignerLike | None = None) -> None:
        self._signer = signer

    def run(
        self,
        proposal: ImprovementProposal,
        parent: SystemBundle,
        candidate: SystemBundle,
        diff: BundleDiff,
        analyses: dict[TaskSetRole, PairedAnalysis],
        metrics: MetricVector,
        approvals: list[ApprovalRecord],
        *,
        allowed_path_prefixes: list[str],
        max_cost_delta_ratio: float = 0.25,
        control_cost: float = 0.0,
        candidate_cost: float = 0.0,
        rerun_agreement: float = 1.0,
    ) -> PromotionDecision:
        required_tier = required_approval_tier(proposal.autonomy_level)
        minimum_practical_effect = proposal.minimum_practical_effect
        retention_floor = proposal.retention_floor
        gate_plan: list[tuple[GateId, Callable[[], GateResult]]] = [
            (
                GateId.G0_INTEGRITY_AND_SCOPE,
                lambda: g0_integrity(proposal, parent, candidate, diff, allowed_path_prefixes),
            ),
            (GateId.G1_STATIC_CHECKS, lambda: g1_static(candidate)),
            (
                GateId.G2_DEVELOPMENT_REPLAY,
                lambda: g2_dev_replay(analyses[TaskSetRole.DEVELOPMENT], minimum_practical_effect),
            ),
            (
                GateId.G3_PROTECTED_HOLDOUT,
                lambda: g3_holdout(analyses[TaskSetRole.PROTECTED_HOLDOUT], minimum_practical_effect),
            ),
            (
                GateId.G4_CAPABILITY_RETENTION,
                lambda: g4_retention(analyses[TaskSetRole.RETENTION], retention_floor),
            ),
            (GateId.G5_ADVERSARIAL_SAFETY, lambda: g5_adversarial(metrics)),
            (
                GateId.G6_RESOURCE_MAINTAINABILITY,
                lambda: g6_resource(candidate_cost, control_cost, max_cost_delta_ratio),
            ),
            (GateId.G7_REPRODUCIBILITY, lambda: g7_reproducibility(rerun_agreement)),
            (
                GateId.G8_HUMAN_AUTHORIZATION,
                lambda: g8_human(proposal, approvals, candidate, required_tier),
            ),
            (GateId.G9_CANARY_MONITORING, lambda: g9_canary()),
        ]
        results = [_fail_closed(gate, fn) for gate, fn in gate_plan]
        action, reason = self._decide(results)
        g8_result = next(r for r in results if r.gate == GateId.G8_HUMAN_AUTHORIZATION)
        accepted_ids = list(g8_result.detail.get("accepted_approval_ids", []))
        decision = PromotionDecision(
            proposal_id=proposal.proposal_id,
            experiment_id=self._experiment_id(analyses),
            candidate_bundle_id=candidate.bundle_id,
            parent_bundle_id=parent.bundle_id,
            action=action,
            required_approval_tier=required_tier,
            proposer=proposal.proposer.id,
            gate_results=results,
            approvals=accepted_ids,
            scope=proposal.deployment_scope.model_dump(mode="json"),
            rollback_target=parent.bundle_id,
            reason=reason,
        )
        if self._signer is not None:
            decision = sign_decision(decision, self._signer)
        return decision

    @staticmethod
    def _decide(results: list[GateResult]) -> tuple[DecisionAction, str]:
        """Map the full gate-result set onto one action (report 13.3)."""
        failed = {result.gate for result in results if not result.passed}
        critical = [gate.value for gate in _REJECT_CRITICAL if gate in failed]
        if critical:
            return (
                DecisionAction.REJECT,
                "critical gate failure (integrity/static/safety): " + ", ".join(critical),
            )
        if GateId.G3_PROTECTED_HOLDOUT in failed:
            return DecisionAction.REJECT, "prefer_parent_when_uncertain"
        if GateId.G4_CAPABILITY_RETENTION in failed:
            return DecisionAction.REJECT, "capability loss on retention tasks"
        retest = [gate.value for gate in _RETEST_GATES if gate in failed]
        if retest:
            return (
                DecisionAction.RETEST,
                "evidence insufficient or unstable: " + ", ".join(retest),
            )
        if GateId.G8_HUMAN_AUTHORIZATION in failed:
            return (
                DecisionAction.QUARANTINE,
                "evidence acceptable but human authorization absent or invalid",
            )
        return (
            DecisionAction.CANARY,
            "all gates passed; promotion proceeds via canary deployment",
        )

    @staticmethod
    def _experiment_id(analyses: dict[TaskSetRole, PairedAnalysis]) -> str | None:
        for role in _ROLE_ORDER:
            if role in analyses:
                return getattr(analyses[role], "experiment_id", None)
        return None
