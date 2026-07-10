"""Foundry command line: demo, verify, lineage and replay (report 19.5, 22.2).

The CLI wires every Stage-1 package into the complete story -- compile,
run, propose, fork, experiment, gate, deploy, roll back -- with all
persistent state under one root directory (``ledger.db``, ``artifacts/``,
``bundles/``, ``keys/``). ``verify`` and ``replay`` implement the report's
first success criterion (22.2): an independent researcher can reproduce a
mission and the candidate-comparison *statistics* (paired deltas, means,
win/loss counts, bootstrap intervals) from the bundle, the events and the
artifacts alone -- the analysis is order-canonical, so no state private to
the original process is needed. Verifying producer *signatures* (events,
bundles) additionally requires the signing key under ``keys/``; a missing
key is reported as its own outcome, never as forgery, and the verifier
never mints keys into the root it audits.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from foundry.artifacts import ArtifactStore
from foundry.compiler import MissionCompiler
from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    AutonomyLevel,
    BundleDiff,
    ChangeTarget,
    DecisionAction,
    DeploymentRecord,
    Event,
    EventTypes,
    ExperimentArm,
    ExperimentBudget,
    ExperimentRecord,
    FieldChange,
    ImprovementProposal,
    MetricVector,
    MissionRequest,
    MissionSpec,
    ModuleRef,
    PairedAnalysis,
    PromotionDecision,
    PromotionStatus,
    RollbackRecord,
    SystemBundle,
    TaskSetRefs,
    TaskSetRole,
    sha256_hex,
)
from foundry.deployment import MODE_CANARY, MODE_SCOPED_PRODUCTION, DeploymentController
from foundry.evaluation import EvaluationHarness, exact_match
from foundry.experiment import (
    VAULT_REF_PREFIX,
    BlindTaskView,
    ExperimentController,
    HoldoutVault,
    derive_seed,
    summarize,
)
from foundry.ledger import EventLedger
from foundry.policy import ALLOWED_MUTATIONS, PolicyDecisionPoint
from foundry.promotion import PromotionGate, verify_decision_signature
from foundry.registry import BundleRegistry, HMACSigner, IntegrityError
from foundry.runtime import FIXTURE_WORKFLOW_REF, DeterministicRuntime
from foundry.workers import FixtureTask, FixtureWorker, generate_task_sets

Printer = Callable[[str], None]

LEDGER_FILE = "ledger.db"
ARTIFACTS_DIR = "artifacts"
BUNDLES_DIR = "bundles"
KEYS_DIR = "keys"
SIGNING_KEY_FILE = "signing.key"
KEY_ID = "foundry-dev"
MINIMUM_PRACTICAL_EFFECT = 0.05

#: Identity fields written by ``BundleRegistry.fork`` itself. They appear in
#: the raw registry diff but are lineage bookkeeping, not proposed behavior
#: changes: G0 verifies ``parent_bundle_id`` structurally and the semantic
#: version bump is mechanical, so the promotion diff excludes both.
FORK_BOOKKEEPING_PATHS = frozenset({"/parent_bundle_id", "/semantic_version"})

_OPEN_ROLES = (TaskSetRole.DEVELOPMENT, TaskSetRole.RETENTION, TaskSetRole.ADVERSARIAL)

_DEMO_MISSION_TEXTS = (
    "Hello  Foundry -- Stage One!",
    "Deterministic runtime demo",
    "Paired   experiments, please.",
)


# -- shared store wiring -----------------------------------------------------


#: Vault secret used by verify/replay paths when ``keys/`` is absent. Any
#: secret reproduces the same candidate-comparison statistics (the analysis
#: is order-canonical); a fixed one keeps keyless replays deterministic.
FALLBACK_VAULT_SECRET = hashlib.sha256(b"foundry-holdout-vault:no-key").digest()


@dataclass
class Stores:
    """Every persistent component of one foundry root, opened together.

    ``signer`` is None when the root has no ``keys/signing.key`` and the
    stores were opened read-only for verification (``create=False``):
    signatures then cannot be verified, but nothing else is affected.
    """

    root: Path
    ledger: EventLedger
    artifacts: ArtifactStore
    registry: BundleRegistry
    signer: HMACSigner | None
    vault_secret: bytes

    def close(self) -> None:
        self.ledger.close()


def open_stores(root: Path, *, create: bool = True) -> Stores:
    """Open the ledger, artifact store, registry and keys under *root*.

    ``create=True`` (the demo path) generates a signing key on first use.
    ``create=False`` (verify/replay/recompute paths) never writes into
    ``keys/``: a verifier must not mutate the evidence root it audits, so
    a missing key yields ``signer=None`` and the fallback vault secret.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    key_path = root / KEYS_DIR / SIGNING_KEY_FILE
    if create:
        signer: HMACSigner | None = HMACSigner.load_or_create(key_path, key_id=KEY_ID)
    else:
        try:
            signer = HMACSigner.load(key_path, key_id=KEY_ID)
        except FileNotFoundError:
            signer = None
    # The vault secret is derived from the persisted signing key so that a
    # later process over the same root regenerates identical blind handles.
    if key_path.exists():
        vault_secret = hashlib.sha256(b"foundry-holdout-vault:" + key_path.read_bytes()).digest()
    else:
        vault_secret = FALLBACK_VAULT_SECRET
    return Stores(
        root=root,
        ledger=EventLedger(root / LEDGER_FILE, producer="foundry-cli", signer=signer),
        artifacts=ArtifactStore(root / ARTIFACTS_DIR),
        registry=BundleRegistry(root / BUNDLES_DIR, signer=signer),
        signer=signer,
        vault_secret=vault_secret,
    )


