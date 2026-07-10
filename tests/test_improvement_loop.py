"""Diagnoser, proposer seam and the full improvement loop (report 8.3,
10.4, 12.4, 12.5).

The capstone test drives the ENTIRE improvement loop deterministically,
with no model anywhere: mission cohort -> read-only diagnosis -> typed
proposal from evidence -> policy-checked fork -> paired experiment with
blind holdout -> G0-G9 gate. The proposer never touches the registry,
vault or gate; everything it emits is data that still has to survive
every downstream authority.
"""

from __future__ import annotations

import pytest

from foundry.cli import FORK_BOOKKEEPING_PATHS
from foundry.compiler import MissionCompiler
from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    AutonomyLevel,
    BundleDiff,
    DecisionAction,
    EventTypes,
    ExperimentBudget,
    FieldChange,
    ImprovementProposal,
    MissionRequest,
    SystemBundle,
    TaskSetRefs,
    TaskSetRole,
)
from foundry.evaluation import EvaluationHarness, exact_match
from foundry.experiment import ExperimentController, HoldoutVault
from foundry.improvement import (
    EvidenceDiagnoser,
    ProposalConstraints,
    ProposalPolicyViolation,
    ProposerLike,
    RejectedDiff,
    TemplateMutationProposer,
    diff_digest,
    record_mission_evaluation,
)
from foundry.ledger import EventLedger
from foundry.policy import ALLOWED_MUTATIONS, PolicyDecisionPoint
from foundry.promotion import PromotionGate
from foundry.registry import BundleRegistry, HMACSigner
from foundry.runtime import FIXTURE_WORKFLOW_REF, DeterministicRuntime
from foundry.workers import FixtureWorker, generate_task_sets

SEED = 7
L2_PREFIXES = tuple(ALLOWED_MUTATIONS[AutonomyLevel.PROMPT_SKILL_ROUTING])


def constraints(**overrides) -> ProposalConstraints:
    defaults = dict(
        allowed_path_prefixes=L2_PREFIXES,
        minimum_practical_effect=0.05,
        retention_set_ref=f"corpus://fixture/{SEED}/retention",
    )
    defaults.update(overrides)
    return ProposalConstraints(**defaults)


def strategy_table() -> TemplateMutationProposer:
    return TemplateMutationProposer(
        mutation_table={"/config/strategy": {"naive": ["robust"]}}
    )


def run_mission_cohort(
    ledger: EventLedger, bundle: SystemBundle, tasks
) -> list[str]:
    """Run one mission per task under *bundle* and ledger the evaluations."""
    compiler = MissionCompiler(ledger)
    runtime = DeterministicRuntime(ledger, FixtureWorker())
    mission_ids = []
    for task in tasks:
        request = MissionRequest(
            description=f"slugify {task.task_id}",
            inputs={"task_id": task.task_id, "text": task.input_text, "family": task.family},
        )
        spec = compiler.compile(request, bundle)
        run_id = runtime.start(spec, bundle)
        completed = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)[0]
        output = completed.payload["final_output"]["output"]
        record_mission_evaluation(
            ledger,
            mission_id=spec.mission_id,
            bundle_id=bundle.bundle_id,
            metric="task_success",
            value=exact_match(task.expected_output, output),
            task_family=task.family,
            difficulty=task.difficulty,
        )
        mission_ids.append(spec.mission_id)
    return mission_ids


@pytest.fixture()
def ledger() -> EventLedger:
    return EventLedger(":memory:")


@pytest.fixture()
def naive_bundle() -> SystemBundle:
    return SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "naive"})


# -- diagnoser -------------------------------------------------------------------


def test_diagnoser_finds_the_hard_slugify_signature(
    ledger: EventLedger, naive_bundle: SystemBundle
) -> None:
    tasks = generate_task_sets(SEED)["development"]
    run_mission_cohort(ledger, naive_bundle, tasks)
    before = ledger.count()

    diagnoses = EvidenceDiagnoser(ledger).diagnose()

    assert ledger.count() == before  # strictly read-only (report 10.4)
    assert len(diagnoses) == 1
    diagnosis = diagnoses[0]
    assert diagnosis.task_family == "slugify"
    assert diagnosis.difficulty == "hard"
    assert diagnosis.bundle_id == naive_bundle.bundle_id
    assert diagnosis.config == {"strategy": "naive"}
    assert diagnosis.failure_rate == 1.0
    assert diagnosis.n_failures >= 3
    recorded_ids = {e.event_id for e in ledger.query(event_type=EventTypes.METRIC_COMPUTED)}
    assert set(diagnosis.evidence_event_ids) <= recorded_ids


