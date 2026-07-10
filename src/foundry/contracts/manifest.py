"""Universal module manifest (report section 17.2 and Appendix A).

The manifest replaces the informal "agent genome": a module is admitted
by manifest, schemas, permissions, budgets, conformance evidence and
signatures -- never by persona description alone. Stage 1 implements a
pragmatic subset of Appendix A; unknown extensions live in ``extra``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._util import content_digest, utcnow
from .enums import ModuleType, PromotionStatus, RiskClass, SecurityClass


class PermissionSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    filesystem_read: list[str] = Field(default_factory=lambda: ["workspace"])
    filesystem_write: list[str] = Field(default_factory=lambda: ["workspace"])
    network_mode: str = "deny_by_default"
    network_allow: list[str] = Field(default_factory=list)
    secret_classes: list[str] = Field(default_factory=list)
    external_side_effects: bool = False
    permission_inheritance: str = "narrower_only"


class ResourceProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_output_tokens: int = 24_000
    max_cost_usd: float = 8.0
    max_wall_seconds: int = 1800
    max_tool_calls: int = 120
    max_iterations: int = 40
    max_parallelism: int = 1


class RetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_attempts: int = 2
    retryable_errors: list[str] = Field(default_factory=lambda: ["transient_model", "transient_tool"])


class ModuleManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Identity
    module_id: str
    module_type: ModuleType
    version: str = "0.1.0"
    publisher: str = "org.local.foundry"
    license: str = "MIT"
    created_at: datetime = Field(default_factory=utcnow)
    status: PromotionStatus = PromotionStatus.EXPERIMENTAL
    parent_version: str | None = None
    rollback_target: str | None = None

    # Purpose
    purpose: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    non_responsibilities: list[str] = Field(default_factory=list)
    task_tags: list[str] = Field(default_factory=list)
    risk_class: RiskClass = RiskClass.LOW

    # Interfaces
    input_schema_ref: str | None = None
    output_schema_ref: str | None = None
    error_schema_ref: str | None = None
    event_schema_ref: str | None = None
    streaming: bool = False
    idempotency_key_fields: list[str] = Field(default_factory=lambda: ["mission_id", "node_id", "attempt"])

    # Capabilities and resources
    allowed_tools: list[str] = Field(default_factory=list)
    permissions: PermissionSpec = Field(default_factory=PermissionSpec)
    memory_read_scope: list[str] = Field(default_factory=list)
    memory_write_scope: list[str] = Field(default_factory=lambda: ["working", "episodic_candidate"])
    resource_budget: ResourceProfile = Field(default_factory=ResourceProfile)

    # Reliability and safety
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    cancellation_supported: bool = True
    safety_constraints: list[str] = Field(default_factory=list)
    known_failure_modes: list[str] = Field(default_factory=list)
    data_classes: list[SecurityClass] = Field(default_factory=lambda: [SecurityClass.INTERNAL])
    sandbox_profile: str = "sandbox://local/none"

    # Quality and dependencies
    quality_metrics: list[str] = Field(default_factory=list)
    acceptance_floors: dict[str, float] = Field(default_factory=dict)
    conformance_suite: list[str] = Field(default_factory=list)
    module_dependencies: list[str] = Field(default_factory=list)
    environment_ref: str = "env://local/python"

    # Provenance
    source_repo: str | None = None
    commit: str | None = None
    sbom_ref: str | None = None
    signatures: list[str] = Field(default_factory=list)

    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.module_id}@{self.version}"

    def digest(self) -> str:
        return content_digest(self.model_dump(mode="json", exclude={"signatures"}))
