"""Capstone end-to-end test: the report 22.2 success criterion.

Runs the complete Stage-1 demo flow once into a temp root and then proves
that an independent researcher, holding the persisted evidence (ledger,
bundles, artifacts -- the signing key is needed only to verify producer
signatures), can reproduce the mission and the candidate comparison:
(a) the experiment evidence and gate outcomes are as designed, (b) a
second set of components recomputes bit-identical paired analyses from
the persisted evidence, and the comparison *statistics* reproduce even
without the private key, (c) a recorded mission replays to the same
output digest, (d) ledger tampering is detected and a missing key is
reported distinctly without mutating the audited root, and (e) the gate
quarantines without approval and refuses a self-approved record.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from foundry.cli import (
    DemoResult,
    open_stores,
    recompute_experiment_analyses,
    replay_mission,
    run_demo,
    verify_root,
)
from foundry.cli import (
    _deployment_controller as deployment_controller_for,
)
from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    DecisionAction,
    EventTypes,
    GateId,
    TaskSetRole,
)
from foundry.ledger import EventLedger
from foundry.promotion import PromotionGate

SEED = 42


def _silent(_: str) -> None:
    return None


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> DemoResult:
    root = tmp_path_factory.mktemp("foundry-e2e")
    return run_demo(root, seed=SEED, out=_silent)


# -- (a) the experiment shows what the corpus was designed to show ------------


def test_development_gain_is_positive(demo: DemoResult) -> None:
    dev = demo.analyses[demo.candidate_arm_id][TaskSetRole.DEVELOPMENT]
    assert dev.mean_delta > 0
    assert dev.mean_delta >= demo.minimum_practical_effect
    assert dev.losses == 0


def test_holdout_lower_confidence_bound_is_positive(demo: DemoResult) -> None:
    holdout = demo.analyses[demo.candidate_arm_id][TaskSetRole.PROTECTED_HOLDOUT]
    assert holdout.ci_low > 0
    # Protected scores are keyed by blind vault handles, never task ids.
    assert all(key.startswith("blind://") for key in holdout.per_task_deltas)


def test_retention_does_not_regress(demo: DemoResult) -> None:
    retention = demo.analyses[demo.candidate_arm_id][TaskSetRole.RETENTION]
    assert retention.losses == 0
    assert retention.ci_low >= 0.0
    assert demo.metrics.safety_critical_violations == 0


def test_gate_reaches_canary_only_with_approval(demo: DemoResult) -> None:
    assert demo.quarantine_decision.action is DecisionAction.QUARANTINE
    assert demo.canary_decision.action is DecisionAction.CANARY
    assert demo.canary_decision.approvals == [demo.approval.approval_id]
    assert all(result.passed for result in demo.canary_decision.gate_results)
    assert demo.canary_decision.rollback_target == demo.s0.bundle_id


def test_demo_root_verifies_clean(demo: DemoResult) -> None:
    assert demo.chain_ok
    assert demo.active_bundle_id == demo.s1.bundle_id
    assert verify_root(demo.root, out=_silent) is True


# -- (b) replay: a second component set reproduces the analysis ---------------


def test_second_component_set_recomputes_identical_analyses(demo: DemoResult) -> None:
    recomputed = recompute_experiment_analyses(demo.root)
    assert set(recomputed) == {demo.record.experiment_id}
    # Full pydantic equality: per-task deltas, CI bounds, bootstrap seeds --
    # bit-for-bit identical to what the original process computed.
    assert recomputed[demo.record.experiment_id] == demo.analyses


def test_statistics_reproduce_without_the_private_key(demo: DemoResult, tmp_path: Path) -> None:
    """Report 22.2: the candidate-comparison statistics are a function of the
    evidence and the recorded seeds, NOT of the original process's secret.
    Blind-handle keys differ under a fresh vault secret; every recorded
    statistic must still match, and no key may be minted into the root."""
    root_copy = tmp_path / "keyless-root"
    shutil.copytree(demo.root, root_copy)
    shutil.rmtree(root_copy / "keys")

    recomputed = recompute_experiment_analyses(root_copy)

    assert not (root_copy / "keys").exists()  # the auditor never mutates the root
    stores = open_stores(root_copy, create=False)
    try:
        analyzed = stores.ledger.query(
            experiment_id=demo.record.experiment_id, event_type=EventTypes.EXPERIMENT_ANALYZED
        )[0]
    finally:
        stores.close()
    recorded = analyzed.payload["arms"]
    for arm_id, per_role in recomputed[demo.record.experiment_id].items():
        for role, analysis in per_role.items():
            summary = recorded[arm_id][role.value]
            assert analysis.n_pairs == summary["n_pairs"]
            assert analysis.mean_delta == summary["mean_delta"]
            assert [analysis.ci_low, analysis.ci_high] == summary["ci"]
            assert (analysis.wins, analysis.losses, analysis.ties) == (
                summary["wins"],
                summary["losses"],
                summary["ties"],
            )


def test_second_deployment_controller_projects_identical_state(demo: DemoResult) -> None:
    stores = open_stores(demo.root, create=False)
    try:
        controller = deployment_controller_for(stores)
        assert controller.active_bundle_id() == demo.active_bundle_id
        history = controller.history()
    finally:
        stores.close()
    kinds = [type(entry).__name__ for entry in history]
    assert kinds == ["DeploymentRecord", "DeploymentRecord", "RollbackRecord", "DeploymentRecord"]


# -- (c) a recorded mission replays to the same output digest -----------------


def test_recorded_missions_replay_to_same_digest(demo: DemoResult) -> None:
    assert len(demo.mission_ids) == 3
    for mission_id in demo.mission_ids:
        assert replay_mission(demo.root, mission_id, out=_silent) is True


def test_replay_unknown_mission_fails(demo: DemoResult) -> None:
    assert replay_mission(demo.root, "mis_does_not_exist", out=_silent) is False


# -- (e) authority is never implicit ------------------------------------------


def _rerun_gate(demo: DemoResult, approvals: list[ApprovalRecord]):
    # Thresholds are pre-registered on the proposal (report 12.3), so the
    # re-run needs no gate-time threshold arguments.
    return PromotionGate().run(
        demo.proposal,
        demo.s0,
        demo.s1,
        demo.diff,
        demo.analyses[demo.candidate_arm_id],
        demo.metrics,
        approvals,
        allowed_path_prefixes=demo.allowed_prefixes,
        rerun_agreement=demo.rerun_agreement,
    )


def test_gate_quarantines_without_any_approval(demo: DemoResult) -> None:
    decision = _rerun_gate(demo, [])
    assert decision.action is DecisionAction.QUARANTINE
    g8 = next(r for r in decision.gate_results if r.gate is GateId.G8_HUMAN_AUTHORIZATION)
    assert not g8.passed


def test_gate_rejects_a_self_approved_record(demo: DemoResult) -> None:
    self_approval = ApprovalRecord(
        approver=demo.proposal.proposer.id,  # the proposer approving itself
        tier=ApprovalTier.A1_SINGLE_REVIEWER,
        candidate_bundle_id=demo.s1.bundle_id,
    )
    decision = _rerun_gate(demo, [self_approval])
    g8 = next(r for r in decision.gate_results if r.gate is GateId.G8_HUMAN_AUTHORIZATION)
    assert not g8.passed
    assert "self-approval" in g8.reason
    assert self_approval.approval_id not in decision.approvals
    # A self-approved record never yields promotion authority: not CANARY.
    assert decision.action is DecisionAction.QUARANTINE


# -- (d) tamper evidence -------------------------------------------------------


def _tampered_copy(demo: DemoResult, tmp_path: Path) -> Path:
    """Copy the whole demo root and corrupt one event payload via raw SQL."""
    root_copy = tmp_path / "tampered-root"
    shutil.copytree(demo.root, root_copy)
    conn = sqlite3.connect(root_copy / "ledger.db")
    try:
        sequence, body = conn.execute(
            "SELECT sequence, body FROM events WHERE event_type = 'mission.compiled'"
            " ORDER BY sequence LIMIT 1"
        ).fetchone()
        doctored = json.loads(body)
        doctored["payload"]["task_type"] = "software.tampered"
        conn.execute(
            "UPDATE events SET body = ? WHERE sequence = ?",
            (json.dumps(doctored), sequence),
        )
        conn.commit()
    finally:
        conn.close()
    return root_copy


def test_tampered_ledger_row_breaks_the_chain(demo: DemoResult, tmp_path: Path) -> None:
    root_copy = _tampered_copy(demo, tmp_path)
    ledger = EventLedger(root_copy / "ledger.db")
    try:
        ok, errors = ledger.verify_chain()
    finally:
        ledger.close()
    assert ok is False
    assert any("digest mismatch" in error for error in errors)
    # The CLI-level verifier fails too, while the untouched original passes.
    assert verify_root(root_copy, out=_silent) is False
    assert verify_root(demo.root, out=_silent) is True


def test_truncated_ledger_tail_is_detected(demo: DemoResult, tmp_path: Path) -> None:
    """Silently deleting the newest event(s) is tamper-evident (checkpoint)."""
    root_copy = tmp_path / "truncated-root"
    shutil.copytree(demo.root, root_copy)
    conn = sqlite3.connect(root_copy / "ledger.db")
    try:
        conn.execute("DELETE FROM events WHERE sequence = (SELECT MAX(sequence) FROM events)")
        conn.commit()
    finally:
        conn.close()
    assert verify_root(root_copy, out=_silent) is False


def test_missing_key_is_a_distinct_outcome_and_never_minted(
    demo: DemoResult, tmp_path: Path
) -> None:
    """A verifier over a keyless root must report 'key not present' (not
    forgery) and must not write a fresh key into the root under audit."""
    root_copy = tmp_path / "no-keys-root"
    shutil.copytree(demo.root, root_copy)
    shutil.rmtree(root_copy / "keys")

    lines: list[str] = []
    ok = verify_root(root_copy, out=lines.append)

    assert ok is False  # signatures cannot be verified without the key
    assert not (root_copy / "keys").exists()  # no key was minted
    output = "\n".join(lines)
    assert "signing key not present" in output
    assert "signature mismatch" not in output  # never misdiagnosed as forgery
    # Everything key-independent still verifies on the same root.
    assert any(line.startswith("PASS ledger hash chain") for line in lines)
    assert any("recomputed paired analysis matches the ledger" in line for line in lines)
    assert not any("FAIL experiment" in line for line in lines)
