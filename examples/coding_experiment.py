"""Paired candidate-vs-control experiment on executable-test coding tasks.

The coding-domain companion to ``examples/quickstart.py``: same control
plane, but success is decided by RUNNING each task's checks in an
ephemeral workspace (report 10.2 deterministic test service), not by
string comparison. Run it with:  python examples/coding_experiment.py
"""

from foundry.contracts import (
    AutonomyLevel,
    ChangeTarget,
    ExperimentBudget,
    FieldChange,
    ImprovementProposal,
    ModuleRef,
    SystemBundle,
    TaskSetRefs,
    TaskSetRole,
)
from foundry.evaluation import DeterministicTestService
from foundry.experiment import ExperimentController, HoldoutVault
from foundry.ledger import EventLedger
from foundry.workers import DeterministicCodingWorker, generate_coding_task_sets, make_coding_run_arm

SEED = 42

# 1. A deterministic corpus of tiny buggy repositories with assertion scripts.
corpus = generate_coding_task_sets(SEED)

# 2. Control S0 repairs only off-by-one boundaries; candidate S1 adds the
#    comparison repair. The only difference is one typed config change.
s0 = SystemBundle(workflow_ref="workflow://coding/v1", config={"strategy": "naive"})
s1 = SystemBundle(
    workflow_ref="workflow://coding/v1",
    config={"strategy": "robust"},
    parent_bundle_id=s0.bundle_id,
)

proposal = ImprovementProposal(
    parent_bundle_id=s0.bundle_id,
    target=ChangeTarget(field_path="/config/strategy"),
    hypothesis="The comparison repair fixes exclusive-threshold defects without regressions.",
    changes=[FieldChange(field_path="/config/strategy", old_value="naive", new_value="robust")],
    autonomy_level=AutonomyLevel.PROMPT_SKILL_ROUTING,
    experiment_plan_ref="artifact://plan/coding-example",
    retention_set_ref=f"corpus://coding/{SEED}/retention",
    minimum_practical_effect=0.05,
    rollback_condition="holdout ci_low below the effect floor or any retention loss",
    proposer=ModuleRef(id="optimizer.human-designed", version="0.1.0"),
)

# 3. Protected tasks live in the vault: candidates only ever see blind
#    handles and redacted inputs; scoring happens inside (report 14.1).
service = DeterministicTestService()
vault = HoldoutVault(secret=b"example-secret-do-not-use-in-lab")
vault_ref = vault.seal("coding-example", list(corpus["protected"]), scorer=service.score)

# 4. Design and run the matched experiment: same tasks, same order, same
#    per-task seeds in every arm (report 13.4).
ledger = EventLedger(":memory:")
controller = ExperimentController(ledger, vault=vault)
record = controller.design(
    proposal,
    control_bundle=s0,
    candidate_bundles=[s1],
    task_set_refs=TaskSetRefs(
        development=f"corpus://coding/{SEED}/development",
        protected=vault_ref,
        retention=f"corpus://coding/{SEED}/retention",
        adversarial=f"corpus://coding/{SEED}/adversarial",
    ),
    budgets=ExperimentBudget(per_arm_cost_usd=1.0, max_runs=100),
    seed=SEED,
    minimum_practical_effect=0.05,
)
results = controller.run(
    record,
    {"control": s0, "candidate_a": s1},
    {
        TaskSetRole.DEVELOPMENT: list(corpus["development"]),
        TaskSetRole.RETENTION: list(corpus["retention"]),
        TaskSetRole.ADVERSARIAL: list(corpus["adversarial"]),
    },
    make_coding_run_arm(DeterministicCodingWorker()),
    service.score,
)

# 5. Paired analysis: the candidate must win on evidence, not impressions.
analyses = controller.analyze(record, results, seed=SEED)["candidate_a"]
for role, analysis in analyses.items():
    print(
        f"{role.value:>12}: n={analysis.n_pairs:2d} mean_delta={analysis.mean_delta:+.3f} "
        f"ci=[{analysis.ci_low:+.3f}, {analysis.ci_high:+.3f}] "
        f"w/l/t={analysis.wins}/{analysis.losses}/{analysis.ties}"
    )
print(f"\nledger recorded {ledger.count()} canonical events; every check ran in a receipted workspace")
