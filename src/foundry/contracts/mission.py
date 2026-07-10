"""MissionSpec (report section 17.4) and its component parts.

A MissionSpec is immutable once compiled: the mission runs under exactly
one frozen SystemBundle and one frozen set of objectives, constraints and
acceptance criteria. Re-scoping a mission means compiling a new spec.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._util import new_id, utcnow
from .enums import OperatingProfile, RiskClass


class Objective(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    priority: str = "must"  # must | should | could


class Constraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str  # e.g. security, budget, style
    rule_ref: str | None = None
    text: str | None = None


class AcceptanceCriterion(BaseModel):
    """An acceptance criterion names a deterministic oracle where possible."""

    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    oracle: str | None = None  # e.g. "test://fixtures/task-01"


class ResourceBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_cost_usd: float = 10.0
    max_wall_seconds: int = 3600
    max_tool_calls: int = 200
    max_output_tokens: int = 50_000


class MissionSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    mission_id: str = Field(default_factory=lambda: new_id("mis"))
    project_id: str = "proj_default"
    request_ref: str | None = None
    task_type: str = "software.fixture"
    objectives: list[Objective] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    risk_class: RiskClass = RiskClass.LOW
    operating_profile: OperatingProfile = OperatingProfile.RESEARCH
    system_bundle_id: str
    resource_budget: ResourceBudget = Field(default_factory=ResourceBudget)
    human_checkpoints: list[str] = Field(default_factory=list)
    data_policy_ref: str = "policy://retention/project-default/v1"
    created_at: datetime = Field(default_factory=utcnow)
    inputs: dict[str, Any] = Field(default_factory=dict)


class MissionRequest(BaseModel):
    """The raw, pre-compilation human request. Mutable field bag by design."""

    request_id: str = Field(default_factory=lambda: new_id("req"))
    project_id: str = "proj_default"
    task_type: str = "software.fixture"
    description: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    risk_class: RiskClass = RiskClass.LOW
    operating_profile: OperatingProfile = OperatingProfile.RESEARCH
    requested_by: str = "human:owner"
