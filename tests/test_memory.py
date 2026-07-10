"""Governed memory service and context builder (report sections 11.3-11.6).

The load-bearing invariants: quarantine (staged items are invisible to
retrieval), provenance-required promotion, no self-promotion, no
autonomous governance/procedural writes, filters-before-match retrieval,
contradiction/expiry semantics with retained history, and event-sourced
state rebuild.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from foundry.contracts import (
    Confidence,
    MemoryItem,
    MemoryType,
    SecurityClass,
    SourceRef,
    VerificationStatus,
    utcnow,
)
from foundry.ledger import EventLedger
from foundry.memory import (
    ContextBuilder,
    MemoryGovernanceError,
    MemoryService,
    project_memory,
)

AUTHOR = "extractor.worker"
REVIEWER = "human:owner"


def claim(**overrides) -> MemoryItem:
    defaults = dict(
        memory_type=MemoryType.SEMANTIC_CLAIM,
        content={"subject": "langgraph", "predicate": "supports", "object": "interrupts"},
        source_refs=[SourceRef(artifact_ref="artifact://source/doc-1", locator="p.4")],
        applicability={"task_tags": ["architecture"], "projects": ["proj_a"]},
        confidence=Confidence(value=0.8, method="test"),
    )
    defaults.update(overrides)
    return MemoryItem(**defaults)


@pytest.fixture()
def ledger() -> EventLedger:
    return EventLedger(":memory:")


@pytest.fixture()
def service(ledger: EventLedger) -> MemoryService:
    return MemoryService(ledger)


def promoted_claim(service: MemoryService, **overrides):
    record = service.stage(claim(**overrides), author=AUTHOR)
    service.review(
        record.item.memory_id,
        reviewer=REVIEWER,
        verification_status=VerificationStatus.CORROBORATED,
    )
    return service.promote(record.item.memory_id, promoter=REVIEWER)


# -- write authority (11.3) -----------------------------------------------------


def test_governance_items_have_no_autonomous_path(service: MemoryService) -> None:
    item = claim(memory_type=MemoryType.GOVERNANCE)
    with pytest.raises(MemoryGovernanceError, match="no autonomous write path"):
        service.stage(item, author=AUTHOR)


def test_procedural_memory_is_refused_with_registry_pointer(service: MemoryService) -> None:
    item = claim(memory_type=MemoryType.PROCEDURE)
    with pytest.raises(MemoryGovernanceError, match="bundle registry"):
        service.stage(item, author=AUTHOR)


def test_source_and_evaluation_types_belong_to_other_stores(service: MemoryService) -> None:
    for memory_type in (MemoryType.SOURCE, MemoryType.EVALUATION):
        with pytest.raises(MemoryGovernanceError, match="owned by another store"):
            service.stage(claim(memory_type=memory_type), author=AUTHOR)


def test_staging_forces_unverified_status(service: MemoryService) -> None:
    smuggled = claim(verification_status=VerificationStatus.HUMAN_CONFIRMED)
    record = service.stage(smuggled, author=AUTHOR)
    assert record.verification_status is VerificationStatus.UNVERIFIED


def test_staged_items_are_quarantined_from_retrieval(service: MemoryService) -> None:
    service.stage(claim(), author=AUTHOR)
    assert service.retrieve(subject="agent.builder", task_tags={"architecture"}) == []


# -- promotion (11.3, 11.6 memory safety invariant) -------------------------------


def test_unreviewed_items_cannot_promote(service: MemoryService) -> None:
    record = service.stage(claim(), author=AUTHOR)
    with pytest.raises(MemoryGovernanceError, match="no.*review evidence|review evidence"):
        service.promote(record.item.memory_id, promoter=REVIEWER)


def test_author_cannot_promote_own_item(service: MemoryService) -> None:
    record = service.stage(claim(), author=AUTHOR)
    service.review(
        record.item.memory_id,
        reviewer=REVIEWER,
        verification_status=VerificationStatus.CORROBORATED,
    )
    with pytest.raises(MemoryGovernanceError, match="self-promotion"):
        service.promote(record.item.memory_id, promoter=AUTHOR)


def test_hypothesis_can_never_become_production_memory(service: MemoryService) -> None:
    hypo = claim(source_refs=[], is_hypothesis=True)
    record = service.stage(hypo, author=AUTHOR)
    service.review(
        record.item.memory_id,
        reviewer=REVIEWER,
        verification_status=VerificationStatus.CORROBORATED,
    )
    with pytest.raises(MemoryGovernanceError, match="hypothesis without provenance"):
        service.promote(record.item.memory_id, promoter=REVIEWER)


def test_rejected_items_stay_rejected(service: MemoryService) -> None:
    record = service.stage(claim(), author=AUTHOR)
    service.review(
        record.item.memory_id,
        reviewer=REVIEWER,
        verification_status=VerificationStatus.CONTRADICTED,
        decision="reject",
    )
    with pytest.raises(MemoryGovernanceError, match="only staged items promote"):
        service.promote(record.item.memory_id, promoter=REVIEWER)


def test_negative_lesson_needs_scope_and_reconsideration(service: MemoryService) -> None:
    unscoped = claim(memory_type=MemoryType.NEGATIVE, applicability={})
    record = service.stage(unscoped, author=AUTHOR)
    service.review(
        record.item.memory_id,
        reviewer=REVIEWER,
        verification_status=VerificationStatus.CORROBORATED,
    )
    with pytest.raises(MemoryGovernanceError, match="applicability scope"):
        service.promote(record.item.memory_id, promoter=REVIEWER)

    no_reconsider = claim(memory_type=MemoryType.NEGATIVE, expiration_policy={})
    record2 = service.stage(no_reconsider, author=AUTHOR)
    service.review(
        record2.item.memory_id,
        reviewer=REVIEWER,
        verification_status=VerificationStatus.CORROBORATED,
    )
    with pytest.raises(MemoryGovernanceError, match="reconsideration condition"):
        service.promote(record2.item.memory_id, promoter=REVIEWER)

    proper = claim(
        memory_type=MemoryType.NEGATIVE,
        expiration_policy={"review_after": (utcnow() + timedelta(days=90)).isoformat()},
    )
    record3 = service.stage(proper, author=AUTHOR)
    service.review(
        record3.item.memory_id,
        reviewer=REVIEWER,
        verification_status=VerificationStatus.CORROBORATED,
    )
    assert service.promote(record3.item.memory_id, promoter=REVIEWER).stage == "promoted"


def test_successful_trajectory_alone_grants_nothing(service: MemoryService) -> None:
    """Report 11.6: appearing in a successful run does not make a claim memory."""
    record = service.stage(
        claim(content={"lesson": "always retry twice"}), author="agent.builder"
    )
    # No review happened; the item matches every filter but is invisible.
    assert service.retrieve(subject="agent.builder", task_tags={"architecture"}) == []
    with pytest.raises(MemoryGovernanceError):
        service.promote(record.item.memory_id, promoter="agent.builder")


# -- retrieval (11.4): filters before match ---------------------------------------


def test_promoted_items_are_retrievable_and_ranked(service: MemoryService) -> None:
    a = promoted_claim(service, content={"fact": "alpha"})
    service.stage(claim(content={"fact": "staged"}), author=AUTHOR)
    results = service.retrieve(subject="agent.builder", task_tags={"architecture"})
    assert [r.item.memory_id for r in results] == [a.item.memory_id]


def test_security_class_filters_run_before_matching(service: MemoryService) -> None:
    secret = promoted_claim(
        service, security_class=SecurityClass.RESTRICTED, content={"fact": "restricted"}
    )
    visible = service.retrieve(
        subject="agent.builder",
        clearance=SecurityClass.INTERNAL,
        task_tags={"architecture"},
    )
    assert secret.item.memory_id not in [r.item.memory_id for r in visible]
    cleared = service.retrieve(
        subject="agent.builder",
        clearance=SecurityClass.RESTRICTED,
        task_tags={"architecture"},
    )
    assert secret.item.memory_id in [r.item.memory_id for r in cleared]


def test_read_scope_binds_to_subject(service: MemoryService) -> None:
    scoped = promoted_claim(service, read_scope=["agent.designer"])
    assert service.retrieve(subject="agent.builder", task_tags={"architecture"}) == []
    allowed = service.retrieve(subject="agent.designer", task_tags={"architecture"})
    assert [r.item.memory_id for r in allowed] == [scoped.item.memory_id]


def test_temporal_validity_window_enforced(service: MemoryService) -> None:
    now = utcnow()
    promoted_claim(service, valid_from=now - timedelta(days=2), valid_to=now - timedelta(days=1))
    assert service.retrieve(subject="s", task_tags={"architecture"}, at=now) == []


def test_contradicted_items_leave_retrieval_and_become_warnings(
    service: MemoryService,
) -> None:
    record = promoted_claim(service)
    service.contradict(
        record.item.memory_id, evidence_ref="artifact://source/doc-2", actor=REVIEWER
    )
    assert service.retrieve(subject="s", task_tags={"architecture"}) == []
    warnings = service.relevant_warnings(task_tags={"architecture"})
    assert [w.item.memory_id for w in warnings] == [record.item.memory_id]
    # History is retained: the record still exists with its contradiction link.
    kept = service.get(record.item.memory_id)
    assert kept.contradiction_refs == ("artifact://source/doc-2",)


def test_expiry_removes_from_retrieval_but_keeps_history(service: MemoryService) -> None:
    record = promoted_claim(
        service,
        expiration_policy={"review_after": (utcnow() - timedelta(days=1)).isoformat()},
    )
    expired = service.expire_due()
    assert expired == [record.item.memory_id]
    assert service.retrieve(subject="s", task_tags={"architecture"}) == []
    assert service.get(record.item.memory_id).stage == "expired"


def test_retrieval_feedback_accumulates_quality_evidence(service: MemoryService) -> None:
    record = promoted_claim(service)
    service.record_retrieval_feedback(record.item.memory_id, signal="useful", actor=REVIEWER)
    service.record_retrieval_feedback(record.item.memory_id, signal="harmful", actor=REVIEWER)
    service.record_retrieval_feedback(record.item.memory_id, signal="useful", actor=REVIEWER)
    assert service.get(record.item.memory_id).quality == {"useful": 2, "harmful": 1}


# -- event-sourced rebuild ---------------------------------------------------------


def test_second_service_projects_identical_state(ledger: EventLedger) -> None:
    first = MemoryService(ledger)
    a = promoted_claim(first)
    staged = first.stage(claim(content={"fact": "pending"}), author=AUTHOR)
    first.contradict(a.item.memory_id, evidence_ref="artifact://x", actor=REVIEWER)

    second = MemoryService(ledger)  # fresh projection over the same ledger
    assert second.records().keys() == first.records().keys()
    assert second.get(a.item.memory_id).verification_status is VerificationStatus.CONTRADICTED
    assert second.get(staged.item.memory_id).stage == "staged"
    assert project_memory([e for e in ledger.query() if e.event_type.startswith("memory.")])[
        a.item.memory_id
    ].contradiction_refs == ("artifact://x",)


# -- context builder (11.4 steps 3-6) ----------------------------------------------


def test_context_package_cites_budgets_and_warns(ledger: EventLedger) -> None:
    service = MemoryService(ledger)
    kept = promoted_claim(service, content={"fact": "useful architecture note"})
    flagged = promoted_claim(service, content={"fact": "later disproven"})
    service.contradict(flagged.item.memory_id, evidence_ref="artifact://counter", actor=REVIEWER)

    builder = ContextBuilder(service, ledger)
    package = builder.build(
        mission_id="mis_ctx",
        node_id="plan",
        subject="agent.builder",
        task_tags={"architecture"},
        procedures=["skill.slugify@1.0.0"],
        max_tokens=500,
    )
    assert [e.ref for e in package.evidence_items] == [kept.item.memory_id]
    assert package.evidence_items[0].source is not None  # citation present
    assert any(flagged.item.memory_id in w for w in package.warnings)
    assert package.token_allocation["budget"] == 500
    assert package.token_allocation["omitted_items"] == 0
    assert package.retrieval_trace["filters_before_match"] is True
    shown = ledger.query(mission_id="mis_ctx", event_type="memory.item_shown")
    assert [e.payload["memory_id"] for e in shown] == [kept.item.memory_id]


def test_context_budget_omits_rather_than_truncates_silently(ledger: EventLedger) -> None:
    service = MemoryService(ledger)
    for i in range(5):
        promoted_claim(service, content={"fact": f"note {i}", "detail": "x" * 300})
    builder = ContextBuilder(service, ledger)
    package = builder.build(
        mission_id="mis_budget",
        node_id="plan",
        subject="agent.builder",
        task_tags={"architecture"},
        max_tokens=150,
    )
    included = len(package.evidence_items)
    assert 0 < included < 5
    assert package.token_allocation["omitted_items"] == 5 - included
    assert package.token_allocation["evidence"] <= 150
