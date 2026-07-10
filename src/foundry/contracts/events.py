"""Canonical event envelope (report section 15.1) and event families (15.2).

Events are the foundry's evidence root. They are append-only: a correction
is a new event, never an in-place edit. The ``integrity`` block is filled by
the ledger at append time (producer, payload digest, hash chain, sequence).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._util import content_digest, new_id, utcnow
from .enums import SecurityClass

SCHEMA_VERSION = "1.0.0"


class ModuleRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    version: str = "0.0.0"
    digest: str | None = None


class ModelRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    endpoint_policy: str | None = None
    sampling: dict[str, Any] = Field(default_factory=dict)


class ToolRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_id: str
    version: str | None = None
    request_digest: str | None = None
    side_effect_class: str = "none"


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    wall_ms: int = 0
    retries: int = 0


class Integrity(BaseModel):
    """Filled in by the ledger; producer signature over the event digest."""

    model_config = ConfigDict(frozen=True)

    producer: str
    digest: str
    prev_digest: str | None = None
    sequence: int
    signature: str | None = None


class Event(BaseModel):
    """Canonical event envelope. Immutable once constructed."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: new_id("evt"))
    event_type: str
    schema_version: str = SCHEMA_VERSION
    occurred_at: datetime = Field(default_factory=utcnow)
    recorded_at: datetime | None = None

    mission_id: str | None = None
    run_id: str | None = None
    node_id: str | None = None
    experiment_id: str | None = None
    arm_id: str | None = None
    system_bundle_id: str | None = None

    module: ModuleRef | None = None
    actor: str = "system"
    subject: str | None = None
    project_id: str | None = None

    parent_event_ids: list[str] = Field(default_factory=list)
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)

    capability_ref: str | None = None
    model_ref: ModelRef | None = None
    tool_ref: ToolRef | None = None
    usage: Usage = Field(default_factory=Usage)

    security_class: SecurityClass = SecurityClass.INTERNAL
    retention: str = "project-default"

    integrity: Integrity | None = None

    def payload_digest(self) -> str:
        """Digest over everything except the integrity block (which contains it)."""
        return content_digest(self.model_dump(mode="json", exclude={"integrity", "recorded_at"}))

    def with_integrity(self, integrity: Integrity, recorded_at: datetime) -> "Event":
        return self.model_copy(update={"integrity": integrity, "recorded_at": recorded_at})


class EventTypes:
    """Required event families (report section 15.2). Names are stable strings."""

    # Mission
    MISSION_REQUESTED = "mission.requested"
    MISSION_ACCEPTED = "mission.accepted"
    MISSION_REJECTED = "mission.rejected"
    MISSION_COMPILED = "mission.compiled"
    MISSION_STARTED = "mission.started"
    MISSION_SUSPENDED = "mission.suspended"
    MISSION_RESUMED = "mission.resumed"
    MISSION_COMPLETED = "mission.completed"
    MISSION_FAILED = "mission.failed"
    MISSION_CANCELLED = "mission.cancelled"

    # Workflow
    NODE_READY = "workflow.node_ready"
    NODE_STARTED = "workflow.node_started"
    NODE_COMPLETED = "workflow.node_completed"
    NODE_FAILED = "workflow.node_failed"
    STATE_UPDATED = "workflow.state_updated"
    HANDOFF = "workflow.handoff"
    RETRY = "workflow.retry"
    TIMEOUT = "workflow.timeout"
    CHECKPOINT = "workflow.checkpoint"
    DUPLICATE_SUPPRESSED = "workflow.duplicate_suppressed"

    # Model
    MODEL_REQUEST = "model.request"
    MODEL_RESPONSE = "model.response"
    MODEL_VALIDATION_FAILED = "model.validation_failed"
    MODEL_FALLBACK = "model.fallback"
    MODEL_REFUSAL = "model.refusal"
    MODEL_USAGE = "model.usage"

    # Tool
    TOOL_DISCOVERED = "tool.discovered"
    TOOL_AUTHORIZED = "tool.authorized"
    TOOL_DENIED = "tool.denied"
    TOOL_CALLED = "tool.call.started"
    TOOL_RESULT = "tool.call.completed"
    TOOL_SIDE_EFFECT = "tool.side_effect_receipt"
    TOOL_ROLLBACK = "tool.rollback"

    # Memory
    MEMORY_QUERY = "memory.query"
    MEMORY_RETRIEVED = "memory.item_retrieved"
    MEMORY_SHOWN = "memory.item_shown"
    MEMORY_CANDIDATE_WRITTEN = "memory.candidate_written"
    MEMORY_PROMOTED = "memory.promoted"
    MEMORY_CONTRADICTED = "memory.contradicted"
    MEMORY_REVIEWED = "memory.reviewed"
    MEMORY_EXPIRED = "memory.expired"

    # Artifact
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_MODIFIED = "artifact.modified"
    ARTIFACT_TESTED = "artifact.tested"
    ARTIFACT_SIGNED = "artifact.signed"
    ARTIFACT_EXPORTED = "artifact.exported"
    ARTIFACT_DELETED = "artifact.deleted"

    # Evaluation
    EVALUATION_SCHEDULED = "evaluation.scheduled"
    METRIC_COMPUTED = "evaluation.metric_computed"
    JUDGE_RESULT = "evaluation.judge_result"
    EVALUATOR_DISAGREEMENT = "evaluation.disagreement"
    HUMAN_ANNOTATION = "evaluation.human_annotation"
    EVALUATION_CALIBRATION = "evaluation.calibration"

    # Experiment
    EXPERIMENT_DESIGNED = "experiment.designed"
    EXPERIMENT_RANDOMIZED = "experiment.randomized"
    ARM_STARTED = "experiment.arm_started"
    ARM_COMPLETED = "experiment.arm_completed"
    LEAKAGE_DETECTED = "experiment.leakage_detected"
    EXPERIMENT_STOPPED = "experiment.stopped"
    EXPERIMENT_ANALYZED = "experiment.analyzed"

    # Governance
    PROPOSAL_SUBMITTED = "governance.proposal_submitted"
    APPROVAL_REQUESTED = "governance.approval_requested"
    GOVERNANCE_DECISION = "governance.decision"
    POLICY_DENIAL = "governance.policy_denial"
    CANARY_STARTED = "governance.canary"
    PROMOTION = "governance.promotion"
    ROLLBACK = "governance.rollback"
    INCIDENT = "governance.incident"

    # Resource
    BUDGET_RESERVED = "resource.budget_reserved"
    BUDGET_WARNING = "resource.budget_warning"
    BUDGET_EXHAUSTED = "resource.budget_exhausted"
    RESOURCE_QUOTA_VIOLATION = "resource.quota_violation"
