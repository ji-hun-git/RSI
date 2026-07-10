"""MemoryItem (report sections 11.2, 17.4) and ContextPackage (11.4).

Stage 1 ships the contracts and staging semantics only; governed
extraction/consolidation pipelines are Stage 2 work. The critical
invariant is already enforced here by typing: a memory item without
``source_refs`` must be explicitly labeled as a hypothesis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._util import new_id, utcnow
from .enums import MemoryType, SecurityClass, VerificationStatus


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_ref: str
    locator: str | None = None  # e.g. "p.12", "line 40-60"


class Confidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float = 0.5
    method: str = "unspecified"


class MemoryLink(BaseModel):
    """Directed supporting/contradicting evidence link (report 11.2).

    Carries the extraction method and a span/locator so the link can be
    audited back to the exact evidence region, not just a bare reference.
    """

    model_config = ConfigDict(frozen=True)

    target_ref: str
    method: str = "unspecified"  # extraction method, e.g. "verbatim", "llm-extraction"
    locator: str | None = None  # span/locator inside the target, e.g. "line 40-60"


class MemoryItem(BaseModel):
    """Universal memory item (report 11.2).

    ``created_at`` is the record time and ``observed_at`` the event time;
    the two are kept distinct by contract. ``read_scope``/``write_scope``
    carry the per-item project/role/capability requirements evaluated by
    the 11.4 retrieval filters, and ``quality_evidence`` accumulates
    retrieval-usefulness and harmful-use observations.
    """

    model_config = ConfigDict(frozen=True)

    memory_id: str = Field(default_factory=lambda: new_id("mem"))
    memory_type: MemoryType
    content: dict[str, Any] = Field(default_factory=dict)
    is_hypothesis: bool = False
    source_refs: list[SourceRef] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)  # record time
    observed_at: datetime = Field(default_factory=utcnow)  # event time
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: Confidence = Field(default_factory=Confidence)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    supporting_refs: list[MemoryLink] = Field(default_factory=list)
    contradicting_refs: list[MemoryLink] = Field(default_factory=list)
    read_scope: list[str] = Field(default_factory=list)  # projects/roles/capabilities
    write_scope: list[str] = Field(default_factory=list)
    quality_evidence: dict[str, Any] = Field(default_factory=dict)
    applicability: dict[str, list[str]] = Field(default_factory=dict)
    security_class: SecurityClass = SecurityClass.INTERNAL
    author: str = "system"
    reviewer: str | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)
    expiration_policy: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_provenance(self) -> "MemoryItem":
        if not self.source_refs and not self.is_hypothesis:
            raise ValueError(
                "memory item has no source_refs; either provide provenance or "
                "mark it explicitly as a hypothesis (is_hypothesis=True)"
            )
        return self


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: str
    excerpt: str | None = None
    source: SourceRef | None = None
    confidence: Confidence | None = None


class ContextPackage(BaseModel):
    """The exact, cited, budgeted evidence set supplied to one module call."""

    model_config = ConfigDict(frozen=True)

    package_id: str = Field(default_factory=lambda: new_id("ctx"))
    version: str = "1.0.0"
    mission_id: str
    node_id: str
    information_need: dict[str, Any] = Field(default_factory=dict)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    procedures: list[str] = Field(default_factory=list)  # pinned skill/prompt versions
    warnings: list[str] = Field(default_factory=list)
    token_allocation: dict[str, int] = Field(default_factory=dict)
    retrieval_trace: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)
