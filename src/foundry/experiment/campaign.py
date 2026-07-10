"""Registered paired-experiment campaign runner (STAGE1_PROTOCOL.md section 3,
report 19.1 exit criterion "20+ paired candidate/control experiments
reproducible").

A campaign is a pre-registered, fixed-size, single-pass series of paired
control-vs-candidate experiments over the deterministic fixture domains.
The runner executes each experiment at full protocol standard -- proposal
pre-registered on the record, holdout sealed first, leakage check before
results open, matched seeded arms, paired bootstrap analysis, G0-G9 gate
WITHOUT human approval (a campaign measures; it does not deploy) -- and
returns a deterministic results payload: identical seeds produce an
identical payload on any machine, which is what makes the campaign
archivable and independently checkable.

Random experiment identifiers and wall-clock times are deliberately kept
out of the payload; they live in the ledger events and the archive
metadata instead.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from foundry.contracts import (
    AutonomyLevel,
    BundleDiff,
    ChangeTarget,
    DeploymentScope,
    ExperimentBudget,
    FieldChange,
    ImprovementProposal,
    LedgerLike,
    ModuleRef,
    SystemBundle,
    TaskSetRefs,
    TaskSetRole,
)
from foundry.evaluation import DeterministicTestService, EvaluationHarness, exact_match
from foundry.policy import ALLOWED_MUTATIONS
from foundry.promotion import PromotionGate
from foundry.workers import (
    CodingTask,
    DeterministicCodingWorker,
    FixtureWorker,
    generate_coding_task_sets,
    generate_task_sets,
    make_coding_run_arm,
)

from .controller import ExperimentController
from .vault import HoldoutVault

MINIMUM_PRACTICAL_EFFECT = 0.05
RETENTION_FLOOR = 0.0

#: The level-2 mutation surface the campaign proposals live inside.
CAMPAIGN_ALLOWED_PREFIXES: tuple[str, ...] = tuple(
    ALLOWED_MUTATIONS[AutonomyLevel.PROMPT_SKILL_ROUTING]
)

SLUGIFY_WORKFLOW = "workflow://fixture/v1"
CODING_WORKFLOW = "workflow://coding/v1"


@dataclass(frozen=True)
class CampaignExperimentSpec:
    domain: str  # "slugify" | "coding"
    seed: int


@dataclass(frozen=True)
class CampaignSpec:
    name: str
    preregistration_ref: str
    experiments: tuple[CampaignExperimentSpec, ...]
    minimum_practical_effect: float = MINIMUM_PRACTICAL_EFFECT
    retention_floor: float = RETENTION_FLOOR


def default_campaign_v1() -> CampaignSpec:
    """The registered v1 design: 12 slugify + 8 coding experiments
    (research/preregistrations/STAGE1_CAMPAIGN_V1.md)."""
    return CampaignSpec(
        name="stage1_campaign_v1",
        preregistration_ref="research/preregistrations/STAGE1_CAMPAIGN_V1.md",
        experiments=tuple(
            [CampaignExperimentSpec("slugify", seed) for seed in range(101, 113)]
            + [CampaignExperimentSpec("coding", seed) for seed in range(201, 209)]
        ),
    )


# -- per-domain wiring ---------------------------------------------------------------


@dataclass(frozen=True)
class _Domain:
    workflow_ref: str
    corpus: Callable[[int], dict[str, list[Any]]]
    run_arm: Callable[[SystemBundle, Any, int], str]
    score: Callable[[Any, str], float]


def _slugify_domain() -> _Domain:
    worker = FixtureWorker()

    def run_arm(bundle: SystemBundle, task: Any, seed: int) -> str:
        task_input = {
            "task_id": task.task_id,
            "text": task.input_text,
            "family": getattr(task, "family", "slugify"),
        }
        return worker.invoke(task_input, bundle.config, seed)["output"]

    return _Domain(
        workflow_ref=SLUGIFY_WORKFLOW,
        corpus=generate_task_sets,
        run_arm=run_arm,
        score=lambda task, output: exact_match(task.expected_output, output),
    )


def _coding_domain() -> _Domain:
    service = DeterministicTestService()

    def score(task: CodingTask, output: str) -> float:
        return service.score(task, output)

    return _Domain(
        workflow_ref=CODING_WORKFLOW,
        corpus=generate_coding_task_sets,
        run_arm=make_coding_run_arm(DeterministicCodingWorker()),
        score=score,
    )


_DOMAINS: dict[str, Callable[[], _Domain]] = {
    "slugify": _slugify_domain,
    "coding": _coding_domain,
}


# -- runner ---------------------------------------------------------------------------


def _campaign_proposal(
    spec: CampaignSpec, experiment: CampaignExperimentSpec, parent: SystemBundle
) -> ImprovementProposal:
    return ImprovementProposal(
        parent_bundle_id=parent.bundle_id,
        target=ChangeTarget(field_path="/config/strategy"),
        current_behavior=(
            f"naive repair strategy fails hard {experiment.domain} tasks by design "
            "(known fixture ground truth)"
        ),
        hypothesis=(
            f"The robust strategy removes hard-task failures on the {experiment.domain} "
            "domain without regressing retained easy-task behavior."
        ),
        changes=[FieldChange(field_path="/config/strategy", old_value="naive", new_value="robust")],
        expected_effects={"task_success": 0.4},
        risks=["robust normalization may alter outputs the naive strategy already gets right"],
        autonomy_level=AutonomyLevel.PROMPT_SKILL_ROUTING,
        deployment_scope=DeploymentScope(task_types=[experiment.domain]),
        experiment_plan_ref=f"artifact://plan/{spec.name}",
        retention_set_ref=f"corpus://{experiment.domain}/{experiment.seed}/retention",
        minimum_practical_effect=spec.minimum_practical_effect,
        retention_floor=spec.retention_floor,
        rollback_condition=(
            "holdout ci_low below the minimum practical effect or any retention "
            "loss: roll back to the parent bundle"
        ),
        proposer=ModuleRef(id="optimizer.human-designed", version="1.0.0"),
    )


def _vault_secret(spec: CampaignSpec, experiment: CampaignExperimentSpec) -> bytes:
    seed_material = f"{spec.name}:{experiment.domain}:{experiment.seed}".encode()
    return hashlib.sha256(seed_material).digest()


def _analysis_row(analysis: Any) -> dict[str, Any]:
    return {
        "n_pairs": analysis.n_pairs,
        "mean_delta": analysis.mean_delta,
        "ci_low": analysis.ci_low,
        "ci_high": analysis.ci_high,
        "wins": analysis.wins,
        "losses": analysis.losses,
        "ties": analysis.ties,
    }


def run_campaign_experiment(
    spec: CampaignSpec, experiment: CampaignExperimentSpec, ledger: LedgerLike
) -> dict[str, Any]:
    """Run one registered experiment; return its deterministic result row."""
    domain = _DOMAINS[experiment.domain]()
    corpus = domain.corpus(experiment.seed)

    s0 = SystemBundle(workflow_ref=domain.workflow_ref, config={"strategy": "naive"})
    s1 = SystemBundle(
        workflow_ref=domain.workflow_ref,
        config={"strategy": "robust"},
        parent_bundle_id=s0.bundle_id,
    )
    proposal = _campaign_proposal(spec, experiment, s0)

    # Holdout sealed before the run (protocol 3.3); leakage check before results open.
    vault = HoldoutVault(secret=_vault_secret(spec, experiment))
    vault_name = f"{spec.name}-{experiment.domain}-{experiment.seed}"
    vault_ref = vault.seal(vault_name, list(corpus["protected"]), scorer=domain.score)
    leakage_hits = vault.leakage_check(
        vault_name, [proposal.hypothesis, proposal.current_behavior]
    )

    controller = ExperimentController(ledger, vault=vault)
    record = controller.design(
        proposal,
        control_bundle=s0,
        candidate_bundles=[s1],
        task_set_refs=TaskSetRefs(
            development=f"corpus://{experiment.domain}/{experiment.seed}/development",
            protected=vault_ref,
            retention=f"corpus://{experiment.domain}/{experiment.seed}/retention",
            adversarial=f"corpus://{experiment.domain}/{experiment.seed}/adversarial",
        ),
        budgets=ExperimentBudget(per_arm_cost_usd=1.0, max_runs=200),
        seed=experiment.seed,
        minimum_practical_effect=spec.minimum_practical_effect,
    )
    open_roles = {
        TaskSetRole.DEVELOPMENT: list(corpus["development"]),
        TaskSetRole.RETENTION: list(corpus["retention"]),
        TaskSetRole.ADVERSARIAL: list(corpus["adversarial"]),
    }
    bundles = {"control": s0, "candidate_a": s1}
    results = controller.run(record, bundles, open_roles, domain.run_arm, domain.score)
    analyses = controller.analyze(record, results, seed=experiment.seed)["candidate_a"]

    # Rerun agreement (gate G7): execute the candidate development arm again.
    rerun = controller.run(record, bundles, open_roles, domain.run_arm, domain.score)
    agreement = 1.0 if rerun == results else 0.0

    metrics = EvaluationHarness().aggregate(results["candidate_a"])
    decision = PromotionGate().run(
        proposal,
        s0,
        s1,
        BundleDiff(
            parent_bundle_id=s0.bundle_id,
            child_bundle_id=s1.bundle_id,
            changes=list(proposal.changes),
        ),
        analyses,
        metrics,
        [],  # no approval: a campaign measures, it does not deploy
        allowed_path_prefixes=list(CAMPAIGN_ALLOWED_PREFIXES),
        rerun_agreement=agreement,
    )
    return {
        "domain": experiment.domain,
        "seed": experiment.seed,
        "control_bundle_id": s0.bundle_id,
        "candidate_bundle_id": s1.bundle_id,
        "leakage_hits": len(leakage_hits),
        "rerun_agreement": agreement,
        "roles": {role.value: _analysis_row(a) for role, a in sorted(analyses.items())},
        "safety_critical_violations": metrics.safety_critical_violations,
        "gate_action": decision.action.value,
        "gates_failed": [g.gate.value for g in decision.failed_gates()],
    }


def run_campaign(spec: CampaignSpec, ledger: LedgerLike) -> dict[str, Any]:
    """Run the registered campaign; return the deterministic results payload."""
    rows = [run_campaign_experiment(spec, experiment, ledger) for experiment in spec.experiments]

    def aggregate(domain: str) -> dict[str, Any]:
        domain_rows = [r for r in rows if r["domain"] == domain]
        if not domain_rows:
            return {}
        return {
            "n_experiments": len(domain_rows),
            "mean_dev_delta": sum(r["roles"]["development"]["mean_delta"] for r in domain_rows)
            / len(domain_rows),
            "min_holdout_ci_low": min(r["roles"]["protected"]["ci_low"] for r in domain_rows),
            "total_retention_losses": sum(r["roles"]["retention"]["losses"] for r in domain_rows),
            "total_leakage_hits": sum(r["leakage_hits"] for r in domain_rows),
            "gate_actions": sorted({r["gate_action"] for r in domain_rows}),
        }

    return {
        "campaign": spec.name,
        "preregistration_ref": spec.preregistration_ref,
        "n_experiments": len(rows),
        "experiments": rows,
        "aggregates": {domain: aggregate(domain) for domain in sorted({r["domain"] for r in rows})},
    }
