"""Typed projection model for the foundry dashboard (report section 15.3).

The dashboard is a read-only *skin over canonical data* (report 15.4): these
frozen structures are the exact evidence each view renders, computed by
:mod:`foundry.dashboard.project` from a ledger and a bundle registry and
consumed by :mod:`foundry.dashboard.render`. Keeping the projection and the
presentation separate means the HTML can never introduce a fact the evidence
does not contain, and the model can be asserted on directly in tests.

Design constraints carried in the field set (report 15.4 "useful transparency
versus decorative visualization"):

* uncertainty is never dropped -- every experiment role analysis keeps its
  confidence interval, not only the point estimate;
* failed and rejected branches are first-class -- quarantined candidates and
  rolled-back deployments are modelled, not omitted;
* the exact diff and every gate result travel with each governance decision,
  so a viewer is never asked to trust an approval without seeing them;
* identity is exact -- bundles, modules and artifacts are referenced by their
  content digests, never by a friendly name alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NodeStep:
    """One workflow node transition in a mission timeline."""

    node_id: str
    status: str  # "completed" | "failed" | "suppressed" | "started"
    output_digest: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MissionView:
    mission_id: str
    run_id: str | None
    status: str
    bundle_id: str | None
    input_text: str | None
    final_output: str | None
    output_digest: str | None
    timeline: tuple[NodeStep, ...] = ()
    artifact_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangeView:
    field_path: str
    old_value: Any
    new_value: Any


@dataclass(frozen=True)
class ProposalView:
    proposal_id: str
    hypothesis: str
    current_behavior: str
    changes: tuple[ChangeView, ...]
    autonomy_level: int
    minimum_practical_effect: float
    retention_floor: float
    retention_set_ref: str
    rollback_condition: str
    experiment_plan_ref: str | None
    proposer: str
    evidence_refs: tuple[str, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True)
class GateResultView:
    gate: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class DecisionView:
    decision_id: str
    action: str
    proposal_id: str | None
    experiment_id: str | None
    candidate_bundle_id: str
    parent_bundle_id: str
    required_tier: str
    reason: str
    signed: bool
    gate_results: tuple[GateResultView, ...]
    approvals: tuple[str, ...]
    rollback_target: str | None
    # Authoritative diff computed from the registry (parent vs candidate),
    # so a decision always shows its exact change even if the proposal link
    # is absent (report 15.4: never approve without the diff). ``diff_source``
    # is "registry", "proposal" or "unavailable".
    changes: tuple[ChangeView, ...] = ()
    diff_source: str = "unavailable"


@dataclass(frozen=True)
class RoleAnalysisView:
    arm_id: str
    role: str
    n_pairs: int
    mean_delta: float
    ci_low: float | None  # None when the analysis carried no (or a malformed) interval
    ci_high: float | None
    wins: int
    losses: int
    ties: int

    @property
    def ci_available(self) -> bool:
        return self.ci_low is not None and self.ci_high is not None


@dataclass(frozen=True)
class ArmView:
    arm_id: str
    bundle_id: str
    is_control: bool


@dataclass(frozen=True)
class ExperimentView:
    experiment_id: str
    seed: int | None
    minimum_practical_effect: float | None
    arms: tuple[ArmView, ...]
    analyses: tuple[RoleAnalysisView, ...]  # candidate-vs-control, per role
    leakage_hits: int
    decision_ids: tuple[str, ...]


@dataclass(frozen=True)
class BundleNode:
    bundle_id: str
    semantic_version: str
    registry_status: str
    parent_bundle_id: str | None
    config: dict[str, Any]
    is_active: bool
    lifecycle: str  # "active" | "promoted" | "canaried" | "rolled_back" | "quarantined" | "registered"
    children: tuple[BundleNode, ...] = ()


@dataclass(frozen=True)
class DeploymentStep:
    kind: str  # "canary" | "promotion" | "rollback"
    bundle_id: str
    from_bundle_id: str | None
    to_bundle_id: str | None
    decision_id: str | None
    trigger: str | None
    sequence: int


@dataclass(frozen=True)
class Incident:
    kind: str  # "chain_error" | "policy_denial" | "leakage" | "rollback" | "node_failed" | "quarantine"
    summary: str
    event_id: str | None
    sequence: int | None


@dataclass(frozen=True)
class ResourceTotals:
    events: int
    missions: int
    experiments: int
    decisions: int
    bundles: int
    artifacts: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    wall_ms: int


@dataclass(frozen=True)
class EvidenceContext:
    """Exactly which evidence snapshot this dashboard reflects (report 15.4:
    "exact version and dependency identity"). Two renders of the same ledger
    share a tip digest; a changed dashboard means changed evidence."""

    event_count: int
    tip_digest: str | None
    chain_ok: bool
    chain_errors: tuple[str, ...]


@dataclass(frozen=True)
class DashboardModel:
    root_name: str
    evidence: EvidenceContext
    active_bundle_id: str | None
    missions: tuple[MissionView, ...] = ()
    proposals: tuple[ProposalView, ...] = ()
    experiments: tuple[ExperimentView, ...] = ()
    decisions: tuple[DecisionView, ...] = ()
    bundle_roots: tuple[BundleNode, ...] = ()
    deployment_timeline: tuple[DeploymentStep, ...] = ()
    incidents: tuple[Incident, ...] = ()
    resources: ResourceTotals = field(
        default_factory=lambda: ResourceTotals(0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0)
    )