def _deployment_controller(stores: Stores) -> DeploymentController:
    """Deployment controller wired to this root's trust anchors."""
    signer = stores.signer

    def verify_decision(decision: PromotionDecision) -> bool:
        return signer is not None and verify_decision_signature(decision, signer)

    return DeploymentController(
        stores.ledger,
        verify_signatures=stores.registry.verify_signatures,
        verify_decision=verify_decision,
    )


# -- fixture arm execution (shared by demo, verify and the capstone test) ----


def task_input_for(task: FixtureTask | BlindTaskView) -> dict[str, str]:
    return {"task_id": task.task_id, "text": task.input_text, "family": task.family}


def run_fixture_arm(bundle: SystemBundle, task: FixtureTask | BlindTaskView, seed: int) -> str:
    """RunArm callable: one worker invocation under the frozen bundle config.

    For protected tasks *task* is the redacted ``BlindTaskView`` (its
    ``task_id`` is the blind handle); the worker only ever needs inputs.
    """
    return FixtureWorker().invoke(task_input_for(task), bundle.config, seed)["output"]


def score_fixture(task: FixtureTask, output: str) -> float:
    """Score callable: deterministic exact match against the corpus ground truth."""
    return exact_match(task.expected_output, output)


def _arm_scores(
    bundle: SystemBundle,
    tasks_by_role: dict[TaskSetRole, list[FixtureTask]],
    vault: HoldoutVault,
    vault_name: str,
    base_seed: int,
) -> dict[TaskSetRole, dict[str, float]]:
    """Re-execute one arm exactly as the experiment controller does.

    Open roles are keyed by task id; the protected role is executed only via
    ``run_blind`` (redacted view in, score out) and keyed by blind handle,
    mirroring :meth:`foundry.experiment.ExperimentController.run` without
    emitting events.
    """

    def scored(task: FixtureTask) -> float:
        return score_fixture(task, run_fixture_arm(bundle, task, derive_seed(base_seed, task.task_id)))

    def run_view(view: BlindTaskView) -> str:
        return run_fixture_arm(bundle, view, derive_seed(base_seed, view.task_id))

    scores: dict[TaskSetRole, dict[str, float]] = {}
    for role in TaskSetRole:
        if role is TaskSetRole.PROTECTED_HOLDOUT:
            scores[role] = {
                handle: vault.run_blind(vault_name, handle, run_view)
                for handle in vault.handles(vault_name)
            }
        else:
            scores[role] = {task.task_id: scored(task) for task in tasks_by_role[role]}
    return scores


def _rerun_agreement(bundle: SystemBundle, tasks: list[FixtureTask], base_seed: int) -> float:
    """G7 evidence: fraction of identical outputs across two executions."""
    runs = [
        [run_fixture_arm(bundle, task, derive_seed(base_seed, task.task_id)) for task in tasks]
        for _ in range(2)
    ]
    return sum(1 for a, b in zip(runs[0], runs[1], strict=True) if a == b) / len(tasks)


# -- demo ---------------------------------------------------------------------


@dataclass
class DemoResult:
    """Everything the demo produced, for programmatic assertions (tests)."""

    root: Path
    seed: int
    s0: SystemBundle
    s1: SystemBundle
    proposal: ImprovementProposal
    diff: BundleDiff
    record: ExperimentRecord
    candidate_arm_id: str
    results: dict[str, dict[TaskSetRole, dict[str, float]]]
    analyses: dict[str, dict[TaskSetRole, PairedAnalysis]]
    metrics: MetricVector
    rerun_agreement: float
    quarantine_decision: PromotionDecision
    canary_decision: PromotionDecision
    approval: ApprovalRecord
    canary_deployment: DeploymentRecord
    production_deployment: DeploymentRecord
    rollback: RollbackRecord
    reactivation: DeploymentRecord
    mission_ids: list[str]
    chain_ok: bool
    event_count: int
    artifact_count: int
    bundle_count: int
    active_bundle_id: str | None
    allowed_prefixes: list[str]
    minimum_practical_effect: float


