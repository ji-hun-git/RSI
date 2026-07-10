"""Tests for foundry.policy: capability tokens and the fail-closed PDP."""

from __future__ import annotations

from datetime import timedelta

import pytest

from foundry.contracts import ApprovalTier, AutonomyLevel
from foundry.policy import (
    ALLOWED_MUTATIONS,
    CapabilityIssuer,
    PolicyDecisionPoint,
    required_approval_tier,
)

# -- capabilities -------------------------------------------------------------


@pytest.fixture()
def issuer():
    return CapabilityIssuer()


def issue_default(issuer, **overrides):
    kwargs = dict(
        subject="agent.builder",
        actions=["tool.terminal.exec"],
        resource_scopes=["workspace/src"],
        ttl_seconds=900,
        mission_id="mis_test",
    )
    kwargs.update(overrides)
    return issuer.issue(**kwargs)


class TestCapabilityIssuer:
    def test_issue_binds_all_fields(self, issuer):
        token = issue_default(issuer)
        assert token.subject == "agent.builder"
        assert token.actions == ["tool.terminal.exec"]
        assert token.resource_scopes == ["workspace/src"]
        assert token.ttl_seconds == 900
        assert token.mission_id == "mis_test"
        assert not token.transferable

    def test_valid_token_validates(self, issuer):
        token = issue_default(issuer)
        assert issuer.validate(
            token,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="workspace/src/main.py",
            at=token.issued_at + timedelta(seconds=1),
        )

    def test_zero_ttl_expires_immediately(self, issuer):
        token = issue_default(issuer, ttl_seconds=0)
        assert not issuer.validate(
            token,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="workspace/src/main.py",
            at=token.issued_at,
        )

    def test_expiry_boundary(self, issuer):
        token = issue_default(issuer, ttl_seconds=60)
        ok_at = token.issued_at + timedelta(seconds=59)
        expired_at = token.issued_at + timedelta(seconds=60)  # now >= expiry fails
        assert issuer.validate(
            token,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="workspace/src/main.py",
            at=ok_at,
        )
        assert not issuer.validate(
            token,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="workspace/src/main.py",
            at=expired_at,
        )

    def test_non_transferability(self, issuer):
        token = issue_default(issuer)
        assert not issuer.validate(
            token,
            subject="optimizer.gepa",  # someone else presenting the token
            action="tool.terminal.exec",
            resource="workspace/src/main.py",
            at=token.issued_at,
        )

    def test_action_scoping(self, issuer):
        token = issue_default(issuer)
        assert not issuer.validate(
            token,
            subject="agent.builder",
            action="holdout.read",
            resource="workspace/src/main.py",
            at=token.issued_at,
        )

    def test_resource_scoping(self, issuer):
        token = issue_default(issuer)
        assert not issuer.validate(
            token,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="secrets/api_key",
            at=token.issued_at,
        )

    def test_empty_resource_scopes_deny_every_resource(self, issuer):
        """Fail-closed: an empty scope list grants nothing, not everything."""
        token = issue_default(issuer, resource_scopes=[])
        assert not issuer.validate(
            token,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="prod://root-secrets",
            at=token.issued_at,
        )

    def test_scoped_token_requires_an_explicit_resource(self, issuer):
        """Fail-closed: omitting the resource never bypasses the scope check."""
        token = issue_default(issuer, resource_scopes=["safe://only/"])
        assert not issuer.validate(
            token, subject="agent.builder", action="tool.terminal.exec", at=token.issued_at
        )

    def test_unscoped_token_allows_resource_free_actions_only(self, issuer):
        token = issue_default(issuer, resource_scopes=[])
        assert issuer.validate(
            token, subject="agent.builder", action="tool.terminal.exec", at=token.issued_at
        )
        assert not issuer.validate(
            token,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="anything://at-all",
            at=token.issued_at,
        )

    def test_revocation(self, issuer):
        token = issue_default(issuer)
        assert issuer.validate(
            token,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="workspace/src/main.py",
            at=token.issued_at,
        )
        issuer.revoke(token.capability_id)
        assert not issuer.validate(
            token,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="workspace/src/main.py",
            at=token.issued_at,
        )

    def test_revocation_is_per_token(self, issuer):
        kept = issue_default(issuer)
        revoked = issue_default(issuer)
        issuer.revoke(revoked.capability_id)
        assert issuer.validate(
            kept,
            subject="agent.builder",
            action="tool.terminal.exec",
            resource="workspace/src/main.py",
            at=kept.issued_at,
        )


