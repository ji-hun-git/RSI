"""Deterministic memory consolidation (report section 11.5).

The load-bearing invariants: recurrence is required (a one-off episode is
not a rule), disconfirming episodes block a candidate before it is staged,
consolidated patterns are STAGED not promoted (the 11.6 safety invariant),
negative lessons carry a reconsideration condition, and the whole job is
deterministic and idempotent.
"""

from __future__ import annotations

import pytest

from foundry.contracts import (
    Event,
    EventTypes,
    MemoryType,
    SystemBundle,
    VerificationStatus,
)
from foundry.improvement import record_mission_evaluation
from foundry.ledger import EventLedger
from foundry.memory import MemoryConsolidator, MemoryService
from foundry.runtime import FIXTURE_WORKFLOW_REF

CONSOLIDATOR = "consolidator.recurrence"
REVIEWER = "human:owner"


def bundle(strategy: str = "robust") -> SystemBundle:
    return SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": strategy})


def start_bundle(ledger: EventLedger, b: SystemBundle) -> None:
    """Record a MISSION_STARTED so the bundle config is attributable."""
    ledger.append(
        Event(
            event_type=EventTypes.MISSION_STARTED,
            mission_id="mis_seed",
            run_id="run_seed",
            system_bundle_id=b.bundle_id,
            payload={"spec": {"inputs": {}}, "bundle": b.model_dump(mode="json")},
        )
    )


def episode(ledger: EventLedger, b: SystemBundle, family: str, difficulty: str, value: float, i: int):
    record_mission_evaluation(
        ledger,
        mission_id=f"mis_{family}_{difficulty}_{i}",
        bundle_id=b.bundle_id,
        metric="task_success",
        value=value,
        task_family=family,
        difficulty=difficulty,
    )


@pytest.fixture()
def ledger() -> EventLedger:
    return EventLedger(":memory:")


@pytest.fixture()
def memory(ledger: EventLedger) -> MemoryService:
    return MemoryService(ledger)


# -- recurrence (step 4) -------------------------------------------------------


def test_recurring_success_pattern_is_staged(ledger: EventLedger, memory: MemoryService) -> None:
    b = bundle("robust")
    start_bundle(ledger, b)
    for i in range(4):
        episode(ledger, b, "slugify", "hard", 1.0, i)

    report = MemoryConsolidator(ledger, memory, min_support=3).consolidate()

    assert len(report.staged) == 1
    record = memory.get(report.staged[0])
    assert record.item.memory_type is MemoryType.SEMANTIC_CLAIM
    assert record.stage == "staged"  # quarantined, NOT promoted (report 11.6)
    assert record.verification_status is VerificationStatus.UNVERIFIED
    assert record.item.content["object"] == "slugify/hard"
    assert record.item.applicability["task_tags"] == ["slugify"]
    # provenance: every supporting episode is a source ref
    assert len(record.item.source_refs) == 4


def test_one_off_episode_is_not_a_rule(ledger: EventLedger, memory: MemoryService) -> None:
    b = bundle("robust")
    start_bundle(ledger, b)
    episode(ledger, b, "slugify", "hard", 1.0, 0)  # a single success
    report = MemoryConsolidator(ledger, memory, min_support=3).consolidate()
    assert report.staged == ()
    assert report.rejected  # recorded as considered-but-rejected, not silently dropped


# -- disconfirming search (step 3) --------------------------------------------


def test_counterexamples_block_a_success_pattern(ledger: EventLedger, memory: MemoryService) -> None:
    b = bundle("naive")
    start_bundle(ledger, b)
    for i in range(4):
        episode(ledger, b, "slugify", "hard", 1.0, i)  # 4 successes
    episode(ledger, b, "slugify", "hard", 0.0, 99)  # 1 disconfirming failure

    # strict default: any counterexample blocks the success pattern
    report = MemoryConsolidator(ledger, memory, min_support=3).consolidate()
    success = [
        p for p in report.rejected if p.kind == "success"
    ]
    assert success and success[0].counterexamples == 1
    # no success claim was staged; only the (sub-support) failure was considered
    staged_types = [memory.get(m).item.memory_type for m in report.staged]
    assert MemoryType.SEMANTIC_CLAIM not in staged_types


def test_counterexample_tolerance_stages_with_recorded_counterevidence(
    ledger: EventLedger, memory: MemoryService
) -> None:
    b = bundle("naive")
    start_bundle(ledger, b)
    for i in range(9):
        episode(ledger, b, "slugify", "easy", 1.0, i)  # 9 successes
    episode(ledger, b, "slugify", "easy", 0.0, 99)  # 1 failure (10% rate)

    report = MemoryConsolidator(
        ledger, memory, min_support=3, max_counterexample_rate=0.2
    ).consolidate()
    claim = next(memory.get(m) for m in report.staged if memory.get(m).item.memory_type is MemoryType.SEMANTIC_CLAIM)
    # the disconfirming episode is attached as counterevidence, not hidden
    assert len(claim.item.contradicting_refs) == 1
    assert claim.item.confidence.value == pytest.approx(9 / 10)


