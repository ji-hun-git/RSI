# Roadmap

Stages 1-4 from `TECHNICAL_REPORT.md` section 19, rendered as checklists. A box is ticked only where this repository actually implements the item today; substitutions are noted inline. See `docs/DECISIONS.md` for why the substitutions exist.

## Stage 1: Minimal research prototype (report 19.1)

Research objective: can one frozen agent-system bundle execute software tasks reproducibly, emit complete evidence and support a fair manual candidate comparison?

Core components:

- [x] `MissionSpec` and `SystemBundle` canonical schemas (`foundry.contracts`, exported JSON Schemas in `schemas/`)
- [x] Event ledger (SQLite, append-only, hash-chained, signed tip checkpoint, JSONL export/import)
- [x] Object store (content-addressed `ArtifactStore`, digest re-verified on read)
- [x] Deterministic tests (exact-match oracle; fixture corpus with development/protected/retention/adversarial roles)
- [x] Manual experiment runner (paired `ExperimentController`: matched tasks, per-task seeds, equalized budgets, control arm mandatory, blind holdout, leakage check, bootstrap analysis)
- [x] Rollback to parent (`DeploymentController.rollback`, exercised in the demo and tests)
- [x] Runtime boundary with crash/resume/cancel/duplicate-suppression conformance (`RuntimeAdapter` protocol; `DeterministicRuntime` reference implementation, ledger-only recovery)
- [ ] LangGraph adapter (the protocol seam exists at `src/foundry/runtime/adapter.py`; the adapter itself belongs in `adapters/runtimes/langgraph/`)
- [ ] OpenHands coding worker (seam: `foundry.contracts.WorkerLike`; home: `adapters/coding/openhands/`)
- [ ] mini-SWE-agent baseline worker (home: `adapters/coding/mini_swe_agent/`)
- [ ] Basic trace UI (`foundry verify` / `foundry lineage` / `foundry replay` are the current observability surface; no UI)

Scope constraints honored: local single-machine deployment, human promotion only (level-2 changes require a non-proposer A1 approval; the PDP's level 3+ mutation surface is empty).

### Stage-1 exit criteria (report 19.1) and current status

| Exit criterion | Status |
|---|---|
| At least 95% required event coverage on fixtures | Partially met. The fixture workflow events every lifecycle transition it has (compile, start, per-node start/complete, resume, duplicate suppression, cancel, complete with output digest), and `tests/test_e2e_replay.py` asserts completeness for the demo story. There is no automated coverage meter against the full 15.2 vocabulary yet. |
| Exact bundle resolution | Met. Bundles are content-addressed, re-verified on load and pinned into every `MissionSpec`; a mission cannot start under a bundle other than the one its spec names. |
| Crash/replay and duplicate-action tests pass | Met. `tests/test_runtime.py` covers resume-from-ledger, cancel semantics and duplicate suppression; `tests/test_e2e_replay.py` replays recorded missions to identical output digests. |
| 20+ paired candidate/control experiments reproducible | Not met as a recorded research campaign. The infrastructure reproduces any experiment bit-for-bit (`foundry verify` recomputes the paired analysis from seeds and events; the capstone test does it on two seeds), but no registered 20-experiment series has been run and archived. This is the next protocol milestone (see `research/protocols/STAGE1_PROTOCOL.md`). |
| Rollback restores parent artifact and configuration | Met. Rollback resolves the recorded parent from the ledger projection and restores it as active; the demo asserts S0 is active after rollback. |

## Stage 2: Modular Agent Foundry (report 19.2)

- [ ] Universal module manifest enforcement (the `ModuleManifest` contract exists; registry-side conformance evidence does not)
- [ ] Conformance SDK and seeded-incompatibility detection
- [ ] Module registry with hot-swap tests (3+ worker modules, 2+ tool providers)
- [ ] Capability gateway on the tool path
- [ ] Memory staging, typed layers and provenance/deletion tests (contracts exist in `foundry.contracts.memory`; no service)
- [ ] Context builder producing `ContextPackage`
- [ ] PydanticAI worker adapter, MCP tool adapter
- [ ] Signed bundle supply chain (Cosign/SBOM grade; Stage 1 has HMAC dev signing)
- [ ] Lineage and experiment dashboard

## Stage 3: Bounded self-improvement (report 19.3)

- [ ] Diagnosers over mission cohorts
- [ ] GEPA/DSPy proposal adapter (`adapters/optimizers/gepa_dspy/`), typed mutation library
- [ ] Experiment scheduler with search-budget accounting
- [ ] Blind holdout service with rotation (Stage 1 has the in-process vault)
- [ ] Retention and adversarial suites at scale
- [ ] Shadow/canary deployment with automatic (trigger-driven) rollback in production traffic
- [ ] Two accepted descendant generations on fresh cohorts with complete cost accounting

## Stage 4: Research-grade RSI platform (report 19.4)

- [ ] Evaluator cross-audit and benchmark rotation
- [ ] Ancestor re-evaluation and causal analysis over generations
- [ ] Multi-runtime conformance
- [ ] Incident corpus, governance committee workflows
- [ ] Privacy-preserving research exports; independent reproduction from released fixtures

## First 90-day build sequence (report 19.5)

1. **Weeks 1-2: DONE.** Canonical `MissionSpec`, `SystemBundle` and event schemas frozen (`foundry.contracts`, `schemas/`); fixture-only ledger and bundle resolver implemented (`foundry.ledger`, `foundry.registry`).
2. **Weeks 3-4: partially done.** The no-model deterministic sample workflow with crash, resume, cancel and duplicate suppression is done (`DeterministicRuntime`); the LangGraph `RuntimeAdapter` is not started.
3. **Weeks 5-6: not started.** OpenHands and mini-SWE-agent integration in isolated repositories.
4. **Weeks 7-8: partially done.** Deterministic test service (oracle/harness), project policy (PDP) and capability issuance exist; a tool-path capability gateway and operator trace/evidence screens do not.
5. **Weeks 9-10: largely done.** Manual candidate branching (`BundleRegistry.fork`) and matched replay exist; development, retention and adversarial fixtures exist (seeded corpus). Fixtures are generated, not curated task files.
6. **Weeks 11-12: partially done.** The demo is a pilot experiment, `foundry verify` is the evidence-completeness audit, and `research/protocols/STAGE1_PROTOCOL.md` is the internal protocol; the 20+ experiment campaign and failure report remain open.
