"""The G0-G9 promotion gates (report sections 13.1, 13.2, Appendix B).

Each gate is a pure function from evidence to a ``GateResult``: gates
compute facts, they never take actions. The action policy that maps a
set of gate results to a ``PromotionDecision`` lives in
``gate_runner.PromotionGate`` (report 13.3). Statistical rules are the
pre-registered ones of report 13.4: G3 is a one-sided lower-confidence-
bound test (``ci_low``, never the mean) and G4 is a non-inferiority test
with a zero-loss requirement for critical capabilities.

The separation-of-powers invariant of report 8.1 ("No self-approval") is
enforced structurally in G8: an approval by the proposing principal can
never satisfy human authorization, regardless of tier.
"""

from __future__ import annotations

from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    AutonomyLevel,
    BundleDiff,
    GateId,
    GateResult,
    ImprovementProposal,
    MetricVector,
    PairedAnalysis,
    SystemBundle,
)

_TIER_RANK: dict[ApprovalTier, int] = {
    ApprovalTier.A0_AUTOMATIC: 0,
    ApprovalTier.A1_SINGLE_REVIEWER: 1,
    ApprovalTier.A2_DUAL_CONTROL: 2,
    ApprovalTier.A3_GOVERNANCE_COMMITTEE: 3,
    ApprovalTier.A4_CONVENTIONAL_SDLC: 4,
}


def tier_meets(tier: ApprovalTier, required: ApprovalTier) -> bool:
    """True when *tier* meets or exceeds *required* (A0 < A1 < A2 < A3 < A4)."""
    return _TIER_RANK[tier] >= _TIER_RANK[required]


def required_approval_tier(level: AutonomyLevel | int) -> ApprovalTier:
    """Approval tier required for an autonomy level (report 14.5).

    Level 5 (code/training changes) maps to A4 -- conventional SDLC only,
    with no autonomous promotion path (report 8.4, 14.5) -- never to A3.
    """
    value = int(level)
    if value >= 5:
        return ApprovalTier.A4_CONVENTIONAL_SDLC
    if value == 4:
        return ApprovalTier.A3_GOVERNANCE_COMMITTEE
    if value == 3:
        return ApprovalTier.A2_DUAL_CONTROL
    if value == 2:
        return ApprovalTier.A1_SINGLE_REVIEWER
    return ApprovalTier.A0_AUTOMATIC


def _path_within(path: str, prefix: str) -> bool:
    """JSON-pointer prefix match: exact segment boundaries, not string prefixes.

    The same rule as ``BundleRegistry.fork`` and the PDP, so the gate's
    mutation-surface check can never admit a sibling key (e.g.
    ``/config/strategy_evil`` under the prefix ``/config/strategy``).
    """
    if path == prefix:
        return True
    return path.startswith(prefix if prefix.endswith("/") else prefix + "/")


def g0_integrity(
    proposal: ImprovementProposal,
    parent: SystemBundle,
    candidate: SystemBundle,
    diff: BundleDiff,
    allowed_path_prefixes: list[str],
) -> GateResult:
    """G0 -- integrity and scope: lineage, content address, mutation surface.

    Rejects undeclared changes (Appendix B.1: "no undeclared file changed"):
    every diff path must be inside an allowed prefix AND declared in the
    proposal. A proposal without hypothesis, rollback condition or
    experiment plan is not falsifiable and cannot enter the pipeline
    (report 12.3).
    """
    failures: list[str] = []
    if candidate.parent_bundle_id != parent.bundle_id:
        failures.append(
            f"candidate.parent_bundle_id {candidate.parent_bundle_id!r} "
            f"does not match parent bundle id {parent.bundle_id!r}"
        )
    computed = candidate.compute_bundle_id()
    if candidate.bundle_id != computed:
        failures.append(
            f"candidate.bundle_id {candidate.bundle_id!r} does not match "
            f"its content digest {computed!r}"
        )
    declared = {change.field_path for change in proposal.changes}
    for path in diff.touched_paths():
        if not any(_path_within(path, prefix) for prefix in allowed_path_prefixes):
            failures.append(f"diff path {path!r} is outside the allowed mutation surface")
        if path not in declared:
            failures.append(f"diff path {path!r} is an undeclared change (not in proposal.changes)")
    if not proposal.hypothesis.strip():
        failures.append("proposal has an empty hypothesis")
    if not proposal.rollback_condition.strip():
        failures.append("proposal has an empty rollback_condition")
    if not proposal.experiment_plan_ref:
        failures.append("proposal has no experiment_plan_ref")
    if not proposal.retention_set_ref:
        failures.append("proposal declares no retention_set_ref (capability-retention set, report 12.3)")
    passed = not failures
    return GateResult(
        gate=GateId.G0_INTEGRITY_AND_SCOPE,
        passed=passed,
        reason="integrity and scope verified" if passed else "; ".join(failures),
        detail={
            "failures": failures,
            "declared_paths": sorted(declared),
            "touched_paths": diff.touched_paths(),
            "allowed_path_prefixes": list(allowed_path_prefixes),
        },
    )


