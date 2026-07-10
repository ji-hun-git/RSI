"""Deterministic, fail-closed Policy Decision Point (report 10.1, 14.5, Appendix B).

The PDP is a pure function of (action, subject, resource, context): no
clock, no randomness, no I/O. Anything it does not recognize -- unknown
action, unknown subject, malformed context -- is denied with reason
``fail_closed``. The Stage-1 mutation surface (report 8.4/19.1) permits
autonomy levels 1-2 only; the approval-tier ladder follows report 14.5
(Level 5 maps to A4: conventional SDLC only, never autonomous).
The protected holdout vault is readable by exactly one principal, the
experiment controller (report 14.1): candidates and proposers may never
see it, which is what keeps holdout evidence admissible.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from foundry.contracts import ApprovalTier, AutonomyLevel


class PolicyDecision(BaseModel):
    """The PDP's only output: permit/deny plus tier, reason and obligations."""

    model_config = ConfigDict(frozen=True)

    permit: bool
    approval_tier: ApprovalTier
    reason: str
    obligations: list[str] = Field(default_factory=list)


_LEVEL_1_SURFACE = ("/config/retrieval", "/memory_policy_ref")
_LEVEL_2_SURFACE = _LEVEL_1_SURFACE + (
    "/config/prompt",
    "/config/strategy",
    "/config/routing",
    "/module_refs",
)

#: Stage-1 mutation surface per autonomy level. Levels 3+ are deliberately
#: empty: topology, evaluator and code changes are not autonomously
#: forkable in Stage 1 (report 19.1) and always deny.
ALLOWED_MUTATIONS: dict[AutonomyLevel, list[str]] = {
    AutonomyLevel.OBSERVE_ONLY: [],
    AutonomyLevel.MEMORY_RETRIEVAL_TUNING: list(_LEVEL_1_SURFACE),
    AutonomyLevel.PROMPT_SKILL_ROUTING: list(_LEVEL_2_SURFACE),
    AutonomyLevel.WORKFLOW_TOPOLOGY: [],
    AutonomyLevel.EVALUATOR_POLICY: [],
    AutonomyLevel.CODE_TRAINING: [],
}

#: The single principal allowed to read the protected holdout vault (14.1).
HOLDOUT_READER = "experiment-controller"

DEFAULT_KNOWN_SUBJECTS: frozenset[str] = frozenset(
    {
        "experiment-controller",
        "optimizer.gepa",
        "agent.builder",
        "human:owner",
        "promotion-gate",
    }
)

KNOWN_ACTIONS: frozenset[str] = frozenset({"bundle.fork", "bundle.promote", "holdout.read"})

_TIER_RANK: dict[ApprovalTier, int] = {
    ApprovalTier.A0_AUTOMATIC: 0,
    ApprovalTier.A1_SINGLE_REVIEWER: 1,
    ApprovalTier.A2_DUAL_CONTROL: 2,
    ApprovalTier.A3_GOVERNANCE_COMMITTEE: 3,
    ApprovalTier.A4_CONVENTIONAL_SDLC: 4,
}


def required_approval_tier(level: AutonomyLevel) -> ApprovalTier:
    """Report 14.5 ladder: 5 -> A4, 4 -> A3, 3 -> A2, 2 -> A1, <=1 -> A0.

    Level 5 (code/training changes) maps to A4 -- conventional SDLC only,
    no autonomous promotion path (report 8.4, 14.5) -- never to A3.
    """
    if level >= AutonomyLevel.CODE_TRAINING:
        return ApprovalTier.A4_CONVENTIONAL_SDLC
    if level == AutonomyLevel.EVALUATOR_POLICY:
        return ApprovalTier.A3_GOVERNANCE_COMMITTEE
    if level == AutonomyLevel.WORKFLOW_TOPOLOGY:
        return ApprovalTier.A2_DUAL_CONTROL
    if level == AutonomyLevel.PROMPT_SKILL_ROUTING:
        return ApprovalTier.A1_SINGLE_REVIEWER
    return ApprovalTier.A0_AUTOMATIC


