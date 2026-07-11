# Modular RSI Agent Foundry

Stage-1 reference implementation of an event-sourced **experiment control plane** for agent systems: every mission runs under a frozen, signed, content-addressed configuration bundle; every proposed change to that configuration is a typed diff tested in a paired, seeded, budget-equalized experiment against a blind protected holdout; and nothing reaches deployment except through a fail-closed G0-G9 promotion gate with human authorization and an executable rollback path. This repo is **not** an autonomous, open-ended self-improving system, and it should never be described as one. Following the claims language of the technical report (section 21.1), what this code implements is infrastructure for **governed system optimization**. "Bounded RSI" is a claim reserved for future multi-generation evidence (report 12.6, 18.8): at least two accepted descendant generations, independently validated on protected holdouts, with the newer system demonstrably participating in producing the next generation. No such evidence exists yet, and this repo makes no such claim.

## What Stage 1 contains

All runtime code lives in `src/foundry/`:

- `contracts/` - the frozen Pydantic contracts: `SystemBundle` (content-addressed identity), canonical `Event` envelope and event-type vocabulary, `MissionSpec`, `ImprovementProposal`, `ExperimentRecord`, `PairedAnalysis`, governance records, memory contracts, and the structural protocols (`LedgerLike`, `ArtifactStoreLike`, `WorkerLike`) other packages build against
- `ledger/` - SQLite append-only event ledger: idempotent on `event_id`, hash-chained, HMAC-signed, with a signed tip checkpoint that makes tail truncation evident; `verify_chain`, JSONL export/import
- `artifacts/` - content-addressed immutable blob store (`artifact://sha256:<hex>`), digest re-verified on every read
- `registry/` - signed, content-addressed bundle registry with lineage, machine-readable diffs and `fork` as the only mutation primitive (policy-checked against allowed path prefixes); `HMACSigner` dev signing
- `compiler/` - `MissionCompiler`: raw request in, immutable `MissionSpec` pinned to exactly one bundle out
- `runtime/` - the `RuntimeAdapter` protocol, the shared `LedgerBackedRuntime` control plane (start/resume/cancel/status derived purely from the ledger) and `DeterministicRuntime`, a no-model plan/execute/verify workflow that keeps zero private state (recovery is ledger-only; duplicate delivery is suppressed as evidence)
- `workers/` - two no-model domains behind `WorkerLike`: `FixtureWorker` with the seeded slugify corpus, and `DeterministicCodingWorker` with the executable-test coding corpus (tiny buggy repos plus assertion scripts, four roles, `make_coding_run_arm` wiring)
- `experiment/` - `ExperimentController` (matched paired design, run, analyze, leakage check), `HoldoutVault` (blind HMAC handles; ground truth never leaves the vault), seeded paired-bootstrap analysis, and the registered-campaign runner (`run_campaign`: pre-registered fixed-size series with deterministic archivable payloads; campaign v1 with 20 experiments is archived under `research/`)
- `evaluation/` - deterministic exact-match oracle, the `MetricVector` aggregation harness, and `DeterministicTestService`: an ephemeral-workspace executable-check runner that force-restores the trusted checks file (a worker that doctors the tests is scored against the originals), emits command receipts and scores untrusted output fail-closed
- `improvement/` - the improvement loop's front half (report 8.3 steps 1-3): `EvidenceDiagnoser` (strictly read-only failure-signature grouping over ledgered mission evaluations) and the `ProposerLike` seam with `TemplateMutationProposer` as the deterministic reference (governance-supplied mutation table, rejected-diff convergence guard, proposal budgets); proposers hold no registry, vault or approval authority
- `memory/` - governed memory service (report 11): quarantine-first staged writes, provenance-required promotion with no self-promotion, contradiction links, expiry, filters-before-match retrieval, a `ContextBuilder` producing cited, token-budgeted `ContextPackage`s, and `MemoryConsolidator` (report 11.5): a deterministic, model-free producer that clusters recurring mission episodes into candidate semantic claims and negative lessons, requires recurrence and a disconfirming-episode search before staging, and only ever stages (never promotes); state is an event-sourced projection over the ledger
- `policy/` - fail-closed `PolicyDecisionPoint` (Stage-1 mutation surface: autonomy levels 1-2 only), capability token issuer
- `promotion/` - the G0-G9 gates as pure functions and the fail-closed `PromotionGate` runner that signs its decisions
- `deployment/` - event-sourced `DeploymentController`: canary before scoped production, signed-decision and signed-bundle verification, rollback to the recorded parent
- `dashboard/` - a read-only, self-contained HTML trace/governance/evolution view (report 15.3/15.6): `build_dashboard_model` projects the ledger and registry into a frozen model, `render_html` turns it into one offline page (inline CSS, no scripts, no external fetches). Built to report 15.4's line between useful and harmful observability: every experiment delta keeps its confidence interval, quarantined and rolled-back branches are never omitted, each decision shows the exact diff and all G0-G9 gate results, dynamic text is escaped and secret-redacted, and the header states the exact evidence snapshot
- `cli.py` - the `foundry` entry point (`demo`, `verify`, `lineage`, `replay`, `coverage`, `dashboard`)
- `adapters/` - optional-dependency framework adapters: `langgraph_runtime.LangGraphRuntime` (`.[langgraph]`), which schedules the same workflow through LangGraph with a byte-identical canonical event stream (pinned by `tests/test_runtime_conformance.py`), and `openai_proposer.OpenAIReflectiveProposer` (`.[openai]`), the first model-backed `ProposerLike`: model output is validated fail-closed (out-of-surface paths and out-of-domain values dropped, old values read from the frozen bundle, rejected-diff and budget rules enforced) and every API call is ledgered as MODEL_REQUEST/MODEL_RESPONSE evidence with digests and token usage; the API key lives in the environment only