# -- failure clusters become negative lessons ---------------------------------


def test_recurring_failure_becomes_a_negative_lesson_with_reconsideration(
    ledger: EventLedger, memory: MemoryService
) -> None:
    b = bundle("naive")
    start_bundle(ledger, b)
    for i in range(4):
        episode(ledger, b, "slugify", "hard", 0.0, i)  # naive reliably fails hard tasks

    report = MemoryConsolidator(ledger, memory, min_support=3).consolidate()
    negatives = [memory.get(m) for m in report.staged if memory.get(m).item.memory_type is MemoryType.NEGATIVE]
    assert len(negatives) == 1
    neg = negatives[0]
    assert neg.item.content["predicate"] == "reliably_fails_on"
    # a negative lesson must carry a reconsideration condition (report 11.3)
    assert "reconsider_when" in neg.item.expiration_policy


# -- the 11.6 safety invariant: staged, still needs review + a distinct promoter


def test_consolidated_claim_still_requires_review_and_a_distinct_promoter(
    ledger: EventLedger, memory: MemoryService
) -> None:
    b = bundle("robust")
    start_bundle(ledger, b)
    for i in range(3):
        episode(ledger, b, "slugify", "hard", 1.0, i)
    memory_id = MemoryConsolidator(ledger, memory, min_support=3).consolidate().staged[0]

    # invisible to retrieval while staged
    assert memory.retrieve(subject="agent.builder", task_tags={"slugify"}) == []
    # the consolidator cannot promote its own output (no self-promotion)
    from foundry.memory import MemoryGovernanceError

    with pytest.raises(MemoryGovernanceError):
        memory.promote(memory_id, promoter=CONSOLIDATOR)
    # a reviewer + distinct promoter is the only path into retrieval
    memory.review(memory_id, reviewer=REVIEWER, verification_status=VerificationStatus.CORROBORATED)
    memory.promote(memory_id, promoter=REVIEWER)
    assert [r.item.memory_id for r in memory.retrieve(subject="a", task_tags={"slugify"})] == [memory_id]


# -- attribution: unrecoverable config is not consolidated ---------------------


def test_episodes_without_a_known_config_are_not_consolidated(
    ledger: EventLedger, memory: MemoryService
) -> None:
    # evaluations exist but NO MISSION_STARTED carries the bundle config
    b = bundle("robust")
    for i in range(4):
        episode(ledger, b, "slugify", "hard", 1.0, i)
    report = MemoryConsolidator(ledger, memory, min_support=3).consolidate()
    assert report.staged == ()  # unattributable to a frozen configuration


def test_experiment_mean_scores_are_not_treated_as_episodes(
    ledger: EventLedger, memory: MemoryService
) -> None:
    b = bundle("robust")
    start_bundle(ledger, b)
    # an experiment-controller METRIC_COMPUTED: mean_score, no mission_id, no task_family
    for _ in range(5):
        ledger.append(
            Event(
                event_type=EventTypes.METRIC_COMPUTED,
                experiment_id="exp_1",
                arm_id="candidate_a",
                system_bundle_id=b.bundle_id,
                payload={"metric": "mean_score", "role": "development", "value": 0.5},
            )
        )
    report = MemoryConsolidator(ledger, memory, min_support=3).consolidate()
    assert report.staged == ()  # aggregate arm metrics are not episodes


# -- determinism / idempotency ------------------------------------------------


def test_consolidation_is_idempotent(ledger: EventLedger, memory: MemoryService) -> None:
    b = bundle("robust")
    start_bundle(ledger, b)
    for i in range(4):
        episode(ledger, b, "slugify", "hard", 1.0, i)

    consolidator = MemoryConsolidator(ledger, memory, min_support=3)
    first = consolidator.consolidate()
    before = len(memory.records())
    second = MemoryConsolidator(ledger, memory, min_support=3).consolidate()
    # same evidence -> same memory id -> staging dedups; no new records
    assert first.staged == second.staged
    assert len(memory.records()) == before


def test_memory_id_is_a_deterministic_signature_digest(
    ledger: EventLedger, memory: MemoryService
) -> None:
    b = bundle("robust")
    start_bundle(ledger, b)
    for i in range(3):
        episode(ledger, b, "slugify", "hard", 1.0, i)
    memory_id = MemoryConsolidator(ledger, memory, min_support=3).consolidate().staged[0]
    assert memory_id.startswith("mem_") and len(memory_id) == len("mem_") + 32
