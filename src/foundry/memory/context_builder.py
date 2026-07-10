"""ContextBuilder: governed retrieval into a cited, budgeted ContextPackage.

The report 11.4 retrieval protocol, steps 3-6: retrieve through the memory
service's filters-first read path, assemble the exact evidence set one
module invocation will see, attach warnings (contradicted or expired items
in scope), enforce an explicit token budget with an omitted-item count
(never silent truncation), record the retrieval trace, and emit a
MEMORY_SHOWN event per included item so "which items were shown to which
module" is reconstructible from the ledger.
"""

from __future__ import annotations

import json
from typing import Any

from foundry.contracts import (
    ContextPackage,
    Event,
    EventTypes,
    EvidenceItem,
    LedgerLike,
    MemoryType,
    SecurityClass,
    utcnow,
)

from .service import MemoryRecord, MemoryService


def _estimate_tokens(text: str) -> int:
    """Coarse, deterministic token estimate (4 chars/token heuristic)."""
    return max(1, len(text) // 4)


def _excerpt(record: MemoryRecord, max_chars: int = 400) -> str:
    return json.dumps(record.item.content, sort_keys=True, ensure_ascii=False)[:max_chars]


class ContextBuilder:
    """Builds one ContextPackage per (mission, node) information need."""

    def __init__(self, memory: MemoryService, ledger: LedgerLike) -> None:
        self._memory = memory
        self._ledger = ledger

    def build(
        self,
        *,
        mission_id: str,
        node_id: str,
        subject: str,
        clearance: SecurityClass = SecurityClass.INTERNAL,
        memory_types: set[MemoryType] | None = None,
        task_tags: set[str] | None = None,
        projects: set[str] | None = None,
        terms: list[str] | None = None,
        procedures: list[str] | None = None,
        max_tokens: int = 2000,
        limit: int = 20,
    ) -> ContextPackage:
        records = self._memory.retrieve(
            subject=subject,
            clearance=clearance,
            memory_types=memory_types,
            task_tags=task_tags,
            projects=projects,
            terms=terms,
            limit=limit,
        )

        evidence: list[EvidenceItem] = []
        used_tokens = 0
        omitted = 0
        for record in records:
            excerpt = _excerpt(record)
            cost = _estimate_tokens(excerpt)
            if used_tokens + cost > max_tokens:
                omitted += 1
                continue
            used_tokens += cost
            evidence.append(
                EvidenceItem(
                    ref=record.item.memory_id,
                    excerpt=excerpt,
                    source=record.item.source_refs[0] if record.item.source_refs else None,
                    confidence=record.item.confidence,
                )
            )

        warnings = [
            (
                f"{r.item.memory_id} is "
                f"{'contradicted' if r.contradiction_refs else r.stage}; "
                "do not rely on it"
            )
            for r in self._memory.relevant_warnings(clearance=clearance, task_tags=task_tags)
        ]

        need: dict[str, Any] = {
            "memory_types": sorted(t.value for t in memory_types) if memory_types else None,
            "task_tags": sorted(task_tags) if task_tags else None,
            "projects": sorted(projects) if projects else None,
            "terms": terms or None,
        }
        package = ContextPackage(
            mission_id=mission_id,
            node_id=node_id,
            information_need={k: v for k, v in need.items() if v is not None},
            evidence_items=evidence,
            procedures=procedures or [],
            warnings=warnings,
            token_allocation={
                "budget": max_tokens,
                "evidence": used_tokens,
                "omitted_items": omitted,
            },
            retrieval_trace={
                "subject": subject,
                "clearance": clearance.value,
                "candidates": len(records),
                "included": [e.ref for e in evidence],
                "filters_before_match": True,
            },
            freshness={"built_at": utcnow().isoformat()},
        )
        for item in evidence:
            self._ledger.append(
                Event(
                    event_type=EventTypes.MEMORY_SHOWN,
                    mission_id=mission_id,
                    node_id=node_id,
                    actor=subject,
                    payload={"memory_id": item.ref, "package_id": package.package_id},
                )
            )
        return package