# -- PDP ---------------------------------------------------------------------


@pytest.fixture()
def pdp():
    return PolicyDecisionPoint()


def fork_context(level, paths):
    return {"autonomy_level": level, "field_paths": paths}


class TestFailClosed:
    def test_unknown_action_denied(self, pdp):
        decision = pdp.decide("bundle.delete", "human:owner", "sha256:x", {})
        assert not decision.permit
        assert decision.reason == "fail_closed"

    def test_unknown_subject_denied(self, pdp):
        decision = pdp.decide(
            "bundle.fork", "intruder", "sha256:x", fork_context(2, ["/config/strategy"])
        )
        assert not decision.permit
        assert decision.reason == "fail_closed"

    def test_missing_context_denied(self, pdp):
        decision = pdp.decide("bundle.fork", "optimizer.gepa", "sha256:x", {})
        assert not decision.permit
        assert decision.reason == "fail_closed"

    def test_malformed_autonomy_level_denied(self, pdp):
        decision = pdp.decide(
            "bundle.fork", "optimizer.gepa", "sha256:x", fork_context(99, ["/config/strategy"])
        )
        assert not decision.permit
        assert decision.reason == "fail_closed"

    @pytest.mark.parametrize("paths", [[42], ["/config/strategy", None], [{"p": 1}], [b"/config"]])
    def test_non_string_field_paths_denied_not_crashed(self, pdp, paths):
        """Malformed context must deny fail_closed, never raise (report 10.1)."""
        decision = pdp.decide("bundle.fork", "optimizer.gepa", "sha256:x", fork_context(2, paths))
        assert not decision.permit
        assert decision.reason == "fail_closed"

    def test_decide_is_deterministic(self, pdp):
        args = ("bundle.fork", "optimizer.gepa", "sha256:x", fork_context(2, ["/config/prompt"]))
        assert pdp.decide(*args) == pdp.decide(*args)


class TestForkPolicy:
    def test_l2_strategy_change_permitted(self, pdp):
        decision = pdp.decide(
            "bundle.fork", "optimizer.gepa", "sha256:x", fork_context(2, ["/config/strategy"])
        )
        assert decision.permit
        assert decision.approval_tier == ApprovalTier.A1_SINGLE_REVIEWER

    def test_l2_surface_includes_l1(self, pdp):
        l1 = ALLOWED_MUTATIONS[AutonomyLevel.MEMORY_RETRIEVAL_TUNING]
        l2 = ALLOWED_MUTATIONS[AutonomyLevel.PROMPT_SKILL_ROUTING]
        assert set(l1) <= set(l2)
        decision = pdp.decide(
            "bundle.fork",
            "optimizer.gepa",
            "sha256:x",
            fork_context(2, ["/memory_policy_ref", "/config/prompt", "/module_refs/planner"]),
        )
        assert decision.permit

    def test_l1_memory_policy_permitted_at_tier_a0(self, pdp):
        decision = pdp.decide(
            "bundle.fork", "optimizer.gepa", "sha256:x", fork_context(1, ["/memory_policy_ref"])
        )
        assert decision.permit
        assert decision.approval_tier == ApprovalTier.A0_AUTOMATIC

    def test_l1_prompt_change_denied(self, pdp):
        decision = pdp.decide(
            "bundle.fork", "optimizer.gepa", "sha256:x", fork_context(1, ["/config/prompt"])
        )
        assert not decision.permit

    def test_l2_path_outside_surface_denied(self, pdp):
        decision = pdp.decide(
            "bundle.fork", "optimizer.gepa", "sha256:x", fork_context(2, ["/workflow_ref"])
        )
        assert not decision.permit

    def test_prefix_match_respects_segment_boundaries(self, pdp):
        decision = pdp.decide(
            "bundle.fork", "optimizer.gepa", "sha256:x", fork_context(2, ["/config/strategyX"])
        )
        assert not decision.permit

    def test_one_bad_path_denies_the_whole_fork(self, pdp):
        decision = pdp.decide(
            "bundle.fork",
            "optimizer.gepa",
            "sha256:x",
            fork_context(2, ["/config/strategy", "/evaluation_profile_ref"]),
        )
        assert not decision.permit

    @pytest.mark.parametrize("level", [0, 3, 4, 5])
    def test_levels_without_stage1_surface_denied(self, pdp, level):
        assert ALLOWED_MUTATIONS[AutonomyLevel(level)] == []
        decision = pdp.decide(
            "bundle.fork", "optimizer.gepa", "sha256:x", fork_context(level, ["/config/strategy"])
        )
        assert not decision.permit


