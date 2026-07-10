"""SystemBundle: the content-addressed unit of system identity (report 9.1).

The bundle is the "mutable genome" of the agent system: every mission runs
under exactly one signed, frozen bundle, and every improvement is a typed
diff that produces a child bundle. A run that cannot resolve its exact
bundle is not admissible evidence for promotion.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._util import content_digest, utcnow
from .enums import PromotionStatus


class SignatureRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    signer: str
    role: str = "author"  # author | reviewer | policy
    algorithm: str = "hmac-sha256"
    signature: str
    signed_at: datetime = Field(default_factory=utcnow)


class SystemBundle(BaseModel):
    """Complete frozen configuration of the behavior under test.

    ``bundle_id`` is derived from the canonical JSON of every identity
    field (everything except ``bundle_id``, ``signature_set``, ``status``
    and ``created_at``). Two bundles with equal content share an id.
    """

    model_config = ConfigDict(frozen=True)

    bundle_id: str = ""
    semantic_version: str = "0.1.0"
    parent_bundle_id: str | None = None

    workflow_ref: str
    module_refs: dict[str, str] = Field(default_factory=dict)  # slot -> module@version
    model_policy_ref: str = "model-policy://none/deterministic"
    memory_policy_ref: str = "memory-policy://default/v1"
    evaluation_profile_ref: str = "eval-profile://default/v1"
    resource_profile_ref: str = "resource-profile://research/v1"
    environment_ref: str = "env://local/python"
    config: dict[str, Any] = Field(default_factory=dict)

    status: PromotionStatus = PromotionStatus.DRAFT
    created_at: datetime = Field(default_factory=utcnow)
    signature_set: list[SignatureRecord] = Field(default_factory=list)

    IDENTITY_EXCLUDE: ClassVar[frozenset[str]] = frozenset(
        {"bundle_id", "signature_set", "status", "created_at"}
    )

    def identity_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude=set(self.IDENTITY_EXCLUDE))

    def compute_bundle_id(self) -> str:
        return content_digest(self.identity_payload())

    @model_validator(mode="after")
    def _fill_bundle_id(self) -> "SystemBundle":
        computed = self.compute_bundle_id()
        if not self.bundle_id:
            object.__setattr__(self, "bundle_id", computed)
        elif self.bundle_id != computed:
            raise ValueError(
                f"bundle_id {self.bundle_id!r} does not match content digest {computed!r}; "
                "bundles are content-addressed and must not be edited in place"
            )
        return self


class FieldChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    field_path: str  # JSON-pointer-ish, e.g. "/config/strategy"
    old_value: Any = None
    new_value: Any = None


class BundleDiff(BaseModel):
    """Machine-readable diff between a parent bundle and a child candidate."""

    model_config = ConfigDict(frozen=True)

    parent_bundle_id: str
    child_bundle_id: str
    changes: list[FieldChange] = Field(default_factory=list)

    def touched_paths(self) -> list[str]:
        return [c.field_path for c in self.changes]