def test_diagnoser_requires_support_and_attributable_config(ledger: EventLedger) -> None:
    # Two failures (below min_support=3) and no MISSION_STARTED config at all.
    for i in range(2):
        record_mission_evaluation(
            ledger,
            mission_id=f"mis_{i}",
            bundle_id="sha256:" + "0" * 64,
            metric="task_success",
            value=0.0,
            task_family="slugify",
            difficulty="hard",
        )
    assert EvidenceDiagnoser(ledger).diagnose() == []


# -- proposer seam ------------------------------------------------------------------


def diagnosed(ledger: EventLedger, bundle: SystemBundle):
    run_mission_cohort(ledger, bundle, generate_task_sets(SEED)["development"])
    return EvidenceDiagnoser(ledger).diagnose()


def test_template_proposer_builds_a_falsifiable_proposal(
    ledger: EventLedger, naive_bundle: SystemBundle
) -> None:
    diagnoses = diagnosed(ledger, naive_bundle)
    proposer = strategy_table()
    assert isinstance(proposer, ProposerLike)

    proposals = proposer.propose(diagnoses, naive_bundle, constraints())

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.parent_bundle_id == naive_bundle.bundle_id
    assert proposal.changes == [
        FieldChange(field_path="/config/strategy", old_value="naive", new_value="robust")
    ]
    assert proposal.evidence_refs == list(diagnoses[0].evidence_event_ids)
    assert proposal.hypothesis and proposal.rollback_condition
    assert proposal.minimum_practical_effect == 0.05
    assert proposal.proposer.id == "optimizer.template-mutation"
    assert proposal.deployment_scope.task_types == ["slugify"]


def test_proposer_cannot_target_outside_the_mutation_surface(
    ledger: EventLedger, naive_bundle: SystemBundle
) -> None:
    rogue = TemplateMutationProposer(
        mutation_table={"/evaluation_profile_ref": {"eval-profile://default/v1": ["weaker"]}}
    )
    with pytest.raises(ProposalPolicyViolation, match="outside the allowed"):
        rogue.propose([], naive_bundle, constraints())


def test_rejected_diff_needs_new_evidence_to_return(
    ledger: EventLedger, naive_bundle: SystemBundle
) -> None:
    diagnoses = diagnosed(ledger, naive_bundle)
    proposer = strategy_table()
    proposal = proposer.propose(diagnoses, naive_bundle, constraints())[0]
    rejected = RejectedDiff(
        digest=diff_digest(list(proposal.changes)),
        evidence_event_ids=frozenset(proposal.evidence_refs),
    )

    # Same evidence, same diff: convergence on a rejected candidate (12.5).
    silenced = proposer.propose(
        diagnoses, naive_bundle, constraints(rejected_diffs=(rejected,))
    )
    assert silenced == []

    # A fresh failing cohort produces NEW evidence ids: admissible again.
    run_mission_cohort(
        ledger, naive_bundle, generate_task_sets(SEED + 1)["development"]
    )
    fresh = EvidenceDiagnoser(ledger).diagnose()
    revived = proposer.propose(
        fresh, naive_bundle, constraints(rejected_diffs=(rejected,))
    )
    assert len(revived) == 1


def test_stale_diagnosis_from_other_lineage_is_ignored(
    ledger: EventLedger, naive_bundle: SystemBundle
) -> None:
    diagnoses = diagnosed(ledger, naive_bundle)
    other_parent = SystemBundle(
        workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "naive", "extra": 1}
    )
    assert strategy_table().propose(diagnoses, other_parent, constraints()) == []


def test_proposer_has_no_vault_access_by_policy() -> None:
    decision = PolicyDecisionPoint().decide(
        "holdout.read", "optimizer.template-mutation", "blind://vault/rotation-1", {}
    )
    assert decision.permit is False


# -- the full loop -------------------------------------------------------------------