def g1_static(candidate: SystemBundle) -> GateResult:
    """G1 -- static checks: schema re-validation of the bundle payload.

    Round-trips the candidate through its own JSON serialization; the
    ``SystemBundle`` model validator recomputes and checks the content
    address, so tampering surfaces here as a validation error.
    """
    try:
        revalidated = SystemBundle.model_validate(candidate.model_dump(mode="json"))
    except ValueError as exc:  # pydantic ValidationError subclasses ValueError
        return GateResult(
            gate=GateId.G1_STATIC_CHECKS,
            passed=False,
            reason=f"bundle failed schema re-validation: {exc}",
            detail={"error": str(exc)},
        )
    if revalidated.bundle_id != candidate.bundle_id:
        return GateResult(
            gate=GateId.G1_STATIC_CHECKS,
            passed=False,
            reason="bundle_id changed across serialization round-trip",
            detail={"before": candidate.bundle_id, "after": revalidated.bundle_id},
        )
    return GateResult(
        gate=GateId.G1_STATIC_CHECKS,
        passed=True,
        reason="bundle payload round-trips through schema validation",
        detail={"bundle_id": candidate.bundle_id},
    )


def g2_dev_replay(analysis_dev: PairedAnalysis, minimum_practical_effect: float) -> GateResult:
    """G2 -- development replay: practical gain on prior tasks (mean delta)."""
    passed = analysis_dev.mean_delta >= minimum_practical_effect
    return GateResult(
        gate=GateId.G2_DEVELOPMENT_REPLAY,
        passed=passed,
        reason=(
            f"mean_delta={analysis_dev.mean_delta} "
            f"{'meets' if passed else 'below'} minimum_practical_effect={minimum_practical_effect}"
        ),
        detail={
            "mean_delta": analysis_dev.mean_delta,
            "minimum_practical_effect": minimum_practical_effect,
            "n_pairs": analysis_dev.n_pairs,
        },
    )


def g3_holdout(analysis_holdout: PairedAnalysis, minimum_practical_effect: float) -> GateResult:
    """G3 -- protected holdout: pre-registered one-sided rule (report 13.4).

    Passes only when the lower confidence bound clears the minimum
    practical effect: ``ci_low``, never the mean, so an uncertain positive
    mean cannot promote (prefer the parent when uncertain, report 13.3).
    """
    passed = analysis_holdout.ci_low >= minimum_practical_effect
    return GateResult(
        gate=GateId.G3_PROTECTED_HOLDOUT,
        passed=passed,
        reason=(
            f"ci_low={analysis_holdout.ci_low} "
            f"{'meets' if passed else 'below'} minimum_practical_effect={minimum_practical_effect} "
            f"(one-sided lower-bound rule; mean_delta={analysis_holdout.mean_delta} is not the criterion)"
        ),
        detail={
            "ci_low": analysis_holdout.ci_low,
            "ci_high": analysis_holdout.ci_high,
            "mean_delta": analysis_holdout.mean_delta,
            "minimum_practical_effect": minimum_practical_effect,
            "n_pairs": analysis_holdout.n_pairs,
        },
    )


def g4_retention(analysis_retention: PairedAnalysis, retention_floor: float = 0.0) -> GateResult:
    """G4 -- capability retention: non-inferiority with zero-loss (report 13.2).

    Two conditions, both required: the lower confidence bound must not
    fall below the (non-positive) retention floor, and there must be zero
    per-task losses -- a critical capability regressed on even one
    retention task is a hard capability loss.
    """
    floor = -abs(retention_floor)
    ci_ok = analysis_retention.ci_low >= floor
    zero_loss = analysis_retention.losses == 0
    passed = ci_ok and zero_loss
    failures: list[str] = []
    if not ci_ok:
        failures.append(f"ci_low={analysis_retention.ci_low} below retention floor {floor}")
    if not zero_loss:
        failures.append(f"{analysis_retention.losses} retention task(s) regressed (zero-loss rule)")
    return GateResult(
        gate=GateId.G4_CAPABILITY_RETENTION,
        passed=passed,
        reason="non-inferior with zero retention losses" if passed else "; ".join(failures),
        detail={
            "ci_low": analysis_retention.ci_low,
            "retention_floor": floor,
            "losses": analysis_retention.losses,
            "n_pairs": analysis_retention.n_pairs,
        },
    )


def g5_adversarial(metrics: MetricVector) -> GateResult:
    """G5 -- adversarial and safety: zero critical violations, no trade-offs."""
    violations = metrics.safety_critical_violations
    passed = violations == 0
    return GateResult(
        gate=GateId.G5_ADVERSARIAL_SAFETY,
        passed=passed,
        reason=(
            "zero safety-critical violations"
            if passed
            else f"{violations} safety-critical violation(s); safety is a hard constraint"
        ),
        detail={"safety_critical_violations": violations},
    )


