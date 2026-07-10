# HANDOFF: resume context for the Modular RSI Agent Foundry (Stage 1)

Read this first in any new session. `CLAUDE.md` holds the working rules; this file holds the state.

## What exists

Stage 1 is complete and green: a single installable package (`agent-foundry`, import root `foundry`) implementing the event-sourced experiment control plane of `docs/TECHNICAL_REPORT.md` sections 19.1 and 22.2 on deterministic fixtures.

- Contracts frozen in `src/foundry/contracts/` (bundle, events, mission, improvement, evaluation, governance, memory, manifest, protocols). JSON Schemas exported to `schemas/` via `scripts/export_schemas.py`.
- Working pipeline: `MissionCompiler` -> `DeterministicRuntime` (plan/execute/verify, ledger-only recovery) -> `ExperimentController` (paired, seeded, blind holdout via `HoldoutVault`) -> `EvaluationHarness` -> `PromotionGate` (G0-G9, fail-closed, signed decisions) -> `DeploymentController` (canary before production, rollback to parent), all over `EventLedger` (SQLite, hash chain, signed tip checkpoint) + `ArtifactStore` + `BundleRegistry` (content-addressed, fork-only mutation) + `PolicyDecisionPoint` (fail-closed, Stage-1 mutation surface = autonomy levels 1-2).
- CLI `foundry` with four subcommands: `demo` (nine-step story), `verify` (full evidence re-verification incl. independent recomputation of every paired analysis; exit 0/1), `lineage`, `replay` (re-executes a recorded mission and compares output digests; exit 0/1).
- LangGraph runtime adapter: `foundry.adapters.langgraph_runtime.LangGraphRuntime` (optional dependency group `langgraph`), built on the shared `foundry.runtime.LedgerBackedRuntime` control plane so its canonical event stream is byte-identical to `DeterministicRuntime`'s. `tests/test_runtime_conformance.py` pins every RuntimeAdapter behavior (crash/resume/cancel/duplicate suppression, deterministic reruns, reference equivalence) across all installed runtimes.
- Executable-test coding domain (report 18.3): `foundry.workers.coding_tasks` (four-role corpus of tiny buggy repos with assertion scripts), `DeterministicCodingWorker` (naive/robust repair strategies, pure), `make_coding_run_arm` (serves open and blind-vault roles), and `foundry.evaluation.DeterministicTestService` (ephemeral workspace, trusted-checks restore so doctored tests buy nothing, command receipts, hard timeout, fail-closed scoring of malformed/path-escaping output). Full paired experiment on run-the-checks evidence in `tests/test_coding_domain.py`; runnable walkthrough in `examples/coding_experiment.py`. See ADR-008.
- Governed memory (report 11): `foundry.memory.MemoryService` (event-sourced projection; quarantine-first staging, review, provenance-required promotion with no self-promotion, contradiction links, expiry, retrieval feedback, filters-before-match retrieval) and `ContextBuilder` (cited, token-budgeted `ContextPackage`s with warnings and MEMORY_SHOWN events). GOVERNANCE items have no autonomous write path; PROCEDURE items are refused (the bundle registry owns them). `tests/test_memory.py`; ADR-009.
- Improvement-loop front half (report 8.3 steps 1-3): `foundry.improvement.EvidenceDiagnoser` (strictly read-only failure-signature grouping over ledgered mission evaluations; refuses evidence not attributable to a frozen bundle config) plus the `ProposerLike` seam with `TemplateMutationProposer` as deterministic reference (governance-supplied mutation table, rejected-diff convergence guard per 12.5, proposal budgets, no registry/vault/approval authority). Full loop cohort->diagnosis->proposal->fork->experiment->gate pinned model-free in `tests/test_improvement_loop.py`; ADR-010.
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (ADR-001..010), `docs/ROADMAP.md`, `research/protocols/STAGE1_PROTOCOL.md`, adapter README stubs under `adapters/`.

## Where state lives