def _expect(condition: bool, message: str) -> None:
    """The demo is also a self-check: an off-script outcome stops the story."""
    if not condition:
        raise RuntimeError(f"demo invariant violated: {message}")


def run_demo(root: Path, seed: int = 42, out: Printer = print) -> DemoResult:
    """Run the complete Stage-1 story end-to-end under *root* (report 19.5)."""
    stores = open_stores(root)
    try:
        return _run_demo(stores, seed, out)
    finally:
        stores.close()


def _run_demo(stores: Stores, seed: int, out: Printer) -> DemoResult:
    ledger, registry, artifacts = stores.ledger, stores.registry, stores.artifacts

    out(f"Agent Foundry Stage-1 demo  (root={stores.root}, seed={seed})")

    # (1) Root bundle S0: naive strategy, signed, registered.
    out("\n[1/9] Create, sign and register the root bundle S0 (strategy=naive)")
    s0 = registry.sign(
        SystemBundle(
            workflow_ref=FIXTURE_WORKFLOW_REF,
            config={"strategy": "naive"},
            status=PromotionStatus.SCOPED_PRODUCTION,
        )
    )
    registry.register(s0)
    out(f"  S0 = {s0.bundle_id} v{s0.semantic_version} [{s0.status.value}], signed by {KEY_ID}")

    # (2) Three fixture missions under S0.
    out("\n[2/9] Compile and run 3 fixture missions under S0")
    compiler = MissionCompiler(ledger)
    runtime = DeterministicRuntime(ledger, FixtureWorker(), artifact_store=artifacts)
    mission_ids: list[str] = []
    for i, text in enumerate(_DEMO_MISSION_TEXTS, start=1):
        request = MissionRequest(
            description=f"Slugify demo input {i}",
            inputs={"task_id": f"demo-{i:02d}", "text": text, "family": "slugify"},
        )
        spec = compiler.compile(request, s0)
        run_id = runtime.start(spec, s0)
        completed = ledger.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)[0]
        mission_ids.append(spec.mission_id)
        out(
            f"  mission {spec.mission_id}: {text!r} -> "
            f"{completed.payload['final_output']['output']!r} "
            f"(digest {completed.payload['output_digest'][:19]}...)"
        )

    # (3) The improvement proposal: one falsifiable hypothesis, typed diff.
    out("\n[3/9] Build the improvement proposal (autonomy level 2)")
    change = FieldChange(field_path="/config/strategy", old_value="naive", new_value="robust")
    plan_ref = artifacts.put_text(
        "Paired experiment plan: control=parent (naive) vs candidate (robust) over the "
        f"seed-{seed} fixture corpus; primary endpoint paired task-success delta; "
        "protected holdout scored blind; decision rule = Stage-1 G0-G9 promotion gate.",
        media_type="text/plain; charset=utf-8",
    )
    proposal = ImprovementProposal(
        parent_bundle_id=s0.bundle_id,
        target=ChangeTarget(field_path="/config/strategy"),
        current_behavior=(
            "naive slugify lowercases and replaces single spaces; it fails on punctuation, "
            "unicode dashes and repeated whitespace"
        ),
        hypothesis=(
            "Robust text normalization (dash folding, punctuation stripping, whitespace "
            "collapsing) reduces hard-task failures without regressing easy-task behavior."
        ),
        changes=[change],
        expected_effects={"task_success": 0.4},
        risks=["over-normalization could alter outputs the naive strategy already gets right"],
        autonomy_level=AutonomyLevel.PROMPT_SKILL_ROUTING,
        experiment_plan_ref=plan_ref,
        # Pre-registered retention set and thresholds (report 12.3): the
        # gate reads these from the proposal, never from call arguments.
        retention_set_ref=f"corpus://fixture/{seed}/retention",
        minimum_practical_effect=MINIMUM_PRACTICAL_EFFECT,
        retention_floor=0.0,
        rollback_condition=(
            "holdout ci_low below the minimum practical effect or any retention loss: "
            "roll back to the parent bundle"
        ),
        proposer=ModuleRef(id="optimizer.gepa", version="0.1.0"),
    )
    ledger.append(
        Event(
            event_type=EventTypes.PROPOSAL_SUBMITTED,
            system_bundle_id=s0.bundle_id,
            actor=proposal.proposer.id,
            subject=proposal.proposal_id,
            payload={"proposal": proposal.model_dump(mode="json")},
        )
    )
    out(f"  proposal {proposal.proposal_id}: {proposal.hypothesis!r}")
    out(f"  experiment plan artifact: {plan_ref}")

    # (4) Fork candidate S1 inside the PDP's level-2 mutation surface.
    out("\n[4/9] PDP check, then fork candidate S1 (strategy=robust)")
    pdp = PolicyDecisionPoint()
    fork_decision = pdp.decide(
        "bundle.fork",
        proposal.proposer.id,
        s0.bundle_id,
        {"autonomy_level": int(proposal.autonomy_level), "field_paths": [change.field_path]},
    )
    _expect(fork_decision.permit, f"PDP denied the fork: {fork_decision.reason}")
    allowed_prefixes = list(ALLOWED_MUTATIONS[AutonomyLevel.PROMPT_SKILL_ROUTING])
    out(f"  PDP: permit={fork_decision.permit} tier={fork_decision.approval_tier.value} "
        f"surface={allowed_prefixes}")
    s1 = registry.sign(registry.fork(s0, [change], allowed_path_prefixes=allowed_prefixes))
    registry.register(s1)
    out(f"  S1 = {s1.bundle_id} v{s1.semantic_version} [{s1.status.value}], parent=S0")

    # (5) Paired experiment: control S0 vs candidate S1, protected set sealed.
    out("\n[5/9] Design, run and analyze the paired experiment")
    corpus = generate_task_sets(seed)
    vault = HoldoutVault(stores.vault_secret)
    vault_name = f"protected-{seed}"
    vault_ref = vault.seal(vault_name, corpus["protected"], scorer=score_fixture)
    holdout_decision = pdp.decide("holdout.read", "experiment-controller", vault_ref, {})
    _expect(holdout_decision.permit, "PDP denied the experiment controller vault access")
    refs = TaskSetRefs(
        development=f"corpus://fixture/{seed}/development",
        protected=vault_ref,
        retention=f"corpus://fixture/{seed}/retention",
        adversarial=f"corpus://fixture/{seed}/adversarial",
    )
    controller = ExperimentController(ledger, vault=vault)
    record = controller.design(
        proposal,
        s0,
        [s1],
        refs,
        ExperimentBudget(),
        seed,
        minimum_practical_effect=MINIMUM_PRACTICAL_EFFECT,
    )
    leaks = controller.check_leakage(record, proposal)
    _expect(not leaks, f"protected task content leaked into the proposal: {leaks}")
    bundles_by_arm = {arm.arm_id: registry.get(arm.bundle_id) for arm in record.arms}
    tasks_by_role = {role: corpus[role.value] for role in _OPEN_ROLES}
    results = controller.run(record, bundles_by_arm, tasks_by_role, run_fixture_arm, score_fixture)
    analyses = controller.analyze(record, results, seed=seed)
    candidate_arm_id = next(arm.arm_id for arm in record.arms if not arm.is_control)
    out(f"  experiment {record.experiment_id}: arms={[arm.arm_id for arm in record.arms]}, "
        f"protected sealed as {vault_ref} ({len(corpus['protected'])} tasks, blind handles only)")
    out(f"  leakage check: {len(leaks)} hit(s)")
    for role, analysis in analyses[candidate_arm_id].items():
        out(
            f"  {role.value:>12}: n={analysis.n_pairs} mean_delta={analysis.mean_delta:+.3f} "
            f"ci=[{analysis.ci_low:+.3f}, {analysis.ci_high:+.3f}] "
            f"wins/losses/ties={analysis.wins}/{analysis.losses}/{analysis.ties}"
        )

    # (6) Metric vector + G0-G9 gate: quarantine without approval, canary with.
    out("\n[6/9] Aggregate metrics and run the G0-G9 promotion gate")
    agreement = _rerun_agreement(bundles_by_arm[candidate_arm_id], corpus["development"], seed)
    metrics = EvaluationHarness().aggregate(
        results[candidate_arm_id], cost_usd=0.0, reproducibility=agreement
    )
    full_diff = registry.diff(s0.bundle_id, s1.bundle_id)
    diff = BundleDiff(
        parent_bundle_id=full_diff.parent_bundle_id,
        child_bundle_id=full_diff.child_bundle_id,
        changes=[c for c in full_diff.changes if c.field_path not in FORK_BOOKKEEPING_PATHS],
    )
    gate = PromotionGate(signer=stores.signer)

    def run_gate(approvals: list[ApprovalRecord]) -> PromotionDecision:
        return gate.run(
            proposal,
            s0,
            s1,
            diff,
            analyses[candidate_arm_id],
            metrics,
            approvals,
            allowed_path_prefixes=allowed_prefixes,
            rerun_agreement=agreement,
        )

    quarantine_decision = run_gate([])
    _expect(
        quarantine_decision.action is DecisionAction.QUARANTINE,
        f"expected QUARANTINE without approval, got {quarantine_decision.action.value}",
    )
    ledger.append(
        Event(
            event_type=EventTypes.GOVERNANCE_DECISION,
            experiment_id=record.experiment_id,
            system_bundle_id=s1.bundle_id,
            actor="promotion-gate",
            subject=quarantine_decision.decision_id,
            payload={"decision": quarantine_decision.model_dump(mode="json")},
        )
    )
    out(f"  gate without approval -> {quarantine_decision.action.value} "
        f"({quarantine_decision.reason})")
    ledger.append(
        Event(
            event_type=EventTypes.APPROVAL_REQUESTED,
            system_bundle_id=s1.bundle_id,
            actor="promotion-gate",
            subject=proposal.proposal_id,
            payload={"required_tier": quarantine_decision.required_approval_tier.value},
        )
    )
    approval = ApprovalRecord(
        approver="human:owner",
        tier=ApprovalTier.A1_SINGLE_REVIEWER,
        candidate_bundle_id=s1.bundle_id,
        rationale="Reviewed paired evidence; robust normalization is a safe, scoped change.",
    )
    canary_decision = run_gate([approval])
    _expect(
        canary_decision.action is DecisionAction.CANARY,
        f"expected CANARY after approval, got {canary_decision.action.value}",
    )
    ledger.append(
        Event(
            event_type=EventTypes.GOVERNANCE_DECISION,
            experiment_id=record.experiment_id,
            system_bundle_id=s1.bundle_id,
            actor="promotion-gate",
            subject=canary_decision.decision_id,
            payload={"decision": canary_decision.model_dump(mode="json")},
        )
    )
    out(f"  human approval {approval.approval_id} by {approval.approver} "
        f"(tier {approval.tier.value})")
    out(f"  gate with approval -> {canary_decision.action.value} ({canary_decision.reason})")

    # (7) Deployment: canary first, then scoped production.
    out("\n[7/9] Deploy: canary, then scoped production")
    deployer = _deployment_controller(stores)
    canary_deployment = deployer.activate(canary_decision, s1, [approval], mode=MODE_CANARY)
    production_deployment = deployer.activate(
        canary_decision, s1, [approval], mode=MODE_SCOPED_PRODUCTION
    )
    out(f"  canary deployment {canary_deployment.deployment_id} -> active={deployer.active_bundle_id()}")
    out(f"  scoped production {production_deployment.deployment_id} "
        f"-> active={deployer.active_bundle_id()}")

    # (8) Executable rollback to S0, then re-activation of S1.
    out("\n[8/9] Roll back to S0 (trigger='demo'), then re-activate S1")
    rollback = deployer.rollback(trigger="demo", initiated_by="human:owner")
    _expect(deployer.active_bundle_id() == s0.bundle_id, "rollback did not restore S0")
    out(f"  rollback {rollback.rollback_id}: {rollback.from_bundle_id} -> {rollback.to_bundle_id}")
    reactivation = deployer.activate(canary_decision, s1, [approval], mode=MODE_SCOPED_PRODUCTION)
    active_bundle_id = deployer.active_bundle_id()
    _expect(active_bundle_id == s1.bundle_id, "re-activation did not restore S1")
    out(f"  re-activation {reactivation.deployment_id} -> active={active_bundle_id}")

    # (9) Evidence integrity and final counts.
    out("\n[9/9] Verify the evidence chain and count the stores")
    chain_ok, chain_errors = ledger.verify_chain()
    _expect(chain_ok, f"ledger chain verification failed: {chain_errors}")
    artifact_count = len(_artifact_blobs(stores.root / ARTIFACTS_DIR))
    bundle_count = len(registry.list_ids())
    out(f"  ledger chain OK: {ledger.count()} events, hash chain intact")
    out(f"  stores: {ledger.count()} events, {artifact_count} artifacts, {bundle_count} bundles")
    out(f"  active bundle: {active_bundle_id}")
    out(f"\nDone. Try: foundry verify --root {stores.root}")
    out(f"     then: foundry replay --root {stores.root} --mission {mission_ids[0]}")

    return DemoResult(
        root=stores.root,
        seed=seed,
        s0=s0,
        s1=s1,
        proposal=proposal,
        diff=diff,
        record=record,
        candidate_arm_id=candidate_arm_id,
        results=results,
        analyses=analyses,
        metrics=metrics,
        rerun_agreement=agreement,
        quarantine_decision=quarantine_decision,
        canary_decision=canary_decision,
        approval=approval,
        canary_deployment=canary_deployment,
        production_deployment=production_deployment,
        rollback=rollback,
        reactivation=reactivation,
        mission_ids=mission_ids,
        chain_ok=chain_ok,
        event_count=ledger.count(),
        artifact_count=artifact_count,
        bundle_count=bundle_count,
        active_bundle_id=active_bundle_id,
        allowed_prefixes=allowed_prefixes,
        minimum_practical_effect=MINIMUM_PRACTICAL_EFFECT,
    )