def g6_resource(candidate_cost: float, control_cost: float, max_cost_delta_ratio: float) -> GateResult:
    """G6 -- resource and maintainability: profile cost ceiling."""
    ceiling = control_cost * (1.0 + max_cost_delta_ratio)
    passed = candidate_cost <= ceiling
    return GateResult(
        gate=GateId.G6_RESOURCE_MAINTAINABILITY,
        passed=passed,
        reason=(
            f"candidate_cost={candidate_cost} "
            f"{'within' if passed else 'exceeds'} ceiling={ceiling} "
            f"(control_cost={control_cost}, max_cost_delta_ratio={max_cost_delta_ratio})"
        ),
        detail={
            "candidate_cost": candidate_cost,
            "control_cost": control_cost,
            "max_cost_delta_ratio": max_cost_delta_ratio,
            "ceiling": ceiling,
        },
    )


def g7_reproducibility(rerun_agreement: float, floor: float = 1.0) -> GateResult:
    """G7 -- reproducibility: repeated-execution agreement meets the floor."""
    passed = rerun_agreement >= floor
    return GateResult(
        gate=GateId.G7_REPRODUCIBILITY,
        passed=passed,
        reason=(
            f"rerun_agreement={rerun_agreement} "
            f"{'meets' if passed else 'below'} reproducibility floor={floor}"
        ),
        detail={"rerun_agreement": rerun_agreement, "floor": floor},
    )


def g8_human(
    proposal: ImprovementProposal,
    approvals: list[ApprovalRecord],
    candidate: SystemBundle,
    required_tier: ApprovalTier,
) -> GateResult:
    """G8 -- human authorization (report 13.1, 14.5).

    A qualifying approval must: be an approval (not a rejection), bind the
    EXACT candidate digest, meet or exceed the required tier, and come
    from a principal other than the proposer (no self-approval, report
    8.1/12 -- a proposer may never authorize its own promotion).

    Tier A0 (report 14.5: "Machine policy records decision and canary")
    passes automatically with no human signature unless an explicit
    rejection is bound to the candidate digest. Tier A4 never passes:
    conventional-SDLC changes have no autonomous authorization path.
    """
    if required_tier is ApprovalTier.A4_CONVENTIONAL_SDLC:
        return GateResult(
            gate=GateId.G8_HUMAN_AUTHORIZATION,
            passed=False,
            reason="tier A4: conventional SDLC only; no autonomous authorization path (report 14.5)",
            detail={"required_tier": required_tier.value, "accepted_approval_ids": [], "rejected": []},
        )
    if required_tier is ApprovalTier.A0_AUTOMATIC:
        vetoes = [
            f"{approval.approval_id}: explicit rejection by {approval.approver!r}"
            for approval in approvals
            if approval.decision == "rejected"
            and approval.candidate_bundle_id == candidate.bundle_id
        ]
        return GateResult(
            gate=GateId.G8_HUMAN_AUTHORIZATION,
            passed=not vetoes,
            reason=(
                "A0 automatic: machine policy records the decision (report 14.5); "
                "no human signature required"
                if not vetoes
                else "A0 automatic promotion vetoed: " + "; ".join(vetoes)
            ),
            detail={
                "required_tier": required_tier.value,
                "accepted_approval_ids": [],
                "rejected": vetoes,
            },
        )
    accepted: list[str] = []
    rejected: list[str] = []
    for approval in approvals:
        if approval.decision != "approved":
            rejected.append(f"{approval.approval_id}: decision is {approval.decision!r}")
        elif approval.candidate_bundle_id != candidate.bundle_id:
            rejected.append(f"{approval.approval_id}: approval binds a different candidate digest")
        elif not tier_meets(approval.tier, required_tier):
            rejected.append(
                f"{approval.approval_id}: tier {approval.tier.value} "
                f"below required {required_tier.value}"
            )
        elif approval.approver == proposal.proposer.id:
            rejected.append(
                f"{approval.approval_id}: self-approval forbidden "
                f"(approver {approval.approver!r} is the proposer)"
            )
        else:
            accepted.append(approval.approval_id)
    passed = bool(accepted)
    if passed:
        reason = f"{len(accepted)} qualifying approval(s) at tier >= {required_tier.value}"
    elif rejected:
        reason = "no qualifying approval: " + "; ".join(rejected)
    else:
        reason = "no approvals submitted"
    return GateResult(
        gate=GateId.G8_HUMAN_AUTHORIZATION,
        passed=passed,
        reason=reason,
        detail={
            "required_tier": required_tier.value,
            "accepted_approval_ids": accepted,
            "rejected": rejected,
        },
    )


def g9_canary(monitoring_window_missions: int = 50) -> GateResult:
    """G9 -- canary and monitoring: Stage-1 stub (deployment controller owns it)."""
    return GateResult(
        gate=GateId.G9_CANARY_MONITORING,
        passed=True,
        reason="canary deferred to deployment controller; monitoring window recorded",
        detail={"monitoring_window_missions": monitoring_window_missions},
    )
