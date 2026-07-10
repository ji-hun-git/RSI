# Stage-1 Experimental Protocol

The operating protocol for Stage-1 (Phase A) experiments in this repository, distilled from `docs/TECHNICAL_REPORT.md` sections 13.4 (statistical design), 18.4 Phase A (infrastructure validation) and 19.1 (Stage-1 exit criteria). Phase A makes **no RSI claim**: its exit question is event completeness, replay, policy and rollback on deterministic fixtures.

## 1. Fixture mission requirements

Every Stage-1 mission must satisfy all of the following (the demo and tests enforce them):

- Deterministic worker: a pure function of `(task_input, config, seed)` behind `WorkerLike`; no wall-clock, no network, no hidden state.
- Frozen identity: the mission's `MissionSpec` pins exactly one signed, registered `SystemBundle` by content digest; the runtime refuses a spec/bundle mismatch.
- Known ground truth: fixture tasks carry `expected_output` computed by the same `robust_slugify` function the robust strategy executes, so oracle and ground-truth worker cannot drift.
- Seeded corpus: task sets are a pure function of the seed (`generate_task_sets(seed)`), identical on any platform and interpreter version.
- Replayability: re-executing the recorded spec under the recorded bundle must reproduce the recorded output digest (`foundry replay` exits 0).

## 2. Event-completeness checklist

For each fixture mission, the ledger must contain, in chain-verified order:

- [ ] `mission.compiled` (spec digest, request id)
- [ ] `mission.started` (payload carries the full frozen spec and bundle, so recovery needs only the ledger)
- [ ] `workflow.node_started` and `workflow.node_completed` for every node (`plan`, `execute`, `verify`), with output digests
- [ ] `mission.completed` with `final_output` and `output_digest`
- [ ] On interruption and resume: `mission.resumed`, plus `workflow.duplicate_suppressed` for every already-completed node (a node executes at most once per run)
- [ ] On failure: `workflow.node_failed` carrying the error before the process propagates it
- [ ] `EventLedger.verify_chain()` returns ok: every payload digest, chain link and sequence recomputes, and the signed tip checkpoint anchors the tail

For each experiment: `experiment.designed`, `experiment.randomized`, `experiment.arm_started`/`arm_completed` per arm, `evaluation.metric_computed` per (arm, role), `experiment.analyzed` with the order-canonical summary, and `experiment.leakage_detected` if (and only if) the leakage check hits.

## 3. Paired-comparison procedure

Per report 13.4, instantiated concretely by `ExperimentController` and the G0-G9 gate:

1. **Pre-register on the proposal, before any protected result is seen.** The `ImprovementProposal` must carry: one primary falsifiable hypothesis, the typed diff (every changed path declared), the primary endpoint (paired task-success delta), `minimum_practical_effect`, `retention_set_ref`, `retention_floor`, and an executable `rollback_condition`. The gate reads thresholds from the proposal, never from gate-time arguments; G0 rejects proposals with an empty hypothesis, empty rollback condition, missing experiment plan or missing retention set.
2. **Design.** Control arm always included; every candidate's `parent_bundle_id` must equal the control bundle (matched lineage); budgets equalized across arms; randomization unit = task, paired = true, seed recorded in `experiment.randomized`.
3. **Seal the holdout first.** Protected tasks go into the `HoldoutVault` before the experiment runs; the vault ref (`blind://vault/<name>`) is the only representation in the `ExperimentRecord`. Only the experiment controller may read the vault (PDP-enforced).
4. **Leakage check before results open.** Proposal hypothesis, current-behavior text and evidence refs are scanned for verbatim protected task content; any hit emits `experiment.leakage_detected` and disqualifies the comparison.
5. **Run matched.** Every arm executes the same tasks in the same order with identical per-task seeds (`derive_seed(base_seed, task_id)`). Protected tasks execute only through `run_blind`: redacted view in, float score out.
6. **Stopping rule.** Stage 1 uses a fixed-size, single-pass design: all tasks in every role, exactly once per arm, then one analysis. There is no adaptive peeking, no early stop on favorable interim results, and no holdout reuse for optimizer feedback.
7. **Analyze paired.** Per-task deltas over identical task sets (unpaired scores are rejected), mean delta plus a seeded paired percentile-bootstrap CI (order-canonical, so it reproduces independently of blind-handle keys), win/loss/tie counts, all persisted in `experiment.analyzed`.
8. **Decision rule.** G2: development mean delta >= minimum practical effect. G3: protected-holdout **lower confidence bound** >= minimum practical effect (one-sided; the mean is never the criterion; failure means "prefer the parent when uncertain"). G4: retention non-inferiority plus zero per-task losses. G5: zero critical adversarial violations, no trade-offs. G7: bit-identical rerun agreement.
9. **Independent reproduction.** `foundry verify` must be able to recompute every recorded paired analysis from the ledger events, registered bundles and seed-regenerated corpus alone, and match the persisted `experiment.analyzed` payload exactly.

## 4. Promotion evidence checklist (report Appendix B.1, condensed)

Before any candidate activates, all of the following must hold (gate G0-G9 plus deployment controller enforce them mechanically):

- [ ] Parent and candidate bundle digests resolve; content addresses recompute; signatures verify
- [ ] Every diff path is inside the allowed mutation surface AND declared in the proposal (no undeclared change)
- [ ] Control and candidate used matched tasks, order, seeds and equalized budgets
- [ ] Protected holdout stayed blind and the leakage check passed
- [ ] Primary endpoint, minimum practical effect and stopping rule match the pre-registration on the proposal
- [ ] Retention floor met with zero per-task retention losses
- [ ] Adversarial suite: zero critical violations
- [ ] Reproducibility: rerun agreement at floor (1.0 for deterministic fixtures)
- [ ] Human authorization: required tier met by distinct non-proposer approver(s) bound to the exact candidate digest; no self-approval; A4 changes never deploy autonomously
- [ ] Decision signed by the gate; every gate result present and passed; canary precedes scoped production; rollback target (the parent) recorded and executable

## 5. Criteria before any claim exceeds "governed system optimization"

Per report 12.6 and 18.8, none of which Stage 1 satisfies (and Stage 1 does not claim to):

- At least **two accepted descendant generations** beyond the initial system, with complete lineage and protected evaluation
- **Persistence**: accepted changes altered versioned components used by future missions (not one-off output revisions)
- **Self-reference**: the changed system participates in producing, selecting or executing later changes
- **Independent validation**: acceptance via protected comparative evidence, never self-assertion
- **Intergenerational effect**: S_t+1 measurably affects the generation, quality or efficiency of candidate S_t+2
- **Retention and governance**: prior capabilities, safety properties and human authority preserved throughout
- Fresh held-out gains exceed the predeclared practical threshold and are not explained by extra resources or model upgrades
- Rejected and rolled-back changes reported, including harmful-modification frequency; full search-cost accounting
- Ablation showing the recursive mechanism contributes beyond static human iteration or fixed optimization

Until every item holds, the only permitted description of results from this platform is **governed system optimization** (report 21.1).
