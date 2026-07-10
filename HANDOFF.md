# HANDOFF: resume context for the Modular RSI Agent Foundry (Stage 1)

Read this first in any new session. `CLAUDE.md` holds the working rules; this file holds the state.

## What exists

Stage 1 is complete and green: a single installable package (`agent-foundry`, import root `foundry`) implementing the event-sourced experiment control plane of `docs/TECHNICAL_REPORT.md` sections 19.1 and 22.2 on deterministic fixtures.

- Contracts frozen in `src/foundry/contracts/` (bundle, events, mission, improvement, evaluation, governance, memory, manifest, protocols). JSON Schemas exported to `schemas/` via `scripts/export_schemas.py`.
- Working pipeline: `MissionCompiler` -> `DeterministicRuntime` (plan/execute/verify, ledger-only recovery) -> `ExperimentController` (paired, seeded, blind holdout via `HoldoutVault`) -> `EvaluationHarness` -> `PromotionGate` (G0-G9, fail-closed, signed decisions) -> `DeploymentController` (canary before production, rollback to parent), all over `EventLedger` (SQLite, hash chain, signed tip checkpoint) + `ArtifactStore` + `BundleRegistry` (content-addressed, fork-only mutation) + `PolicyDecisionPoint` (fail-closed, Stage-1 mutation surface = autonomy levels 1-2).
- CLI `foundry` with four subcommands: `demo` (nine-step story), `verify` (full evidence re-verification incl. independent recomputation of every paired analysis; exit 0/1), `lineage`, `replay` (re-executes a recorded mission and compares output digests; exit 0/1).
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (ADR-001..006), `docs/ROADMAP.md`, `research/protocols/STAGE1_PROTOCOL.md`, adapter README stubs under `adapters/`.

## Where state lives

- All runtime state goes under a root directory passed as `--root` (contains `ledger.db`, `ledger.db.checkpoint`, `artifacts/`, `bundles/`, `keys/signing.key`).
- Local state roots are gitignored (`.foundry*/`, `*.db`). Never commit a foundry root: it contains a signing key and machine-local evidence.
- `.ruff_cache/`, `*.egg-info/` etc. are gitignored as usual.

## How to run everything

```bash
cd C:\Users\Jason\RSI
pip install -e ".[dev]"
python -m pytest -q                          # expect: 356 passed
python -m ruff check src tests examples scripts   # expect: All checks passed!
foundry demo --root .foundry-demo [--seed N]
foundry verify --root .foundry-demo
foundry replay --root .foundry-demo --mission <mis_... printed by demo>
```

The capstone suite is `tests/test_e2e_replay.py` (15 tests over a session-scoped demo run, including keyless statistical reproduction and tamper detection).

## The frozen-contracts rule

`src/foundry/contracts/` is the interchange layer other packages, the exported schemas and the persisted evidence all depend on. Do not change field names, types, defaults that affect serialization, or digest/identity computations. Additive, backward-compatible changes require a migration note (new ADR) in `docs/DECISIONS.md`; anything that would change the digest of an existing event or bundle is effectively forbidden, because it makes honest historical evidence look tampered.

## What to build next (in rough order)

1. **LangGraph RuntimeAdapter** in `adapters/runtimes/langgraph/`, behind the `foundry.runtime.adapter.RuntimeAdapter` protocol (start/resume/cancel/status). Canonical events remain the record; native LangGraph checkpoints stay opaque. Conformance target: the same crash/resume/cancel/duplicate-suppression behavior `tests/test_runtime.py` pins for the deterministic runtime. Optional dependency group `langgraph` already exists in `pyproject.toml`.
2. **Real coding workers** behind `foundry.contracts.WorkerLike`: OpenHands in `adapters/coding/openhands/`, mini-SWE-agent baseline in `adapters/coding/mini_swe_agent/`. Keep the fixture worker: it stays the conformance and replay baseline.
3. **Memory service** per report section 11 over the existing `MemoryItem`/`ContextPackage` contracts: staging (candidate writes), quarantine, provenance-required promotion, contradiction links, expiry. Write authority is governed; models only propose.
4. **GEPA/DSPy proposer adapter** in `adapters/optimizers/gepa_dspy/`: consumes ledger evidence, emits typed `ImprovementProposal` objects with `FieldChange` diffs inside the PDP mutation surface. It gets no promotion authority and no vault access, ever.
5. Also open (smaller): the 20+ paired-experiment registered campaign from `research/protocols/STAGE1_PROTOCOL.md`, and an automated event-coverage meter for the 95% exit criterion.

## Governance invariants that must never be weakened

Tests pin all of these; treat a red test here as a design alarm, not an inconvenience.

- **Append-only evidence.** No update or delete on the ledger; corrections are new events. Hash chain plus signed tip checkpoint must keep detecting in-place edits and tail truncation.
- **Content-addressed frozen bundles.** `bundle_id` always equals the recomputed content digest; fork is the only mutation path and is policy-checked against allowed path prefixes; `/parent_bundle_id` is never directly editable and `/workflow_ref` only when explicitly allowed.
- **Blind holdouts.** Protected tasks are executed only through `HoldoutVault.run_blind`; ground truth and true task ids never cross the vault boundary; only the experiment controller may read the vault (PDP); the leakage check runs before protected results open.
- **No self-approval.** G8 rejects proposer-signed approvals; the deployment controller independently requires distinct non-proposer approvers bound to the exact candidate digest. A4 (code/training-level) changes have no autonomous path at all.
- **Fail-closed everywhere.** A throwing gate is a failed gate; a decision missing any G0-G9 result cannot deploy; unsigned decisions and unsigned bundles cannot deploy; unknown PDP actions/subjects are denied; a missing signing key is a distinct audit outcome and verifiers never mint keys into a root under audit.
- **Canary precedes production; rollback stays executable.** Every promotion records its parent as rollback target; `rollback()` must keep working from the ledger alone.
- **Claims language** (report 21.1): this repo is "governed system optimization" infrastructure. Do not describe it as autonomous or open-ended RSI anywhere, including docstrings, commit messages and demos.
