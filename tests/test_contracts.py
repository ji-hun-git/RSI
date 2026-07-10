"""Tests for contract-level fixes: canonical digests, 11.2 memory fields,
17.4 evaluation integrity, 12.3 proposal pre-registration, 15.2 event
vocabulary and the signed PromotionDecision payload.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest

from foundry.contracts import (
    ApprovalTier,
    DecisionAction,
    EvaluationResult,
    EventTypes,
    ImprovementProposal,
    MemoryItem,
    MemoryLink,
    MemoryType,
    ModuleRef,
    PromotionDecision,
    ResultIntegrity,
    SourceRef,
    canonical_json,
    content_digest,
    utcnow,
)


class TestCanonicalDigests:
    def test_naive_datetime_is_rejected(self) -> None:
        """A naive datetime would digest differently per host timezone."""
        naive = datetime(2026, 1, 1, 12, 0, 0)
        with pytest.raises(ValueError, match="naive datetime"):
            content_digest({"t": naive})
        with pytest.raises(ValueError, match="naive datetime"):
            canonical_json(naive)

    def test_aware_datetime_digests_identically_regardless_of_offset(self) -> None:
        from datetime import timedelta

        utc = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        seoul = utc.astimezone(timezone(timedelta(hours=9)))
        assert content_digest({"t": utc}) == content_digest({"t": seoul})

    def test_utcnow_is_aware(self) -> None:
        assert utcnow().tzinfo is not None


class TestMemoryItem:
    def _item(self, **overrides) -> MemoryItem:
        kwargs = dict(
            memory_type=MemoryType.SEMANTIC_CLAIM,
            content={"claim": "robust normalization helps"},
            source_refs=[SourceRef(artifact_ref="artifact://sha256:" + "a" * 64)],
        )
        kwargs.update(overrides)
        return MemoryItem(**kwargs)

    def test_carries_11_2_governance_fields(self) -> None:
        item = self._item(
            read_scope=["project:demo", "role:analyst"],
            write_scope=["project:demo"],
            quality_evidence={"retrieval_usefulness": 0.8},
        )
        assert item.read_scope == ["project:demo", "role:analyst"]
        assert item.write_scope == ["project:demo"]
        assert item.quality_evidence == {"retrieval_usefulness": 0.8}

    def test_created_at_and_observed_at_are_distinct_fields(self) -> None:
        observed = datetime(2026, 1, 1, tzinfo=UTC)
        item = self._item(observed_at=observed)
        assert item.observed_at == observed
        assert item.created_at != observed  # record time filled independently

    def test_evidence_links_are_typed_with_method_and_locator(self) -> None:
        link = MemoryLink(
            target_ref="artifact://sha256:" + "b" * 64,
            method="verbatim",
            locator="line 40-60",
        )
        item = self._item(supporting_refs=[link], contradicting_refs=[])
        assert item.supporting_refs[0].method == "verbatim"
        assert item.supporting_refs[0].locator == "line 40-60"
        with pytest.raises(ValueError):
            self._item(supporting_refs=["bare-string-ref"])  # type: ignore[list-item]


class TestEvaluationIntegrity:
    def _result(self) -> EvaluationResult:
        return EvaluationResult(
            subject_run_id="run_1",
            evaluator=ModuleRef(id="eval.exact_match", version="1.0.0"),
            metric="task_success",
            value=1.0,
        )

    def test_digest_excludes_the_integrity_block(self) -> None:
        result = self._result()
        digest = result.digest()
        sealed = result.with_integrity(ResultIntegrity(digest=digest))
        assert sealed.digest() == digest  # adding integrity does not change it
        assert sealed.integrity is not None
        assert sealed.integrity.digest == digest

    def test_tampering_is_detectable_against_the_stored_digest(self) -> None:
        result = self._result()
        sealed = result.with_integrity(ResultIntegrity(digest=result.digest()))
        tampered = sealed.model_copy(update={"value": 0.0})
        assert tampered.digest() != tampered.integrity.digest


class TestProposalPreRegistration:
    def test_proposal_carries_retention_set_and_thresholds(self) -> None:
        proposal = ImprovementProposal(
            parent_bundle_id="sha256:" + "a" * 64,
            target={"field_path": "/config/strategy"},  # type: ignore[arg-type]
            hypothesis="h",
            retention_set_ref="corpus://fixture/retention",
            minimum_practical_effect=0.05,
            retention_floor=0.01,
            subgroup_floors={"hard": 0.5},
        )
        assert proposal.retention_set_ref == "corpus://fixture/retention"
        assert proposal.minimum_practical_effect == 0.05
        assert proposal.retention_floor == 0.01
        assert proposal.subgroup_floors == {"hard": 0.5}


class TestEventVocabulary:
    @pytest.mark.parametrize(
        ("constant", "value"),
        [
            ("MODEL_REFUSAL", "model.refusal"),
            ("MODEL_USAGE", "model.usage"),
            ("TOOL_DISCOVERED", "tool.discovered"),
            ("TOOL_ROLLBACK", "tool.rollback"),
            ("MEMORY_REVIEWED", "memory.reviewed"),
            ("MEMORY_EXPIRED", "memory.expired"),
            ("ARTIFACT_EXPORTED", "artifact.exported"),
            ("ARTIFACT_DELETED", "artifact.deleted"),
            ("EVALUATION_CALIBRATION", "evaluation.calibration"),
            ("RESOURCE_QUOTA_VIOLATION", "resource.quota_violation"),
        ],
    )
    def test_15_2_event_types_are_named(self, constant: str, value: str) -> None:
        assert getattr(EventTypes, constant) == value


class TestPromotionDecisionSigning:
    def _decision(self) -> PromotionDecision:
        return PromotionDecision(
            candidate_bundle_id="sha256:" + "c" * 64,
            parent_bundle_id="sha256:" + "p" * 64,
            action=DecisionAction.CANARY,
            required_approval_tier=ApprovalTier.A1_SINGLE_REVIEWER,
            proposer="optimizer.gepa",
        )

    def test_signable_payload_excludes_only_the_signature_fields(self) -> None:
        decision = self._decision()
        payload = decision.signable_payload()
        assert "signer" not in payload
        assert "signature" not in payload
        assert payload["proposer"] == "optimizer.gepa"
        assert payload["required_approval_tier"] == "A1"
        # Every governance-relevant field is inside the signed payload.
        for field in ("action", "gate_results", "approvals", "candidate_bundle_id", "scope"):
            assert field in payload

    def test_payload_changes_when_any_signed_field_changes(self) -> None:
        decision = self._decision()
        downgraded = decision.model_copy(
            update={"required_approval_tier": ApprovalTier.A0_AUTOMATIC}
        )
        assert canonical_json(decision.signable_payload()) != canonical_json(
            downgraded.signable_payload()
        )