def test_full_improvement_loop_from_cohort_to_canary(
    ledger: EventLedger, tmp_path
) -> None:
    signer = HMACSigner.load_or_create(tmp_path / "keys" / "signing.key")
    registry = BundleRegistry(tmp_path / "bundles", signer=signer)
    s0 = registry.sign(
        SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "naive"})
    )
    registry.register(s0)

    # 1. Mission cohort under frozen S0, evaluations ledgered.
    corpus = generate_task_sets(SEED)
    run_mission_cohort(ledger, s0, corpus["development"])

    # 2-3. Read-only diagnosis, then a typed proposal from that evidence.
    diagnoses = EvidenceDiagnoser(ledger).diagnose()
    proposals = strategy_table().propose(diagnoses, s0, constraints())
    proposal: ImprovementProposal = proposals[0]
    ledgered = {e.event_id for e in ledger.query()}
    assert set(proposal.evidence_refs) <= ledgered  # evidence-backed change (12.2)

    # 4. The fork is policy-checked; the proposer never touched the registry.
    s1 = registry.fork(s0, list(proposal.changes), allowed_path_prefixes=list(L2_PREFIXES))
    s1 = registry.sign(s1)
    registry.register(s1)
    assert s1.config["strategy"] == "robust"

    # 5. Matched paired experiment with the protected set sealed blind.
    vault = HoldoutVault(secret=b"improvement-loop-vault-secret-01")
    vault_ref = vault.seal(
        "loop-rotation-1",
        list(corpus["protected"]),
        scorer=lambda task, output: exact_match(task.expected_output, output),
    )
    controller = ExperimentController(ledger, vault=vault)
    record = controller.design(
        proposal,
        control_bundle=s0,
        candidate_bundles=[s1],
        task_set_refs=TaskSetRefs(
            development=f"corpus://fixture/{SEED}/development",
            protected=vault_ref,
            retention=f"corpus://fixture/{SEED}/retention",
            adversarial=f"corpus://fixture/{SEED}/adversarial",
        ),
        budgets=ExperimentBudget(per_arm_cost_usd=1.0, max_runs=200),
        seed=SEED,
        minimum_practical_effect=proposal.minimum_practical_effect,
    )
    worker = FixtureWorker()

    def run_arm(bundle: SystemBundle, task, seed: int) -> str:
        task_input = {
            "task_id": task.task_id,
            "text": task.input_text,
            "family": getattr(task, "family", "slugify"),
        }
        return worker.invoke(task_input, bundle.config, seed)["output"]

    results = controller.run(
        record,
        {"control": s0, "candidate_a": s1},
        {
            TaskSetRole.DEVELOPMENT: list(corpus["development"]),
            TaskSetRole.RETENTION: list(corpus["retention"]),
            TaskSetRole.ADVERSARIAL: list(corpus["adversarial"]),
        },
        run_arm,
        lambda task, output: exact_match(task.expected_output, output),
    )
    analyses = controller.analyze(record, results, seed=SEED)["candidate_a"]
    assert analyses[TaskSetRole.PROTECTED_HOLDOUT].ci_low > proposal.minimum_practical_effect
    assert analyses[TaskSetRole.RETENTION].losses == 0

    # 6. The gate: quarantined without a human, canary with one; the
    #    proposer itself can never supply the authorization.
    metrics = EvaluationHarness().aggregate(results["candidate_a"])
    gate = PromotionGate()
    full_diff = registry.diff(s0.bundle_id, s1.bundle_id)
    diff = BundleDiff(
        parent_bundle_id=full_diff.parent_bundle_id,
        child_bundle_id=full_diff.child_bundle_id,
        changes=[c for c in full_diff.changes if c.field_path not in FORK_BOOKKEEPING_PATHS],
    )
    unapproved = gate.run(
        proposal, s0, s1, diff, analyses, metrics, [], allowed_path_prefixes=list(L2_PREFIXES)
    )
    assert unapproved.action is DecisionAction.QUARANTINE

    self_approved = gate.run(
        proposal,
        s0,
        s1,
        diff,
        analyses,
        metrics,
        [
            ApprovalRecord(
                approver=proposal.proposer.id,  # the optimizer approving itself
                tier=ApprovalTier.A1_SINGLE_REVIEWER,
                candidate_bundle_id=s1.bundle_id,
            )
        ],
        allowed_path_prefixes=list(L2_PREFIXES),
    )
    assert self_approved.action is not DecisionAction.CANARY

    approved = gate.run(
        proposal,
        s0,
        s1,
        diff,
        analyses,
        metrics,
        [
            ApprovalRecord(
                approver="human:owner",
                tier=ApprovalTier.A1_SINGLE_REVIEWER,
                candidate_bundle_id=s1.bundle_id,
            )
        ],
        allowed_path_prefixes=list(L2_PREFIXES),
    )
    assert approved.action is DecisionAction.CANARY
    assert approved.rollback_target == s0.bundle_id
