"""Governance records: gate results, promotion decisions, approvals,
deployments, rollbacks and capability tokens (report sections 13, 14).

The separation of four powers is encoded structurally: proposals
(improvement.py) carry no authority; gate results are evidence;
PromotionDecision is produced only by the deterministic gate; approvals
are human records referencing the *exact* candidate digest.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._util import new_id, utcnow
from .enums import ApprovalTier, DecisionAction, GateId


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    gate: GateId
    passed: bool
    reason: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


class ApprovalRecord(BaseModel):
    """A human approval binds an identity to an exact candidate digest and scope."""

    model_config = ConfigDict(frozen=True)

    approval_id: str = Field(default_factory=lambda: new_id("appr"))
    approver: str  # e.g. "human:owner"
    tier: ApprovalTier
    candidate_bundle_id: str
    scope: dict[str, Any] = Field(default_factory=dict)
    decision: str = "approved"  # approved | rejected
    rationale: str = ""
    approved_at: datetime = Field(default_factory=utcnow)


class PromotionDecision(BaseModel):
    """Produced only by the deterministic promotion gate (report 13.3).

    ``signer``/``signature`` bind the decision to the gate that produced
    it: the gate signs the canonical JSON of :meth:`signable_payload`, so
    a hand-built or field-tampered decision cannot pass the deployment
    trust boundary. ``proposer`` records the proposing principal so the
    no-self-approval rule (report 8.1) is enforceable at deploy time.
    """

    model_config = ConfigDict(frozen=True)

    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    proposal_id: str | None = None
    experiment_id: str | None = None
    candidate_bundle_id: str
    parent_bundle_id: str
    action: DecisionAction
    required_approval_tier: ApprovalTier
    proposer: str | None = None  # proposing principal, e.g. "optimizer.gepa"
    gate_results: list[GateResult] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)  # approval_ids accepted by G8
    scope: dict[str, Any] = Field(default_factory=dict)
    rollback_target: str | None = None
    reason: str = ""
    decided_at: datetime = Field(default_factory=utcnow)
    signer: str | None = None
    signature: str | None = None

    def failed_gates(self) -> list[GateResult]:
        return [g for g in self.gate_results if not g.passed]

    def signable_payload(self) -> dict[str, Any]:
        """Canonical payload the producing gate signs (everything but the signature)."""
        return self.model_dump(mode="json", exclude={"signer", "signature"})


class DeploymentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    deployment_id: str = Field(default_factory=lambda: new_id("dep"))
    bundle_id: str
    parent_bundle_id: str | None = None
    decision_id: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    mode: str = "scoped_production"  # shadow | canary | scoped_production | general_production
    monitoring_window_missions: int = 50
    rollback_triggers: list[str] = Field(default_factory=list)
    activated_at: datetime = Field(default_factory=utcnow)
    active: bool = True


class RollbackRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    rollback_id: str = Field(default_factory=lambda: new_id("rbk"))
    from_bundle_id: str
    to_bundle_id: str
    trigger: str
    initiated_by: str = "system"
    rolled_back_at: datetime = Field(default_factory=utcnow)


class CapabilityToken(BaseModel):
    """Short-lived, scoped, non-transferable authorization grant (report 14)."""

    model_config = ConfigDict(frozen=True)

    capability_id: str = Field(default_factory=lambda: new_id("cap"))
    subject: str  # module or principal the grant is bound to
    mission_id: str | None = None
    actions: list[str] = Field(default_factory=list)  # e.g. ["tool.terminal.exec"]
    resource_scopes: list[str] = Field(default_factory=list)
    issued_at: datetime = Field(default_factory=utcnow)
    ttl_seconds: int = 900
    transferable: bool = False
    issuer: str = "capability-issuer"

    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(seconds=self.ttl_seconds)

    def is_valid(self, at: datetime | None = None, subject: str | None = None) -> bool:
        now = at or utcnow()
        if now >= self.expires_at():
            return False
        if subject is not None and subject != self.subject:
            # Tokens are non-transferable: presenting another subject's token fails.
            return False
        return True

    def allows(self, action: str, resource: str | None = None) -> bool:
        """Fail-closed scope check (least privilege, report 14).

        An empty ``resource_scopes`` grants no resource at all, and a
        scoped token denies any request that omits the resource: absence
        of scope information is never treated as universal permission.
        """
        if action not in self.actions:
            return False
        if resource is None:
            # Only a deliberately unscoped token may act without naming a resource.
            return not self.resource_scopes
        if not self.resource_scopes:
            return False
        return any(resource.startswith(scope) for scope in self.resource_scopes)
