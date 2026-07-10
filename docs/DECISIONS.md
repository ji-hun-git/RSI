# Decision records

ADR-style records for the places where this Stage-1 implementation deviates from, or narrows, the recommendations in `TECHNICAL_REPORT.md`. Schema changes to `foundry.contracts` require a new record here (see `CLAUDE.md`: contracts are frozen).

## ADR-001: Single installable package instead of the report 17.1 multi-package monorepo

- **Context.** Report 17.1 proposes a monorepo with separate `packages/` (contracts, event-ledger, policy, registry, ...) plus `apps/` and `adapters/`. Stage 1 is one small reference implementation maintained by one team.
- **Decision.** Ship one installable distribution (`agent-foundry`) with one import root (`foundry`), keeping the report's module boundaries as subpackages (`foundry.contracts`, `foundry.ledger`, `foundry.policy`, ...) that depend on each other only through the structural protocols in `contracts/protocols.py`.
- **Consequences.** One `pip install -e .`, one test run, no cross-package versioning overhead. The boundaries are preserved logically, so splitting into real packages later is a mechanical move. The top-level `adapters/`, `modules/`, `bundles/`, `benchmarks/`, `policies/` and `research/` directories from 17.1 already exist as data/adapter homes.

## ADR-002: SQLite plus file store instead of Postgres/S3

- **Context.** Report 16.1 recommends PostgreSQL + pgvector and an S3-compatible object store. Stage 1 must run locally on Windows and POSIX with zero services, and `foundry verify` must audit a root directory as a self-contained evidence package.
- **Decision.** `EventLedger` is a single-file SQLite database (append-only schema, hash chain, signed tip checkpoint); `ArtifactStore` and `BundleRegistry` are content-addressed files under the same root.
- **Consequences.** A foundry root is portable, diffable and auditable offline. Consumers depend on `LedgerLike` and `ArtifactStoreLike`, not on SQLite or the filesystem, so a Postgres/S3 backend is a drop-in replacement behind the same protocols. Concurrency is deliberately modest (BEGIN IMMEDIATE serialization), which is sufficient for Stage-1 workloads.

## ADR-003: HMAC dev signing as the Sigstore stand-in

- **Context.** The report calls for Cosign/Sigstore-grade signing of bundles and governance records (16.1, 14.5). Stage 1 needs the full sign/verify workflow exercised without external infrastructure.
- **Decision.** `HMACSigner` (HMAC-SHA256, key in a local file) signs events, bundles, promotion decisions and ledger checkpoints. Verifiers load keys with `HMACSigner.load` and never mint keys into a root under audit; a missing key is reported as its own outcome, never as forgery.
- **Consequences.** Integrity and signer identity are real; non-repudiation is not (a symmetric key can both sign and verify). Every trust decision flows through `registry/signing.py` and the `SignerLike` duck types, so swapping in asymmetric signatures changes one module.

## ADR-004: Deterministic fixture worker and slugify corpus instead of LLM workers

- **Context.** Report 18.4 Phase A validates infrastructure on deterministic fixture missions before any model runs; the Stage-1 exit questions (event completeness, replay, fair comparison) are unanswerable with a stochastic worker in the loop.
- **Decision.** `FixtureWorker` is a pure function of `(task_input, config, seed)` whose `strategy` config selects a naive or robust slugify transformation; `generate_task_sets(seed)` produces the four-role corpus, with `robust_slugify` as the single source of ground truth for both the oracle and the robust strategy.
- **Consequences.** Candidate-vs-control experiments have a known answer, replay is bit-exact, and `foundry verify` can recompute the full paired analysis from seeds alone. `WorkerLike` is the seam: OpenHands and mini-SWE-agent integrate behind the identical `invoke` contract without touching the control plane.

## ADR-005: Injected callables (RunArm/Score) decouple the experiment controller from the runtime

