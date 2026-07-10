"""ImprovementProposal and ExperimentRecord (report sections 12.3, 17.4).

A proposal is a falsifiable object: one primary causal hypothesis, a typed
diff, expected effects, risks, an experiment plan and an executable
rollback condition. A proposal without an experiment plan cannot enter
the promotion pipeline (gate G0 rejects it).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._util import new_id, utcnow
from .bundle import FieldChange
from .enums import AutonomyLevel, TaskSetRole
from .events import ModuleRef


class ChangeTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    module_id: str | None = None
    field_path: str  # path inside the SystemBundle identity payload


class DeploymentScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_types: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    percent: float = 100.0


class ImprovementProposal(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: str = Field(default_factory=lambda: new_id("prop"))
    parent_bundle_id: str
    target: ChangeTarget
    current_behavior: str = ""
    hypothesis: str
    secondary_hypotheses: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    changes: list[FieldChange] = Field(default_factory=list)
    expected_effects: dict[str, float] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    autonomy_level: AutonomyLevel = AutonomyLevel.PROMPT_SKILL_ROUTING
    deployment_scope: DeploymentScope = Field(default_factory=DeploymentScope)
    experiment_plan_ref: str | None = None
    # Pre-registered capability-retention set and regression thresholds
    # (report 12.3, 13.4): the proposer commits to these before any
    # protected result is opened; the gate reads them from here, never
    # from gate-time caller arguments.
    retention_set_ref: str | None = None
    minimum_practical_effect: float = 0.0
    retention_floor: float = 0.0
    subgroup_floors: dict[str, float] = Field(default_factory=dict)
    rollback_condition: str = ""
    proposer: ModuleRef = Field(default_factory=lambda: ModuleRef(id="human:owner"))
    created_at: datetime = Field(default_factory=utcnow)


class ExperimentArm(BaseModel):
    model_config = ConfigDict(frozen=True)

    arm_id: str  # "control" | "candidate_a" | ...
    bundle_id: str
    is_control: bool = False


class TaskSetRefs(BaseModel):
    model_config = ConfigDict(frozen=True)

    development: str | None = None
    protected: str | None = None
    retention: str | None = None
    adversarial: str | None = None

    def ref_for(self, role: TaskSetRole) -> str | None:
        return {
            TaskSetRole.DEVELOPMENT: self.development,
            TaskSetRole.PROTECTED_HOLDOUT: self.protected,
            TaskSetRole.RETENTION: self.retention,
            TaskSetRole.ADVERSARIAL: self.adversarial,
        }[role]


class Randomization(BaseModel):
    model_config = ConfigDict(frozen=True)

    unit: str = "task"
    paired: bool = True
    seed: int = 0


class ExperimentBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    per_arm_cost_usd: float = 100.0
    max_runs: int = 200
    equalized: bool = True


class ExperimentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: str = Field(default_factory=lambda: new_id("exp"))
    protocol_version: str = "1.0.0"
    proposal_id: str | None = None
    preregistration_ref: str | None = None
    arms: list[ExperimentArm] = Field(default_factory=list)
    task_sets: TaskSetRefs = Field(default_factory=TaskSetRefs)
    randomization: Randomization = Field(default_factory=Randomization)
    budgets: ExperimentBudget = Field(default_factory=ExperimentBudget)
    primary_endpoint: str = "paired_task_success_delta"
    minimum_practical_effect: float = 0.0
    decision_rule_ref: str = "policy://promotion/stage1-v1"
    status: str = "designed"  # designed | running | completed | stopped
    analysis_ref: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class PairedAnalysis(BaseModel):
    """Result of a paired candidate-vs-control comparison on one task set."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    arm_id: str
    task_set_role: TaskSetRole
    n_pairs: int
    mean_delta: float
    ci_low: float
    ci_high: float
    wins: int
    losses: int
    ties: int
    per_task_deltas: dict[str, float] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)