- All runtime state goes under a root directory passed as `--root` (contains `ledger.db`, `ledger.db.checkpoint`, `artifacts/`, `bundles/`, `keys/signing.key`).
- Local state roots are gitignored (`.foundry*/`, `*.db`). Never commit a foundry root: it contains a signing key and machine-local evidence.
- `.ruff_cache/`, `*.egg-info/` etc. are gitignored as usual.

## How to run everything

```bash
cd C:\Users\Jason\RSI
pip install -e ".[dev,langgraph]"
python -m pytest -q                          # expect: 425 passed (LangGraph conformance skips without the extra)
python -m ruff check src tests examples scripts   # expect: All checks passed!
foundry demo --root .foundry-demo [--seed N]
foundry verify --root .foundry-demo
foundry replay --root .foundry-demo --mission <mis_... printed by demo>
```

The capstone suite is `tests/test_e2e_replay.py` (15 tests over a session-scoped demo run, including keyless statistical reproduction and tamper detection).

## The frozen-contracts rule

`src/foundry/contracts/` is the interchange layer other packages, the exported schemas and the persisted evidence all depend on. Do not change field names, types, defaults that affect serialization, or digest/identity computations. Additive, backward-compatible changes require a migration note (new ADR) in `docs/DECISIONS.md`; anything that would change the digest of an existing event or bundle is effectively forbidden, because it makes honest historical evidence look tampered.

## What to build next (in rough order)

1. **GEPA/DSPy proposer adapter** in `adapters/optimizers/gepa_dspy/`: implement `foundry.improvement.ProposerLike` behind an LLM key (BLOCKED on the key; the seam, constraints object, rejected-diff rule and full downstream loop are already exercised model-free). It gets no promotion authority and no vault access, ever; see the adapter README for the exact contract.
2. **Memory extensions** (smaller): model-assisted extraction staging through `MemoryService.stage`, consolidation jobs (11.5), vector/graph projections rebuilt from ledger events, and the privacy deletion/redaction workflow (15.5).
3. Also open (smaller): the 20+ paired-experiment registered campaign from `research/protocols/STAGE1_PROTOCOL.md`, and an automated event-coverage meter for the 95% exit criterion.
4. **Real coding agents (OpenHands, mini-SWE-agent)**: seam fully specified by the coding domain (`WorkerLike` + `make_coding_run_arm` + `DeterministicTestService`), but BLOCKED on LLM keys and a real sandbox behind `run_checks` (ADR-008; adapter READMEs state the contract and blockers). Do not run model-generated code under the local-subprocess test service.

## Governance invariants that must never be weakened

Tests pin all of these; treat a red test here as a design alarm, not an inconvenience.

- **Append-only evidence.** No update or delete on the ledger; corrections are new events. Hash chain plus signed tip checkpoint must keep detecting in-place edits and tail truncation.
- **Content-addressed frozen bundles.** `bundle_id` always equals the recomputed content digest; fork is the only mutation path and is policy-checked against allowed path prefixes; `/parent_bundle_id` is never directly editable and `/workflow_ref` only when explicitly allowed.
- **Blind holdouts.** Protected tasks are executed only through `HoldoutVault.run_blind`; ground truth and true task ids never cross the vault boundary; only the experiment controller may read the vault (PDP); the leakage check runs before protected results open.
- **No self-approval.** G8 rejects proposer-signed approvals; the deployment controller independently requires distinct non-proposer approvers bound to the exact candidate digest. A4 (code/training-level) changes have no autonomous path at all.
- **Fail-closed everywhere.** A throwing gate is a failed gate; a decision missing any G0-G9 result cannot deploy; unsigned decisions and unsigned bundles cannot deploy; unknown PDP actions/subjects are denied; a missing signing key is a distinct audit outcome and verifiers never mint keys into a root under audit.
- **Canary precedes production; rollback stays executable.** Every promotion records its parent as rollback target; `rollback()` must keep working from the ledger alone.
- **Claims language** (report 21.1): this repo is "governed system optimization" infrastructure. Do not describe it as autonomous or open-ended RSI anywhere, including docstrings, commit messages and demos.