## Quickstart

```bash
pip install -e ".[dev,langgraph]"    # drop the langgraph extra for the dependency-free core
python -m pytest                      # 484 tests (LangGraph conformance and the live OpenAI test skip without extra/key)
foundry demo --root .foundry-demo    # run the complete Stage-1 story
foundry verify --root .foundry-demo  # re-verify all evidence (exit 0/1)
foundry lineage --root .foundry-demo # print the bundle tree
foundry replay --root .foundry-demo --mission <mission_id>   # exit 0/1
foundry coverage --root .foundry-demo # event-coverage audit vs the 95% exit criterion
foundry dashboard --root .foundry-demo # write a self-contained HTML trace/governance dashboard
```

The demo prints the mission ids to use with `replay`. `examples/quickstart.py` is a compact, commented walkthrough of the same pipeline, and `examples/coding_experiment.py` runs the paired experiment on the executable-test coding domain.

## The demo storyline

`foundry demo` runs the full Stage-1 arc (the CLI prints these as `[1/9]` through `[9/9]`), asserting its own invariants at every step:

1. Create, sign and register the root bundle S0 (`strategy=naive`).
2. Compile and run three fixture missions under frozen S0, emitting canonical events.
3. Build a typed `ImprovementProposal` (one falsifiable hypothesis, pre-registered thresholds, rollback condition, experiment plan artifact).
4. Ask the policy decision point for permission, then fork candidate S1 (`strategy=robust`) inside the level-2 mutation surface.
5. Design, run and analyze the paired experiment: control vs candidate over the seeded corpus, protected holdout sealed in the vault and scored blind, leakage check before results open.
6. Aggregate the metric vector and run the G0-G9 gate: without approval the decision is QUARANTINE; with a non-proposer human approval it is CANARY.
7. Deploy: canary first, then scoped production (the controller refuses production without a prior canary).
8. Roll back to S0 on an explicit trigger, then re-activate S1 (rollback is executable, not documentation).
9. Verify the evidence chain and count the stores.

## Five design rules the code enforces structurally

