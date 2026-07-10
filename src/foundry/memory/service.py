"""Governed memory service: staging, quarantine, promotion, contradiction,
expiry and filtered retrieval (report sections 11.3, 11.4).

The service is an event-sourced projection, exactly like the deployment
controller: every state change is a canonical ``memory.*`` event on the
append-only ledger, item content is immutable once staged (corrections
are new items linked through ``lineage``), and a fresh service over the
same ledger projects identical state.

The write-authority table of report 11.3 is enforced structurally:

* Anything may be *staged* (a quarantine namespace) if its type is one
  the service governs -- semantic claims, negative lessons and episodic
  summaries. Staged items are invisible to retrieval, no matter how well
  they match.
* GOVERNANCE items are refused outright (no autonomous path, 11.3), and
  PROCEDURE items are refused with a pointer to the bundle registry:
  procedural memory is the highest-risk memory and takes the experiment
  and promotion-gate lifecycle, never a memory write.
* Promotion into retrieval requires review evidence (a verification
  status better than ``unverified``), real provenance (a hypothesis can
  never be promoted), and a promoting principal different from the
  author -- the memory-plane mirror of the no-self-approval rule.
* Negative lessons additionally require an explicit applicability scope
  and a reconsideration condition ("a warning and a test source, not an
  absolute prohibition", report 11.1/11.3).

This is the memory safety invariant of report 11.6 as code: no statement
becomes retrievable production memory merely because it appeared in a
successful trajectory.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from foundry.contracts import (
    Event,
    EventTypes,
    LedgerLike,
    MemoryItem,
    MemoryType,
    SecurityClass,
    VerificationStatus,
    utcnow,
)

#: Types this service governs (report 11.3). Source material belongs to the
#: artifact store, raw episodes to the event ledger, procedures to the
#: bundle registry, evaluations to the harness, governance to humans.
GOVERNED_TYPES = frozenset(
    {MemoryType.SEMANTIC_CLAIM, MemoryType.NEGATIVE, MemoryType.EPISODE}
)

#: Verification statuses that carry enough review evidence to promote.
PROMOTABLE_STATUSES = frozenset(
    {
        VerificationStatus.CORROBORATED,
        VerificationStatus.HUMAN_CONFIRMED,
        VerificationStatus.EXPERIMENTALLY_SUPPORTED,
    }
)

_CLEARANCE_ORDER = [
    SecurityClass.PUBLIC,
    SecurityClass.INTERNAL,
    SecurityClass.CONFIDENTIAL,
    SecurityClass.RESTRICTED,
    SecurityClass.SECRET_REFERENCE_ONLY,
]

_STATUS_RANK = {
    VerificationStatus.EXPERIMENTALLY_SUPPORTED: 3,
    VerificationStatus.HUMAN_CONFIRMED: 2,
    VerificationStatus.CORROBORATED: 1,
}


class MemoryGovernanceError(Exception):
    """A memory write or promotion violated the report 11.3 authority table."""


def clearance_covers(clearance: SecurityClass, item_class: SecurityClass) -> bool:
    return _CLEARANCE_ORDER.index(clearance) >= _CLEARANCE_ORDER.index(item_class)


@dataclass(frozen=True)
class MemoryRecord:
    """Projected state of one memory item. Content never mutates; only the
    lifecycle fields move, and every move has a ledger event behind it."""

    item: MemoryItem
    stage: str  # "staged" | "promoted" | "rejected" | "expired"
    verification_status: VerificationStatus
    author: str
    reviewer: str | None = None
    contradiction_refs: tuple[str, ...] = ()
    quality: dict[str, int] = field(default_factory=dict)


def project_memory(events: list[Event]) -> dict[str, MemoryRecord]:
    """Pure projection: replay ``memory.*`` events into current state."""
    records: dict[str, MemoryRecord] = {}
    for event in events:
        payload = event.payload
        if event.event_type == EventTypes.MEMORY_CANDIDATE_WRITTEN:
            item = MemoryItem.model_validate(payload["item"])
            records[item.memory_id] = MemoryRecord(
                item=item,
                stage="staged",
                verification_status=item.verification_status,
                author=payload["author"],
            )
            continue
        memory_id = payload.get("memory_id")
        if memory_id is None or memory_id not in records:
            continue
        record = records[memory_id]
        if event.event_type == EventTypes.MEMORY_REVIEWED:
            if payload.get("kind") == "retrieval_feedback":
                quality = dict(record.quality)
                signal = payload["signal"]
                quality[signal] = quality.get(signal, 0) + 1
                records[memory_id] = replace(record, quality=quality)
            else:
                status = VerificationStatus(payload["verification_status"])
                stage = "rejected" if payload.get("decision") == "reject" else record.stage
                records[memory_id] = replace(
                    record,
                    verification_status=status,
                    reviewer=payload["reviewer"],
                    stage=stage,
                )
        elif event.event_type == EventTypes.MEMORY_PROMOTED:
            records[memory_id] = replace(record, stage="promoted")
        elif event.event_type == EventTypes.MEMORY_CONTRADICTED:
            records[memory_id] = replace(
                record,
                verification_status=VerificationStatus.CONTRADICTED,
                contradiction_refs=record.contradiction_refs + (payload["evidence_ref"],),
            )
        elif event.event_type == EventTypes.MEMORY_EXPIRED:
            records[memory_id] = replace(record, stage="expired")
    return records


class MemoryService:
    """Ledger-backed governed memory (report 11.3/11.4). State is a projection."""

    def __init__(self, ledger: LedgerLike) -> None:
        self._ledger = ledger
        self._records = project_memory(
            [e for e in ledger.query() if e.event_type.startswith("memory.")]
        )

    # -- write path (11.3) -----------------------------------------------------

    def stage(self, item: MemoryItem, *, author: str) -> MemoryRecord:
        """Quarantined candidate write. The ONLY entry point for new items."""
        if item.memory_type is MemoryType.GOVERNANCE:
            raise MemoryGovernanceError(
                "governance records have no autonomous write path (report 11.3)"
            )
        if item.memory_type is MemoryType.PROCEDURE:
            raise MemoryGovernanceError(
                "procedural memory takes the experiment/promotion-gate lifecycle "
                "through the bundle registry, never a memory write (report 11.3)"
            )
        if item.memory_type not in GOVERNED_TYPES:
            raise MemoryGovernanceError(
                f"memory type {item.memory_type.value!r} is owned by another store "
                "(source -> artifact store, raw episodes -> event ledger, "
                "evaluations -> harness); this service stages claims, lessons "
                "and episodic summaries only"
            )
        if item.memory_id in self._records:
            return self._records[item.memory_id]  # idempotent re-stage
        # Whatever the writer asserted, a candidate starts unverified:
        # verification evidence is produced by review, not self-declared.
        staged_item = item.model_copy(
            update={"verification_status": VerificationStatus.UNVERIFIED, "author": author}
        )
        self._emit(
            EventTypes.MEMORY_CANDIDATE_WRITTEN,
            {"item": staged_item.model_dump(mode="json"), "author": author},
            actor=author,
        )
        record = MemoryRecord(
            item=staged_item,
            stage="staged",
            verification_status=VerificationStatus.UNVERIFIED,
            author=author,
        )
        self._records[staged_item.memory_id] = record
        return record

    def review(
        self,
        memory_id: str,
        *,
        reviewer: str,
        verification_status: VerificationStatus,
        decision: str = "accept",
        rationale: str = "",
    ) -> MemoryRecord:
        """Attach review evidence; ``decision='reject'`` quarantines for good."""
        record = self._require(memory_id)
        if record.stage == "expired":
            raise MemoryGovernanceError(f"memory {memory_id!r} is expired; review a successor")
        self._emit(
            EventTypes.MEMORY_REVIEWED,
            {
                "memory_id": memory_id,
                "reviewer": reviewer,
                "verification_status": verification_status.value,
                "decision": decision,
                "rationale": rationale,
            },
            actor=reviewer,
        )
        stage = "rejected" if decision == "reject" else record.stage
        updated = replace(
            record, verification_status=verification_status, reviewer=reviewer, stage=stage
        )
        self._records[memory_id] = updated
        return updated

    def promote(self, memory_id: str, *, promoter: str) -> MemoryRecord:
        """Move a reviewed item into the retrievable store (report 11.3/11.6)."""
        record = self._require(memory_id)
        if record.stage != "staged":
            raise MemoryGovernanceError(
                f"memory {memory_id!r} is {record.stage!r}; only staged items promote"
            )
        if promoter == record.author:
            raise MemoryGovernanceError(
                "the author of a memory item may not promote it "
                "(no self-promotion; report 8.1 applied to the memory plane)"
            )
        if record.item.is_hypothesis or not record.item.source_refs:
            raise MemoryGovernanceError(
                "a hypothesis without provenance can never become production memory "
                "(report 11.6 memory safety invariant)"
            )
        if record.verification_status not in PROMOTABLE_STATUSES:
            raise MemoryGovernanceError(
                f"verification status {record.verification_status.value!r} carries no "
                "review evidence; promotion requires corroborated, human-confirmed "
                "or experimentally-supported status"
            )
        if record.item.memory_type is MemoryType.NEGATIVE:
            if not record.item.applicability:
                raise MemoryGovernanceError(
                    "a negative lesson needs an explicit applicability scope; "
                    "promote narrowly (report 11.5)"
                )
            if not record.item.expiration_policy:
                raise MemoryGovernanceError(
                    "a negative lesson must state its reconsideration condition "
                    "(report 11.3: a warning, not an absolute prohibition)"
                )
        self._emit(
            EventTypes.MEMORY_PROMOTED,
            {"memory_id": memory_id, "promoter": promoter},
            actor=promoter,
        )
        updated = replace(record, stage="promoted")
        self._records[memory_id] = updated
        return updated

    def contradict(self, memory_id: str, *, evidence_ref: str, actor: str) -> MemoryRecord:
        """Record contradicting evidence; the item stays, flagged, in history."""
        record = self._require(memory_id)
        self._emit(
            EventTypes.MEMORY_CONTRADICTED,
            {"memory_id": memory_id, "evidence_ref": evidence_ref},
            actor=actor,
        )
        updated = replace(
            record,
            verification_status=VerificationStatus.CONTRADICTED,
            contradiction_refs=record.contradiction_refs + (evidence_ref,),
        )
        self._records[memory_id] = updated
        return updated

    def expire(self, memory_id: str, *, reason: str, actor: str = "memory-service") -> MemoryRecord:
        """Retire an item from retrieval. History is retained, never deleted."""
        record = self._require(memory_id)
        self._emit(
            EventTypes.MEMORY_EXPIRED,
            {"memory_id": memory_id, "reason": reason},
            actor=actor,
        )
        updated = replace(record, stage="expired")
        self._records[memory_id] = updated
        return updated

    def expire_due(self, *, at: datetime | None = None) -> list[str]:
        """Expire every promoted item whose validity window or review date passed."""
        now = at or utcnow()
        expired: list[str] = []
        for memory_id, record in list(self._records.items()):
            if record.stage != "promoted":
                continue
            item = record.item
            due = item.valid_to is not None and item.valid_to <= now
            review_after = item.expiration_policy.get("review_after")
            if isinstance(review_after, str):
                due = due or datetime.fromisoformat(review_after) <= now
            if due:
                self.expire(memory_id, reason="validity window or review date passed")
                expired.append(memory_id)
        return expired

    def record_retrieval_feedback(
        self, memory_id: str, *, signal: str, actor: str, evidence_ref: str | None = None
    ) -> MemoryRecord:
        """Accumulate report 11.4 step-7 usefulness/harm observations."""
        if signal not in ("useful", "harmful"):
            raise ValueError(f"unknown retrieval feedback signal {signal!r}")
        record = self._require(memory_id)
        self._emit(
            EventTypes.MEMORY_REVIEWED,
            {
                "memory_id": memory_id,
                "kind": "retrieval_feedback",
                "signal": signal,
                "reviewer": actor,
                "evidence_ref": evidence_ref,
            },
            actor=actor,
        )
        quality = dict(record.quality)
        quality[signal] = quality.get(signal, 0) + 1
        updated = replace(record, quality=quality)
        self._records[memory_id] = updated
        return updated

    # -- read path (11.4): filters first, then match, then rank ---------------

    def retrieve(
        self,
        *,
        subject: str,
        clearance: SecurityClass = SecurityClass.INTERNAL,
        memory_types: set[MemoryType] | None = None,
        task_tags: set[str] | None = None,
        projects: set[str] | None = None,
        terms: list[str] | None = None,
        at: datetime | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Promoted, in-scope, non-contradicted items, deterministically ranked.

        Identity, security-class, read-scope and temporal filters run BEFORE
        any relevance matching (report 11.4 step 2): an out-of-clearance item
        is invisible no matter how well it matches. Contradicted items are
        excluded here and surface as ContextPackage warnings instead.
        """
        now = at or utcnow()
        eligible: list[tuple[tuple[int, int, int, str], MemoryRecord]] = []
        for record in self._records.values():
            if record.stage != "promoted":
                continue  # staged/rejected/expired items are not retrievable
            if record.verification_status in (
                VerificationStatus.CONTRADICTED,
                VerificationStatus.DEPRECATED,
            ):
                continue
            item = record.item
            if not clearance_covers(clearance, item.security_class):
                continue
            if item.read_scope and subject not in item.read_scope:
                continue
            if item.valid_from is not None and item.valid_from > now:
                continue
            if item.valid_to is not None and item.valid_to <= now:
                continue
            if memory_types is not None and item.memory_type not in memory_types:
                continue
            tag_hits = self._matches(item, "task_tags", task_tags)
            project_hits = self._matches(item, "projects", projects)
            if task_tags is not None and tag_hits == 0:
                continue
            if projects is not None and project_hits == 0:
                continue
            term_hits = 0
            if terms:
                text = str(sorted(item.content.items()))
                term_hits = sum(1 for term in terms if term in text)
                if term_hits == 0:
                    continue
            rank = (
                -_STATUS_RANK.get(record.verification_status, 0),
                -(tag_hits + project_hits),
                -term_hits,
                item.memory_id,  # total, deterministic order
            )
            eligible.append((rank, record))
        eligible.sort(key=lambda pair: pair[0])
        return [record for _, record in eligible[:limit]]

    def relevant_warnings(
        self,
        *,
        clearance: SecurityClass = SecurityClass.INTERNAL,
        task_tags: set[str] | None = None,
    ) -> list[MemoryRecord]:
        """Contradicted or expired items a consumer should be warned about."""
        warnings = []
        for record in self._records.values():
            flagged = (
                record.verification_status is VerificationStatus.CONTRADICTED
                or record.stage == "expired"
            )
            if not flagged or not clearance_covers(clearance, record.item.security_class):
                continue
            if task_tags is not None and self._matches(record.item, "task_tags", task_tags) == 0:
                continue
            warnings.append(record)
        return sorted(warnings, key=lambda r: r.item.memory_id)

    def get(self, memory_id: str) -> MemoryRecord:
        return self._require(memory_id)

    def records(self) -> dict[str, MemoryRecord]:
        return dict(self._records)

    # -- internal --------------------------------------------------------------

    @staticmethod
    def _matches(item: MemoryItem, key: str, wanted: set[str] | None) -> int:
        if wanted is None:
            return 0
        declared = set(item.applicability.get(key, []))
        return len(declared & wanted)

    def _require(self, memory_id: str) -> MemoryRecord:
        if memory_id not in self._records:
            raise KeyError(f"unknown memory item {memory_id!r}")
        return self._records[memory_id]

    def _emit(self, event_type: str, payload: dict[str, Any], *, actor: str) -> Event:
        return self._ledger.append(
            Event(event_type=event_type, actor=actor, payload=payload)
        )
