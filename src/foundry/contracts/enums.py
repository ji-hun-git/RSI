"""Closed vocabularies used across the foundry contracts.

These enums encode governance semantics from the technical report:
autonomy levels (report section 8.4), approval tiers (14.5), promotion
statuses (13.6), gate identifiers (13.1) and memory typing (11.1/11.2).
"""

from __future__ import annotations

from enum import Enum


class RiskClass(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class OperatingProfile(str, Enum):
    """Deployment profiles (report section 9.5)."""

    RESEARCH = "research"
    HIGH_RELIABILITY = "high_reliability"
    LOW_COST = "low_cost"
    FAST_RESPONSE = "fast_response"
    EXPERIMENTAL = "experimental"


class SecurityClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    SECRET_REFERENCE_ONLY = "secret_reference_only"


class AutonomyLevel(int, Enum):
    """Mutable-surface levels (report section 8.4). Stage 1 permits 0-2."""

    OBSERVE_ONLY = 0
    MEMORY_RETRIEVAL_TUNING = 1
    PROMPT_SKILL_ROUTING = 2
    WORKFLOW_TOPOLOGY = 3
    EVALUATOR_POLICY = 4
    CODE_TRAINING = 5


class ApprovalTier(str, Enum):
    """Human approval tiers (report section 14.5)."""

    A0_AUTOMATIC = "A0"
    A1_SINGLE_REVIEWER = "A1"
    A2_DUAL_CONTROL = "A2"
    A3_GOVERNANCE_COMMITTEE = "A3"
    A4_CONVENTIONAL_SDLC = "A4"


class PromotionStatus(str, Enum):
    """Module/bundle lifecycle statuses (report section 13.6)."""

    DRAFT = "draft"
    QUARANTINED = "quarantined"
    EXPERIMENTAL = "experimental"
    SHADOW = "shadow"
    CANARY = "canary"
    SCOPED_PRODUCTION = "scoped_production"
    GENERAL_PRODUCTION = "general_production"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class DecisionAction(str, Enum):
    """Terminal actions of the promotion gate (report sections 12.2, 13.1)."""

    REJECT = "reject"
    QUARANTINE = "quarantine"
    RETEST = "retest"
    CANARY = "canary"
    PROMOTE = "promote"


class GateId(str, Enum):
    """Promotion gate sequence (report section 13.1)."""

    G0_INTEGRITY_AND_SCOPE = "G0"
    G1_STATIC_CHECKS = "G1"
    G2_DEVELOPMENT_REPLAY = "G2"
    G3_PROTECTED_HOLDOUT = "G3"
    G4_CAPABILITY_RETENTION = "G4"
    G5_ADVERSARIAL_SAFETY = "G5"
    G6_RESOURCE_MAINTAINABILITY = "G6"
    G7_REPRODUCIBILITY = "G7"
    G8_HUMAN_AUTHORIZATION = "G8"
    G9_CANARY_MONITORING = "G9"


class MissionState(str, Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPILED = "compiled"
    STARTED = "started"
    SUSPENDED = "suspended"
    RESUMED = "resumed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MemoryType(str, Enum):
    """Typed memory layers (report section 11.1)."""

    SOURCE = "source"
    EPISODE = "episode"
    SEMANTIC_CLAIM = "semantic_claim"
    PROCEDURE = "procedure"
    EVALUATION = "evaluation"
    NEGATIVE = "negative"
    GOVERNANCE = "governance"


class VerificationStatus(str, Enum):
    """Memory verification statuses (report section 11.2)."""

    UNVERIFIED = "unverified"
    CORROBORATED = "corroborated"
    CONTRADICTED = "contradicted"
    HUMAN_CONFIRMED = "human_confirmed"
    EXPERIMENTALLY_SUPPORTED = "experimentally_supported"
    DEPRECATED = "deprecated"


class ModuleType(str, Enum):
    AGENT = "agent"
    TOOL = "tool"
    SKILL = "skill"
    EVALUATOR = "evaluator"
    WORKFLOW = "workflow"
    SERVICE = "service"


class TaskSetRole(str, Enum):
    """Task-set roles inside an experiment (report section 17.4)."""

    DEVELOPMENT = "development"
    PROTECTED_HOLDOUT = "protected"
    RETENTION = "retention"
    ADVERSARIAL = "adversarial"
