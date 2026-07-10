"""EvaluationResult (report section 17.4) and the metric vector (13.2).

An evaluation result is a *claim about an observation*, distinct from the
observation itself (an event) and from the governed action taken on it
(a promotion decision). Evaluator identity and uncertainty are mandatory.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._util import content_digest, new_id, utcnow
from .events import ModuleRef


class Uncertainty(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str = "point"  # point | bootstrap_ci | stddev
    low: float | None = None
    high: float | None = None


class ResultIntegrity(BaseModel):
    """Integrity block of report 17.4: digest of the result plus signature.

    Evaluation records are decision evidence (report 17.5), so they carry
    their own tamper-evidence: ``digest`` covers every field except this
    block, ``signature`` is the producing evaluator's signature over it.
    """

    model_config = ConfigDict(frozen=True)

    digest: str
    signature: str | None = None
    signer: str | None = None


class EvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_id: str = Field(default_factory=lambda: new_id("eval"))
    subject_run_id: str
    subject_bundle_id: str | None = None
    evaluator: ModuleRef
    dataset_item_handle: str | None = None  # blind handle for protected items
    metric: str
    value: float
    uncertainty: Uncertainty = Field(default_factory=Uncertainty)
    subgroups: dict[str, float] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    judge_output_ref: str | None = None
    status: str = "valid"  # valid | invalid | disputed
    created_at: datetime = Field(default_factory=utcnow)
    detail: dict[str, Any] = Field(default_factory=dict)
    integrity: ResultIntegrity | None = None

    def digest(self) -> str:
        """Digest over everything except the integrity block (which contains it)."""
        return content_digest(self.model_dump(mode="json", exclude={"integrity"}))

    def with_integrity(self, integrity: ResultIntegrity) -> "EvaluationResult":
        return self.model_copy(update={"integrity": integrity})


class MetricVector(BaseModel):
    """Multi-objective outcome vector for one run or one arm (report 13.2).

    Hard-constraint dimensions (safety, retention, reproducibility, cost,
    latency) are checked before any preference optimization; a single
    weighted score is deliberately not provided.
    """

    model_config = ConfigDict(frozen=True)

    task_success: float | None = None
    factuality: float | None = None
    robustness: float | None = None
    generalization: float | None = None
    safety_critical_violations: int = 0
    capability_retention: float | None = None
    cost_usd: float = 0.0
    latency_p95_ms: float | None = None
    stability: float | None = None
    interpretability: float | None = None
    maintainability: float | None = None
    reproducibility: float | None = None
    subgroup_minima: dict[str, float] = Field(default_factory=dict)
    extra: dict[str, float] = Field(default_factory=dict)
