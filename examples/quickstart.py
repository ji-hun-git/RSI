"""Agent Foundry quickstart: bundle -> missions -> proposal -> fork -> experiment -> gate.

A compact, heavily commented walk through steps 1-6 of the Stage-1 story
(see ``foundry demo`` for the full nine-step version with deployment and
rollback). Everything persists under one temporary directory; run it with
``python examples/quickstart.py``.
"""

import tempfile
from pathlib import Path

from foundry.compiler import MissionCompiler
from foundry.contracts import (
    ApprovalRecord,
    ApprovalTier,
    AutonomyLevel,
    BundleDiff,
    ChangeTarget,
    ExperimentBudget,
    FieldChange,
    ImprovementProposal,
    MissionRequest,
    ModuleRef,
    PromotionStatus,
    SystemBundle,
    TaskSetRefs,
    TaskSetRole,
)
from foundry.evaluation import EvaluationHarness, exact_match
from foundry.experiment import ExperimentController, HoldoutVault
from foundry.ledger import EventLedger
from foundry.policy import ALLOWED_MUTATIONS
from foundry.promotion import PromotionGate
from foundry.registry import BundleRegistry, HMACSigner
from foundry.runtime import FIXTURE_WORKFLOW_REF, DeterministicRuntime
from foundry.workers import FixtureWorker, generate_task_sets

SEED = 42
root = Path(tempfile.mkdtemp(prefix="foundry-quickstart-"))

# All state is explicit and file-backed: an append-only hash-chained event
# ledger (the evidence root) and a content-addressed bundle registry.
signer = HMACSigner.load_or_create(root / "keys" / "signing.key", key_id="quickstart")
ledger = EventLedger(root / "ledger.db", producer="quickstart", signer=signer)
registry = BundleRegistry(root / "bundles", signer=signer)

# (1) The root bundle S0 is the system's frozen "genome": content-addressed,
# signed, registered. Its config selects the deliberately weak strategy.
s0 = registry.sign(SystemBundle(
    workflow_ref=FIXTURE_WORKFLOW_REF,
    config={"strategy": "naive"},
    status=PromotionStatus.SCOPED_PRODUCTION,
))
registry.register(s0)

# (2) Missions run under exactly one bundle. The compiler freezes the spec;
# the deterministic runtime executes plan/execute/verify, all as ledger events.
compiler = MissionCompiler(ledger)
runtime = DeterministicRuntime(ledger, FixtureWorker())
request = MissionRequest(description="Slugify a title", inputs={"text": "Hello,  Foundry!"})
spec = compiler.compile(request, s0)
runtime.start(spec, s0)

# (3) An improvement is a falsifiable proposal: one hypothesis, a typed diff,
# an experiment plan and an executable rollback condition -- never a hot edit.
change = FieldChange(field_path="/config/strategy", old_value="naive", new_value="robust")
proposal = ImprovementProposal(
    parent_bundle_id=s0.bundle_id,
    target=ChangeTarget(field_path="/config/strategy"),
    hypothesis="Robust normalization reduces hard-task failures.",
    changes=[change],
    autonomy_level=AutonomyLevel.PROMPT_SKILL_ROUTING,  # level 2
    experiment_plan_ref="plan://quickstart/robust-normalization",
    # The proposer pre-registers its retention set and thresholds (12.3);
    # the promotion gate reads them from here, never from call arguments.
    retention_set_ref="corpus://quickstart/retention",
    minimum_practical_effect=0.0,
    retention_floor=0.0,
    rollback_condition="holdout ci_low <= 0 or any retention loss: prefer the parent",
    proposer=ModuleRef(id="optimizer.gepa"),
)

# (4) Fork the candidate S1. The registry only accepts changes inside the
# policy's level-2 mutation surface; anything else raises PolicyViolation.
allowed = list(ALLOWED_MUTATIONS[AutonomyLevel.PROMPT_SKILL_ROUTING])
s1 = registry.sign(registry.fork(s0, [change], allowed_path_prefixes=allowed))
registry.register(s1)

# (5) A matched, paired experiment: same tasks, order and per-task seeds for
# both arms. The protected holdout is sealed in a vault together with its
# trusted scorer; arms only ever see blind handles and redacted views, so
# candidates can neither memorize nor echo the held-out tasks.
def run_arm(bundle, task, seed):  # a "run" here is one deterministic worker call
    task_input = {"task_id": task.task_id, "text": task.input_text, "family": task.family}
    return FixtureWorker().invoke(task_input, bundle.config, seed)["output"]

def score(task, output):  # deterministic oracle: exact match on ground truth
    return exact_match(task.expected_output, output)

corpus = generate_task_sets(SEED)
vault = HoldoutVault(secret=b"quickstart-vault-secret")
refs = TaskSetRefs(
    development="corpus://quickstart/development",
    protected=vault.seal("protected", corpus["protected"], scorer=score),
    retention="corpus://quickstart/retention",
    adversarial="corpus://quickstart/adversarial",
)
controller = ExperimentController(ledger, vault=vault)
record = controller.design(proposal, s0, [s1], refs, ExperimentBudget(), SEED)

open_tasks = {role: corpus[role.value] for role in
              (TaskSetRole.DEVELOPMENT, TaskSetRole.RETENTION, TaskSetRole.ADVERSARIAL)}
results = controller.run(record, {"control": s0, "candidate_a": s1}, open_tasks, run_arm, score)
analyses = controller.analyze(record, results, seed=SEED)["candidate_a"]

# (6) The deterministic G0-G9 gate turns evidence into one governed decision.
# Without a human approval the candidate is QUARANTINED even though every
# statistical gate passes; with an A1 approval (from a non-proposer) it
# proceeds to CANARY. Promotion authority is never the proposer's.
metrics = EvaluationHarness().aggregate(results["candidate_a"])
diff = BundleDiff(parent_bundle_id=s0.bundle_id, child_bundle_id=s1.bundle_id, changes=[change])
gate = PromotionGate(signer=signer)  # decisions are signed by the gate that made them
quarantined = gate.run(proposal, s0, s1, diff, analyses, metrics, [], allowed_path_prefixes=allowed)
approval = ApprovalRecord(approver="human:owner", tier=ApprovalTier.A1_SINGLE_REVIEWER,
                          candidate_bundle_id=s1.bundle_id)
approved = gate.run(proposal, s0, s1, diff, analyses, metrics, [approval],
                    allowed_path_prefixes=allowed)

dev = analyses[TaskSetRole.DEVELOPMENT]
holdout = analyses[TaskSetRole.PROTECTED_HOLDOUT]
print(f"development mean_delta = {dev.mean_delta:+.3f} (n={dev.n_pairs})")
print(f"holdout ci = [{holdout.ci_low:+.3f}, {holdout.ci_high:+.3f}] (blind handles only)")
print(f"gate without approval -> {quarantined.action.value}")
print(f"gate with A1 approval -> {approved.action.value}")
print(f"evidence: {ledger.count()} hash-chained events under {root}")
ledger.close()
