"""Budget-governed improvement search (report 12.2, 12.5, 6).

Unit tests pin each stopping condition with injected propose/evaluate
functions; the integration test drives the real pipeline (diagnose ->
propose -> fork -> paired blind experiment -> gate) as a budget-governed
search and checks the full cost accounting.
"""

from __future__ import annotations

import pytest

from foundry.cli import FORK_BOOKKEEPING_PATHS
from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    BundleDiff,
    ChangeTarget,
    DecisionAction,
    EventTypes,
    ExperimentBudget,
    FieldChange,
    ImprovementProposal,
    ModuleRef,
    SystemBundle,
    TaskSetRefs,
    TaskSetRole,
)
from foundry.evaluation import EvaluationHarness, exact_match
from foundry.experiment import ExperimentController, HoldoutVault
from foundry.improvement import (
    CandidateOutcome,
    EvidenceDiagnoser,
    SearchBudget,
    SearchController,
    TemplateMutationProposer,
    diff_digest,
)
from foundry.ledger import EventLedger
from foundry.promotion import PromotionGate
from foundry.registry import BundleRegistry, HMACSigner
from foundry.runtime import FIXTURE_WORKFLOW_REF
from foundry.workers import FixtureWorker, generate_task_sets
from test_improvement_loop import L2_PREFIXES, SEED, constraints, run_mission_cohort


def parent_bundle() -> SystemBundle:
    return SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "naive"})


def a_proposal(parent: SystemBundle, new_value: str = "robust") -> ImprovementProposal:
    return ImprovementProposal(
        parent_bundle_id=parent.bundle_id,
        target=ChangeTarget(field_path="/config/strategy"),
        hypothesis="x",
        changes=[FieldChange(field_path="/config/strategy", old_value="naive", new_value=new_value)],
        rollback_condition="rb",
        proposer=ModuleRef(id="optimizer.test"),
    )


def outcome_for(proposal: ImprovementProposal, *, accepted: bool, holdout: float, cost: float = 1.0):
    return CandidateOutcome(
        proposal_id=proposal.proposal_id,
        candidate_bundle_id="sha256:" + "c" * 64,
        diff_digest=diff_digest(list(proposal.changes)),
        action="canary" if accepted else "quarantine",
        holdout_lower_bound=holdout,
        cost_usd=cost,
        accepted=accepted,
    )


# -- stopping conditions ------------------------------------------------------


def test_accepting_a_candidate_stops_the_search() -> None:
    parent = parent_bundle()
    report = SearchController(SearchBudget()).run(
        parent,
        lambda p, rejected: [a_proposal(p)],
        lambda p, proposal: outcome_for(proposal, accepted=True, holdout=1.0),
    )
    assert report.accepted is not None
    assert report.stop_reason == "accepted a candidate"
    assert report.candidates_evaluated == 1


def test_convergence_when_the_proposer_runs_dry() -> None:
    parent = parent_bundle()
    calls = {"n": 0}

    def propose(p, rejected):
        calls["n"] += 1
        return [a_proposal(p)] if calls["n"] == 1 else []  # then honors the rejected diff

    report = SearchController(SearchBudget(max_iterations=5)).run(
        parent, propose, lambda p, proposal: outcome_for(proposal, accepted=False, holdout=-0.1)
    )
    assert report.accepted is None
    assert "converged" in report.stop_reason
    assert report.candidates_evaluated == 1
    assert len(report.rejected_diffs) == 1


def test_cost_budget_exhaustion_stops_the_search() -> None:
    parent = parent_bundle()
    report = SearchController(SearchBudget(max_cost_usd=3.0, max_iterations=10)).run(
        parent,
        lambda p, rejected: [a_proposal(p, new_value=f"variant_{len(rejected)}")],
        lambda p, proposal: outcome_for(proposal, accepted=False, holdout=0.0, cost=2.0),
    )
    assert report.accepted is None
    assert "cost budget exhausted" in report.stop_reason
    assert report.total_cost_usd <= 4.0


def test_candidate_budget_exhaustion_stops_the_search() -> None:
    parent = parent_bundle()
    i = {"n": 0}

    def propose(p, rejected):
        i["n"] += 1
        return [a_proposal(p, new_value=f"v{i['n']}")]

    report = SearchController(SearchBudget(max_candidates=3, max_iterations=100)).run(
        parent, propose, lambda p, proposal: outcome_for(proposal, accepted=False, holdout=0.0, cost=0.0)
    )
    assert report.candidates_evaluated == 3
    assert "candidate budget exhausted" in report.stop_reason