# -- verify --------------------------------------------------------------------


def _artifact_blobs(store_root: Path) -> list[Path]:
    """Every content-addressed blob file under an artifact store root."""
    return sorted(p for p in store_root.glob("*/*/*") if p.is_file() and len(p.name) == 64)


def _recompute_analyses(stores: Stores) -> dict[str, dict[str, dict[TaskSetRole, PairedAnalysis]]]:
    """Recompute every experiment's paired analyses from persisted evidence.

    Uses only the ledger events (design, randomization and analysis seeds),
    the registered bundles and the seed-regenerated fixture corpus -- exactly
    what an independent researcher holds (report 22.2). The recorded
    statistics are order-canonical, so they reproduce even without the
    original vault secret (blind-handle *keys* then differ, values do not).
    """
    recomputed: dict[str, dict[str, dict[TaskSetRole, PairedAnalysis]]] = {}
    for designed in stores.ledger.query(event_type=EventTypes.EXPERIMENT_DESIGNED):
        experiment_id = designed.experiment_id
        assert experiment_id is not None
        randomized = stores.ledger.query(
            experiment_id=experiment_id, event_type=EventTypes.EXPERIMENT_RANDOMIZED
        )[0]
        analyzed = stores.ledger.query(
            experiment_id=experiment_id, event_type=EventTypes.EXPERIMENT_ANALYZED
        )[0]
        base_seed = int(randomized.payload["seed"])
        analysis_seed = int(analyzed.payload["seed"])
        corpus = generate_task_sets(base_seed)
        refs = TaskSetRefs.model_validate(designed.payload["task_sets"])
        if refs.protected is None or not refs.protected.startswith(VAULT_REF_PREFIX):
            raise ValueError(f"experiment {experiment_id} has no vault-sealed protected set")
        vault_name = refs.protected.removeprefix(VAULT_REF_PREFIX)
        vault = HoldoutVault(stores.vault_secret)
        vault.seal(vault_name, corpus["protected"], scorer=score_fixture)
        arms = [ExperimentArm.model_validate(a) for a in designed.payload["arms"]]
        tasks_by_role = {role: corpus[role.value] for role in _OPEN_ROLES}
        scores = {
            arm.arm_id: _arm_scores(
                stores.registry.get(arm.bundle_id), tasks_by_role, vault, vault_name, base_seed
            )
            for arm in arms
        }
        control_arm = next(arm for arm in arms if arm.is_control)
        recomputed[experiment_id] = {
            arm.arm_id: {
                role: summarize(
                    experiment_id,
                    arm.arm_id,
                    role,
                    scores[control_arm.arm_id][role],
                    scores[arm.arm_id][role],
                    seed=derive_seed(analysis_seed, f"{arm.arm_id}:{role.value}"),
                )
                for role in TaskSetRole
            }
            for arm in arms
            if not arm.is_control
        }
    return recomputed