These are report section 8.1 rules implemented as code paths, not conventions, and the test suite pins them:

1. **Frozen content-addressed bundles.** `SystemBundle.bundle_id` is recomputed by a model validator; the registry re-verifies the content address on every load and refuses mismatches; `fork` is the only way to derive a child.
2. **Append-only hash-chained evidence.** The ledger has no update or delete; every event carries a digest, chain link, sequence and signature; a signed tip checkpoint makes deleting the newest events detectable.
3. **Blind holdouts.** Protected tasks are reachable only through `HoldoutVault.run_blind`: candidates see a redacted view keyed by an HMAC handle, scoring happens inside the vault, and the PDP grants `holdout.read` to exactly one principal (the experiment controller).
4. **No self-approval.** Gate G8 rejects any approval whose approver is the proposer, and the deployment controller independently re-checks distinct non-proposer approvers bound to the exact candidate digest.
5. **Fail-closed gates plus executable rollback.** A gate that throws has failed; a decision missing any gate result cannot deploy; only gate-signed decisions and signed bundles deploy; every promotion names its parent as the rollback target and `rollback()` restores it.

## Repository layout

```
RSI/
├── src/foundry/          # the Stage-1 packages listed above
├── tests/                # 484 tests, including tests/test_e2e_replay.py (capstone)
├── schemas/              # exported JSON Schemas (scripts/export_schemas.py)
├── examples/quickstart.py
├── scripts/export_schemas.py
├── adapters/             # per-adapter docs; implemented code lives in src/foundry/adapters/
│   ├── runtimes/langgraph/
│   ├── coding/{openhands,mini_swe_agent}/
│   └── optimizers/gepa_dspy/
├── modules/              # versioned module packages (Stage 2)
├── bundles/              # signed bundle declarations (Stage 2)
├── benchmarks/           # public / protected-manifests / adversarial / retention / incidents
├── policies/             # capabilities / promotion / retention / sandbox (policy-as-code, Stage 2+)
├── research/protocols/   # STAGE1_PROTOCOL.md
└── docs/                 # TECHNICAL_REPORT.md, ARCHITECTURE.md, DECISIONS.md, ROADMAP.md
```

## Roadmap (report section 19)

| Stage | Objective | Status |
|-------|-----------|--------|
| 1. Minimal research prototype | One frozen bundle executes reproducibly, emits complete evidence, supports a fair manual candidate comparison | **This repo**: core loop implemented on deterministic fixtures; LangGraph adapter done (conformance-pinned); OpenHands/mini-SWE-agent workers and trace UI still open (see docs/ROADMAP.md) |
| 2. Modular Agent Foundry | Replace agents, workers, tools and memories through stable contracts without corrupting evidence | Not started (the protocol seams exist in `contracts/` and `runtime/adapter.py`) |
| 3. Bounded self-improvement | Automated proposers (GEPA/DSPy), shadow/canary at scale, autonomy levels 1-2 with lower regression risk than fixed optimization | Not started |
| 4. Research-grade RSI platform | Longitudinal multi-generation studies, evaluator cross-audit, meta-RSI shadow experiments | Not started |

## Relationship to the technical report

`docs/TECHNICAL_REPORT.md` is the authoritative specification; this repo is the "immediate next artifact" it calls for (section 22.2): a small executable reference implementation of the Stage-1 schemas, deterministic fixture workflow, event ledger, paired experiment runner and manual promotion record, whose first success criterion is that an independent researcher can reproduce a mission and candidate comparison from the bundle, events and artifacts alone (`foundry verify` and `foundry replay` implement exactly that check). Source docstrings cite the report sections they implement. Where Stage 1 deliberately deviates from the report's recommended stack (SQLite instead of Postgres, HMAC instead of Sigstore, a fixture worker instead of OpenHands, Python 3.11 floor), `docs/DECISIONS.md` records the decision and the migration seam.

## License

MIT (see `LICENSE`).