def test_no_candidate_beats_the_effect_floor_is_reported() -> None:
    parent = parent_bundle()
    i = {"n": 0}

    def propose(p, rejected):
        i["n"] += 1
        return [a_proposal(p, new_value=f"v{i['n']}")] if i["n"] <= 3 else []

    report = SearchController(SearchBudget(minimum_practical_effect=0.05)).run(
        parent, propose, lambda p, proposal: outcome_for(proposal, accepted=False, holdout=0.01)
    )
    assert report.accepted is None
    assert "minimum practical effect" in report.stop_reason
    assert report.best_holdout_lower_bound == pytest.approx(0.01)


def test_budget_events_are_ledgered() -> None:
    ledger = EventLedger(":memory:")
    parent = parent_bundle()
    SearchController(SearchBudget(max_cost_usd=4.0), ledger=ledger).run(
        parent,
        lambda p, rejected: [a_proposal(p, new_value=f"v{len(rejected)}")],
        lambda p, proposal: outcome_for(proposal, accepted=False, holdout=0.0, cost=5.0),
    )
    assert ledger.query(event_type=EventTypes.BUDGET_RESERVED)
    assert ledger.query(event_type=EventTypes.BUDGET_EXHAUSTED)


# -- integration with the real pipeline ---------------------------------------


def test_search_over_the_real_pipeline_finds_and_accepts_robust(tmp_path) -> None:
    prefixes = list(L2_PREFIXES)
    ledger = EventLedger(":memory:")
    signer = HMACSigner.load_or_create(tmp_path / "keys" / "k.key")
    registry = BundleRegistry(tmp_path / "bundles", signer=signer)
    s0 = registry.sign(SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "naive"}))
    registry.register(s0)
    corpus = generate_task_sets(SEED)
    run_mission_cohort(ledger, s0, corpus["development"])

    diagnoses = EvidenceDiagnoser(ledger).diagnose()
    proposer = TemplateMutationProposer(mutation_table={"/config/strategy": {"naive": ["robust"]}})
    worker = FixtureWorker()

    def score(task, output):
        return exact_match(task.expected_output, output)

    def run_arm(bundle, task, seed):
        task_input = {"task_id": task.task_id, "text": task.input_text,
                      "family": getattr(task, "family", "slugify")}
        return worker.invoke(task_input, bundle.config, seed)["output"]

    def propose(parent, rejected):
        return proposer.propose(diagnoses, parent, constraints(rejected_diffs=rejected))

    def evaluate(parent, proposal):
        change = proposal.changes[0]
        s1 = registry.sign(registry.fork(parent, [change], allowed_path_prefixes=prefixes))
        registry.register(s1)
        vault = HoldoutVault(secret=b"search-vault-secret-00000000-01")
        vref = vault.seal(f"search-{s1.bundle_id[:12]}", list(corpus["protected"]), scorer=score)
        controller = ExperimentController(ledger, vault=vault)
        record = controller.design(
            proposal, parent, [s1],
            TaskSetRefs(development="d", protected=vref, retention="r", adversarial="a"),
            ExperimentBudget(per_arm_cost_usd=1.0, max_runs=200), SEED,
            minimum_practical_effect=proposal.minimum_practical_effect,
        )
        results = controller.run(
            record, {"control": parent, "candidate_a": s1},
            {TaskSetRole.DEVELOPMENT: list(corpus["development"]),
             TaskSetRole.RETENTION: list(corpus["retention"]),
             TaskSetRole.ADVERSARIAL: list(corpus["adversarial"])},
            run_arm, score,
        )
        analyses = controller.analyze(record, results, seed=SEED)["candidate_a"]
        metrics = EvaluationHarness().aggregate(results["candidate_a"])
        full = registry.diff(parent.bundle_id, s1.bundle_id)
        diff = BundleDiff(
            parent_bundle_id=full.parent_bundle_id, child_bundle_id=full.child_bundle_id,
            changes=[c for c in full.changes if c.field_path not in FORK_BOOKKEEPING_PATHS],
        )
        approval = ApprovalRecord(
            approver="human:owner", tier=ApprovalTier.A1_SINGLE_REVIEWER,
            candidate_bundle_id=s1.bundle_id,
        )
        decision = PromotionGate().run(
            proposal, parent, s1, diff, analyses, metrics, [approval], allowed_path_prefixes=prefixes
        )
        return CandidateOutcome(
            proposal_id=proposal.proposal_id,
            candidate_bundle_id=s1.bundle_id,
            diff_digest=diff_digest(list(proposal.changes)),
            action=decision.action.value,
            holdout_lower_bound=analyses[TaskSetRole.PROTECTED_HOLDOUT].ci_low,
            cost_usd=1.0,
            accepted=decision.action is DecisionAction.CANARY,
            evidence_event_ids=tuple(proposal.evidence_refs),
        )

    report = SearchController(SearchBudget(max_iterations=3), ledger=ledger).run(s0, propose, evaluate)
    assert report.accepted is not None
    assert report.accepted.holdout_lower_bound > 0.05
    assert report.stop_reason == "accepted a candidate"
    assert report.total_cost_usd == 1.0  # found it on the first candidate