def recompute_experiment_analyses(
    root: Path,
) -> dict[str, dict[str, dict[TaskSetRole, PairedAnalysis]]]:
    """Public replay entry point: ``{experiment_id: {arm_id: {role: analysis}}}``.

    Opens the stores read-only (never minting keys); without ``keys/`` the
    blind-handle keys differ but every recorded statistic reproduces.
    """
    stores = open_stores(root, create=False)
    try:
        return _recompute_analyses(stores)
    finally:
        stores.close()


def _analysis_matches_summary(analysis: PairedAnalysis, summary: dict) -> bool:
    return (
        analysis.n_pairs == summary["n_pairs"]
        and analysis.mean_delta == summary["mean_delta"]
        and [analysis.ci_low, analysis.ci_high] == summary["ci"]
        and analysis.wins == summary["wins"]
        and analysis.losses == summary["losses"]
        and analysis.ties == summary["ties"]
    )


def verify_root(root: Path, out: Printer = print) -> bool:
    """Re-verify every store under *root*; True iff all checks pass.

    Opens the stores read-only: a missing ``keys/signing.key`` is reported
    as its own distinct outcome (signatures unverifiable), never as
    forgery, and no key is ever minted into the root under audit.
    """
    ok = True

    def check(passed: bool, label: str) -> bool:
        nonlocal ok
        ok = ok and passed
        out(f"{'PASS' if passed else 'FAIL'} {label}")
        return passed

    stores = open_stores(root, create=False)
    try:
        key_present = stores.signer is not None
        chain_ok, chain_errors = stores.ledger.verify_chain()
        check(chain_ok, f"ledger hash chain ({stores.ledger.count()} events)")
        for error in chain_errors:
            out(f"     {error}")

        events = stores.ledger.all_events()
        if not key_present:
            check(False, "signing key present (keys/signing.key)")
            out("     signing key not present under this root; event and bundle")
            out("     signatures cannot be verified (this is not evidence of forgery)")
        else:
            assert stores.signer is not None
            bad_signatures = []
            for event in events:
                integrity = event.integrity
                if integrity is None or integrity.signature is None:
                    bad_signatures.append(f"{event.event_id}: unsigned")
                    continue
                _, _, signature = integrity.signature.partition(":")
                if not stores.signer.verify(integrity.digest.encode("utf-8"), signature):
                    bad_signatures.append(f"{event.event_id}: signature mismatch")
            check(not bad_signatures, f"event signatures ({len(events)} events)")
            for line in bad_signatures:
                out(f"     {line}")

        bundle_ids = stores.registry.list_ids()
        bundle_errors = []
        for bundle_id in bundle_ids:
            try:
                bundle = stores.registry.get(bundle_id)
            except IntegrityError as exc:
                bundle_errors.append(str(exc))
                continue
            if key_present and not stores.registry.verify_signatures(bundle):
                bundle_errors.append(f"{bundle_id}: signature set failed verification")
        label = (
            f"bundle content addresses and signatures ({len(bundle_ids)} bundles)"
            if key_present
            else f"bundle content addresses ({len(bundle_ids)} bundles; signatures skipped, no key)"
        )
        check(not bundle_errors, label)
        for line in bundle_errors:
            out(f"     {line}")

        blobs = _artifact_blobs(stores.root / ARTIFACTS_DIR)
        corrupt = [str(blob) for blob in blobs if sha256_hex(blob.read_bytes()) != blob.name]
        check(not corrupt, f"artifact content addresses ({len(blobs)} blobs)")
        for line in corrupt:
            out(f"     {line}")

        if chain_ok:
            recomputed = _recompute_analyses(stores)
            for experiment_id, per_arm in recomputed.items():
                analyzed = stores.ledger.query(
                    experiment_id=experiment_id, event_type=EventTypes.EXPERIMENT_ANALYZED
                )[0]
                recorded = analyzed.payload["arms"]
                matches = all(
                    _analysis_matches_summary(analysis, recorded[arm_id][role.value])
                    for arm_id, per_role in per_arm.items()
                    for role, analysis in per_role.items()
                )
                check(
                    matches,
                    f"experiment {experiment_id}: recomputed paired analysis matches the ledger",
                )
        else:
            check(False, "experiment re-analysis skipped: ledger chain is broken")
    finally:
        stores.close()
    return ok