class TestApprovalTiers:
    @pytest.mark.parametrize(
        ("level", "tier"),
        [
            (0, ApprovalTier.A0_AUTOMATIC),
            (1, ApprovalTier.A0_AUTOMATIC),
            (2, ApprovalTier.A1_SINGLE_REVIEWER),
            (3, ApprovalTier.A2_DUAL_CONTROL),
            (4, ApprovalTier.A3_GOVERNANCE_COMMITTEE),
            (5, ApprovalTier.A4_CONVENTIONAL_SDLC),  # report 14.5: never A3
        ],
    )
    def test_report_14_5_mapping(self, level, tier):
        assert required_approval_tier(AutonomyLevel(level)) == tier


class TestPromotePolicy:
    def promote(self, pdp, **context):
        base = {"autonomy_level": 2, "gates_passed": True, "approval_tier": "A1"}
        base.update(context)
        return pdp.decide("bundle.promote", "promotion-gate", "sha256:candidate", base)

    def test_gates_passed_and_tier_met_permits(self, pdp):
        decision = self.promote(pdp)
        assert decision.permit
        assert decision.approval_tier == ApprovalTier.A1_SINGLE_REVIEWER

    def test_higher_tier_than_required_permits(self, pdp):
        assert self.promote(pdp, approval_tier=ApprovalTier.A2_DUAL_CONTROL).permit

    def test_gates_not_passed_denied(self, pdp):
        assert not self.promote(pdp, gates_passed=False).permit

    def test_gates_passed_must_be_exactly_true(self, pdp):
        assert not self.promote(pdp, gates_passed=1).permit
        assert not self.promote(pdp, gates_passed="yes").permit

    def test_insufficient_tier_denied(self, pdp):
        assert not self.promote(pdp, approval_tier="A0").permit

    def test_level_4_promotion_requires_a3(self, pdp):
        assert not self.promote(pdp, autonomy_level=4, approval_tier="A2").permit
        assert self.promote(pdp, autonomy_level=4, approval_tier="A3").permit

    def test_level_5_never_promotes_autonomously(self, pdp):
        """Report 14.5: Level 5 is A4 -- conventional SDLC only, no autonomous
        promotion path even when the caller asserts tier A3 or A4."""
        for asserted in ("A3", "A4"):
            decision = self.promote(pdp, autonomy_level=5, approval_tier=asserted)
            assert not decision.permit
            assert decision.reason == "conventional_sdlc_only_no_autonomous_promotion"
            assert decision.approval_tier == ApprovalTier.A4_CONVENTIONAL_SDLC

    def test_malformed_tier_denied(self, pdp):
        decision = self.promote(pdp, approval_tier="A9")
        assert not decision.permit
        assert decision.reason == "fail_closed"


class TestHoldoutRead:
    @pytest.mark.parametrize("subject", ["optimizer.gepa", "agent.builder"])
    def test_candidates_and_proposers_never_read_the_vault(self, pdp, subject):
        decision = pdp.decide("holdout.read", subject, "blind://vault/rotation-1", {})
        assert not decision.permit

    def test_experiment_controller_may_read(self, pdp):
        decision = pdp.decide(
            "holdout.read", "experiment-controller", "blind://vault/rotation-1", {}
        )
        assert decision.permit

    def test_unknown_subject_fails_closed(self, pdp):
        decision = pdp.decide("holdout.read", "candidate-under-test", "blind://vault/r1", {})
        assert not decision.permit
        assert decision.reason == "fail_closed"