def _path_within(path: str, prefix: str) -> bool:
    if path == prefix:
        return True
    return path.startswith(prefix if prefix.endswith("/") else prefix + "/")


def _coerce_level(value: Any) -> AutonomyLevel | None:
    try:
        return AutonomyLevel(value)
    except ValueError:
        return None


def _coerce_tier(value: Any) -> ApprovalTier | None:
    try:
        return ApprovalTier(value)
    except ValueError:
        return None


def _deny(reason: str, tier: ApprovalTier = ApprovalTier.A4_CONVENTIONAL_SDLC) -> PolicyDecision:
    return PolicyDecision(permit=False, approval_tier=tier, reason=reason)


class PolicyDecisionPoint:
    """Deterministic permit/deny authority over governance-relevant actions.

    Sits outside the self-modification boundary (report 14.1): candidates
    can neither edit the mutation surface nor widen the subject list.
    """

    def __init__(self, known_subjects: Iterable[str] | None = None) -> None:
        self.known_subjects: frozenset[str] = (
            frozenset(known_subjects) if known_subjects is not None else DEFAULT_KNOWN_SUBJECTS
        )

    def decide(
        self, action: str, subject: str, resource: str, context: dict[str, Any]
    ) -> PolicyDecision:
        if action not in KNOWN_ACTIONS or subject not in self.known_subjects:
            return _deny("fail_closed")
        if action == "holdout.read":
            return self._decide_holdout_read(subject)
        if action == "bundle.fork":
            return self._decide_fork(context)
        return self._decide_promote(context)

    def _decide_holdout_read(self, subject: str) -> PolicyDecision:
        if subject != HOLDOUT_READER:
            return _deny("holdout_vault_reader_restricted")
        return PolicyDecision(
            permit=True,
            approval_tier=ApprovalTier.A0_AUTOMATIC,
            reason="experiment_controller_vault_access",
            obligations=["emit_leakage_audit_event"],
        )

    def _decide_fork(self, context: dict[str, Any]) -> PolicyDecision:
        level = _coerce_level(context.get("autonomy_level"))
        field_paths = context.get("field_paths")
        if (
            level is None
            or not isinstance(field_paths, list)
            or not field_paths
            or not all(isinstance(path, str) for path in field_paths)
        ):
            return _deny("fail_closed")
        surface = ALLOWED_MUTATIONS[level]
        if not surface:
            return _deny(f"autonomy_level_{int(level)}_has_no_stage1_mutation_surface")
        tier = required_approval_tier(level)
        for path in field_paths:
            if not any(_path_within(path, prefix) for prefix in surface):
                return _deny(f"field_path_outside_mutation_surface:{path}", tier=tier)
        return PolicyDecision(
            permit=True,
            approval_tier=tier,
            reason="within_stage1_mutation_surface",
            obligations=["register_child_bundle", "run_promotion_gates"],
        )

    def _decide_promote(self, context: dict[str, Any]) -> PolicyDecision:
        level = _coerce_level(context.get("autonomy_level"))
        tier = _coerce_tier(context.get("approval_tier"))
        if level is None or tier is None:
            return _deny("fail_closed")
        required = required_approval_tier(level)
        if required is ApprovalTier.A4_CONVENTIONAL_SDLC:
            # Report 14.5: A4 changes go through conventional SDLC only;
            # there is no autonomous promotion path whatever tier is asserted.
            return _deny("conventional_sdlc_only_no_autonomous_promotion", tier=required)
        if context.get("gates_passed") is not True:
            return _deny("gates_not_passed", tier=required)
        if _TIER_RANK[tier] < _TIER_RANK[required]:
            return _deny(f"approval_tier_below_required:{required.value}", tier=required)
        return PolicyDecision(
            permit=True,
            approval_tier=required,
            reason="gates_passed_and_tier_met",
            obligations=["start_canary_monitoring", "record_rollback_target"],
        )