# -- lineage ---------------------------------------------------------------------


def print_lineage(root: Path, out: Printer = print) -> None:
    """Print the registered bundle tree with statuses and the active marker."""
    stores = open_stores(root, create=False)
    try:
        active = _deployment_controller(stores).active_bundle_id()
        bundles = {bundle_id: stores.registry.get(bundle_id) for bundle_id in stores.registry.list_ids()}
        children: dict[str | None, list[str]] = {}
        for bundle_id, bundle in bundles.items():
            children.setdefault(bundle.parent_bundle_id, []).append(bundle_id)
        for sibling_ids in children.values():
            sibling_ids.sort()

        def emit(bundle_id: str, depth: int) -> None:
            bundle = bundles[bundle_id]
            marker = "  <- active" if bundle_id == active else ""
            out(f"{'    ' * depth}{bundle_id} v{bundle.semantic_version} [{bundle.status.value}]{marker}")
            for child_id in children.get(bundle_id, []):
                emit(child_id, depth + 1)

        roots = sorted(
            bundle_id for bundle_id, bundle in bundles.items() if bundle.parent_bundle_id not in bundles
        )
        if not roots:
            out("(no bundles registered)")
        for root_id in roots:
            emit(root_id, 0)
    finally:
        stores.close()


# -- coverage ----------------------------------------------------------------------