- **Context.** The experiment controller must compare arbitrary workers under arbitrary bundles without importing any runtime, and the vault must be able to execute candidates on protected tasks without revealing ground truth.
- **Decision.** `ExperimentController.run` takes `run_arm: (bundle, task, seed) -> output` and `score: (task, output) -> float` as arguments; the protected role is executed only through `HoldoutVault.run_blind`, which wraps `run_arm` in a redacted view and applies the seal-time scorer internally.
- **Consequences.** The controller is runtime-agnostic and trivially testable; scoring for open roles is caller-supplied while protected scoring is vault-owned, which is exactly the trust split report 14.1 requires. The same callables are reused by `verify`'s independent re-analysis path.

## ADR-006: Python 3.11 floor

- **Context.** Report 16.1 recommends Python 3.12+. The development and CI machines in scope for Stage 1 include 3.11 interpreters, and nothing in the codebase requires 3.12 features.
- **Decision.** `requires-python = ">=3.11"` with ruff targeting `py311`; CI exercises 3.11 and 3.12 on Linux and Windows.
- **Consequences.** Broader machine reality coverage at zero feature cost. Corpus generation and bootstrap analysis draw randomness only through `random.Random.random()` (the one generator method with a documented cross-version stability guarantee), so results are identical across interpreter versions. Revisit the floor when a 3.12-only feature earns its keep.

## ADR-007: Adapter code lives in src/foundry/adapters/ behind optional dependency groups

- **Context.** Report 17.1 places adapters in a top-level `adapters/` tree, which in the multi-package monorepo would be independently installable packages. ADR-001 collapsed Stage 1 into a single installable package, so a separately packaged adapter tree would reintroduce exactly the packaging overhead ADR-001 removed, while an adapter inside the core dependency set would force LangGraph onto every user of the dependency-free core.
- **Decision.** Adapter implementations live in `src/foundry/adapters/` (e.g. `langgraph_runtime.py`) guarded by optional dependency groups in `pyproject.toml` (`pip install agent-foundry[langgraph]`); importing the module without the extra raises with the install hint. The top-level `adapters/` directories remain the per-adapter documentation and the report-layout anchor. Shared runtime behavior was extracted to `foundry.runtime.LedgerBackedRuntime` and `foundry.runtime.fixture_workflow` so adapters supply scheduling only, never record semantics, and `tests/test_runtime_conformance.py` runs the full RuntimeAdapter behavior suite against every installed runtime plus a byte-equivalence check against the deterministic reference.
- **Consequences.** The core stays dependency-light and the canonical event stream is runtime-invariant by construction, which is the report 9.3 requirement stated as a test. When an adapter graduates to its own distribution (Stage 2+), the module moves out with its optional group and the conformance suite comes along unchanged.

## ADR-008: Executable-test coding domain with a trusted-checks test service, before any model-backed coding agent

- **Context.** Report 18.3 makes "small software tasks with executable tests" the primary first domain, and HANDOFF queued OpenHands/mini-SWE-agent workers next. But real agent runs need LLM keys and a real sandbox, neither of which exists in Stage 1, and the report's own known failure mode "edits tests to fit incorrect implementation" (Appendix A) plus threat "tamper with tests" (14.2) must be answered by infrastructure, not by trusting the worker.
- **Decision.** Ship the domain substrate first, fully deterministic: `foundry.workers.coding_tasks` (tiny buggy repos + assertion scripts, four roles, generated by construction from seed and index), `DeterministicCodingWorker` (pure repair strategies; robust reproduces the hidden ground truth exactly), and `foundry.evaluation.DeterministicTestService`, which materializes candidate output in an ephemeral workspace, force-restores the trusted checks file, executes with a hard timeout and emits command receipts (14.4). Scoring untrusted output is fail-closed (malformed JSON, path traversal, timeout all score 0.0). Workers stay pure functions; only the test service executes anything.
- **Consequences.** Paired experiments now run on run-the-checks evidence with a known answer, and the test-tampering defense is a pinned test rather than an assumption. The local subprocess is documented as a determinism convenience, NOT a security sandbox: model-generated code must not execute here, so the OpenHands/mini-SWE adapters (whose `WorkerLike` seam and task shape this domain now specifies exactly) remain blocked on a real sandbox behind the same `run_checks` interface. That ordering is the report's own stage gating (19.6) applied to ourselves.