def report_coverage(root: Path, out: Printer = print) -> bool:
    """Event-coverage audit for the 95% exit criterion (report 19.1).

    Measures the persisted ledger against the demo-required vocabulary
    (a state root holds demo-shaped evidence; the interruption vocabulary
    is exercised and pinned by the fixture test suite instead). True iff
    the coverage ratio meets the exit-criterion threshold.
    """
    from foundry.evaluation.coverage import (
        DEMO_REQUIRED_EVENTS,
        EXIT_CRITERION_THRESHOLD,
        measure_coverage,
    )

    stores = open_stores(root, create=False)
    try:
        report = measure_coverage(stores.ledger, DEMO_REQUIRED_EVENTS)
    finally:
        stores.close()
    out(
        f"required event types: {len(report.required)}; observed of required: "
        f"{len(report.required) - len(report.missing)}; coverage {report.ratio:.0%} "
        f"(threshold {EXIT_CRITERION_THRESHOLD:.0%})"
    )
    for missing in report.missing:
        out(f"MISSING {missing}")
    verdict = report.passed()
    out(("PASS" if verdict else "FAIL") + " event coverage")
    return verdict


# -- replay ------------------------------------------------------------------------


def replay_mission(root: Path, mission_id: str, out: Printer = print) -> bool:
    """Re-execute a recorded mission from its frozen spec and bundle (report 22.2).

    The recorded MISSION_STARTED payload carries the exact spec and bundle;
    re-execution happens against a scratch in-memory ledger so the persisted
    evidence is never touched. True iff the replayed final output digest
    matches the recorded one.
    """
    stores = open_stores(root, create=False)
    try:
        started = stores.ledger.query(mission_id=mission_id, event_type=EventTypes.MISSION_STARTED)
        completed = stores.ledger.query(mission_id=mission_id, event_type=EventTypes.MISSION_COMPLETED)
        if not started or not completed:
            out(f"FAIL mission {mission_id}: no recorded start/completion events")
            return False
        spec = MissionSpec.model_validate(started[0].payload["spec"])
        bundle = SystemBundle.model_validate(started[0].payload["bundle"])
        recorded_digest = completed[-1].payload["output_digest"]
    finally:
        stores.close()

    scratch = EventLedger(":memory:", producer="foundry-replay")
    try:
        runtime = DeterministicRuntime(scratch, FixtureWorker())
        run_id = runtime.start(spec, bundle)
        replayed = scratch.query(run_id=run_id, event_type=EventTypes.MISSION_COMPLETED)[0]
        replayed_digest = replayed.payload["output_digest"]
    finally:
        scratch.close()

    match = replayed_digest == recorded_digest
    out(f"{'PASS' if match else 'FAIL'} mission {mission_id}: "
        f"recorded {recorded_digest} / replayed {replayed_digest}")
    return match


# -- entry point ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="foundry",
        description="Agent Foundry Stage-1 reference CLI (demo, verify, lineage, replay).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser("demo", help="run the complete Stage-1 story end-to-end")
    demo_parser.add_argument("--root", type=Path, required=True, help="state directory")
    demo_parser.add_argument("--seed", type=int, default=42, help="corpus/experiment seed")

    verify_parser = subparsers.add_parser("verify", help="re-verify all evidence under a root")
    verify_parser.add_argument("--root", type=Path, required=True, help="state directory")

    lineage_parser = subparsers.add_parser("lineage", help="print the bundle lineage tree")
    lineage_parser.add_argument("--root", type=Path, required=True, help="state directory")

    replay_parser = subparsers.add_parser("replay", help="re-execute a recorded mission")
    replay_parser.add_argument("--root", type=Path, required=True, help="state directory")
    replay_parser.add_argument("--mission", required=True, help="mission id to replay")

    coverage_parser = subparsers.add_parser(
        "coverage", help="event-coverage audit against the required Stage-1 vocabulary"
    )
    coverage_parser.add_argument("--root", type=Path, required=True, help="state directory")

    args = parser.parse_args(argv)
    if args.command == "demo":
        run_demo(args.root, seed=args.seed)
        return 0
    if args.command == "verify":
        return 0 if verify_root(args.root) else 1
    if args.command == "lineage":
        print_lineage(args.root)
        return 0
    if args.command == "coverage":
        return 0 if report_coverage(args.root) else 1
    return 0 if replay_mission(args.root, args.mission) else 1


if __name__ == "__main__":
    sys.exit(main())
