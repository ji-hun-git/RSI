# Roadmap

Stages 1-4 from `TECHNICAL_REPORT.md` section 19, rendered as checklists. A box is ticked only where this repository actually implements the item today; substitutions are noted inline. See `docs/DECISIONS.md` for why the substitutions exist.

## Stage 1: Minimal research prototype (report 19.1)

Research objective: can one frozen agent-system bundle execute software tasks reproducibly, emit complete evidence and support a fair manual candidate comparison?

Core components:

- [x] `MissionSpec` and `SystemBundle` canonical schemas (`foundry.contracts`, exported JSON Schemas in `schemas/`)
- [x] Event ledger (SQLite, append-only, hash-chained, signed tip checkpoint, JSONL export/import)
- [x] Object store (content-addressed `ArtifactStore`, digest re-verified on read)
- [x] Deterministic tests (exact-match oracle; fixture corpus with development/protected/retention/adversarial roles)
- [x] Executable-test coding domain (`generate_coding_task_sets`, `DeterministicCodingWorker`, `DeterministicTestService` with trusted-checks restore, command receipts, fail-closed scoring; report 10.2, 14.2, 14.4, 18.3)
- [x] Manual experiment runner (paired `ExperimentController`: matched tasks, per-task seeds, equalized budgets, control arm mandatory, blind holdout, leakage check, bootstrap analysis)
- [x] Rollback to parent (`DeploymentController.rollback`, exercised in the demo and tests)
- [x] Runtime boundary with crash/resume/cancel/duplicate-suppression conformance (`RuntimeAdapter` protocol; `DeterministicRuntime` reference implementation, ledger-only recovery)
- [x] LangGraph adapter (`foundry.adapters.langgraph_runtime.LangGraphRuntime`, optional dependency group `langgraph`; pinned byte-equivalent to the deterministic reference by `tests/test_runtime_conformance.py`)
- [ ] OpenHands coding worker (seam: `foundry.contracts.WorkerLike` + `make_coding_run_arm`, fully specified by the coding domain; blocked on LLM keys and a real sandbox behind `run_checks`, see ADR-008 and `adapters/coding/openhands/README.md`)
- [ ] mini-SWE-agent baseline worker (same seam and blockers; also needs a POSIX shell, `adapters/coding/mini_swe_agent/README.md`)
- [x] Basic trace UI (`foundry.dashboard` + `foundry dashboard --root DIR`: a self-contained HTML trace/lineage/governance/evolution view, read-only projection over the ledger, built to report 15.4's useful-not-harmful spec; ADR-013)

With the trace UI complete, every report 19.1 Stage-1 exit criterion and core-component item is now met.

Scope constraints honored: local single-machine deployment, human promotion only (level-2 changes require a non-proposer A1 approval; the PDP's level 3+ mutation surface is empty).

### Stage-1 exit criteria (report 19.1) and current status

| Exit criterion | Status |
|---|---|
| At least 95% required event coverage on fixtures | Met. `foundry.evaluation.coverage` measures coverage against declared vocabularies; `foundry coverage --root` audits a state root (demo roots score 100%), and the fixture suite pins the interruption vocabulary (resume, duplicate suppression, node failure, cancel) on top (ADR-012). |
| Exact bundle resolution | Met. Bundles are content-addressed, re-verified on load and pinned into every `MissionSpec`; a mission cannot start under a bundle other than the one its spec names. |
| Crash/replay and duplicate-action tests pass | Met. `tests/test_runtime.py` covers resume-from-ledger, cancel semantics and duplicate suppression; `tests/test_runtime_conformance.py` pins the same behavior for every installed runtime adapter (deterministic and LangGraph); `tests/test_e2e_replay.py` replays recorded missions to identical output digests. |
| 20+ paired candidate/control experiments reproducible | Met. Registered campaign v1 (pre-registered in `research/preregistrations/STAGE1_CAMPAIGN_V1.md`, 12 slugify + 8 coding experiments) is archived under `research/analyses/` and `research/reports/` with its full hash-chained event log; all six pre-registered predictions held, and CI recomputes sample rows bit-for-bit from the registered seeds (ADR-012, `tests/test_campaign.py`). |
| Rollback restores parent artifact and configuration | Met. Rollback resolves the recorded parent from the ledger projection and restores it as active; the demo asserts S0 is active after rollback. |

## Stage 2: Modular Agent Foundry (report 19.2)

- [x] Universal module manifest enforcement (`foundry.modules.ModuleRegistry` admits a module only with passing, optionally signed conformance evidence bound to the manifest digest; version immutability enforced; ADR-015)
- [x] Conformance SDK and seeded-incompatibility detection (`WorkerConformanceHarness`: determinism / statelessness / output-shape / declared-input checks; nondeterministic, stateful, wrong-shape and crashing workers are detected and refused; `tests/test_modules.py`)
- [~] Module registry with hot-swap tests: the registry, the report 17.3 shadow-execution replacement check (`check_replacement`), and runtime resolution (`ModuleResolvingRuntime` resolves a bundle's `module_refs` through the conformance-gated registry, so a mission runs only an admitted module; ADR-015/017) exist; a tool-provider conformance suite now gates tool admission (`ToolConformanceHarness` + `ToolGateway.register_conformant`, side-effect-aware, ADR-018); the full 3-worker/2-tool-provider hot-swap bar remains open
- [x] Capability gateway on the tool path (`foundry.tools.ToolGateway`: capability-bound, deny-by-default, discovery-not-authorization, SSRF/egress blocking, per-call ledger receipts, untrusted output, output-size cap, authorization-checked idempotent replay; ADR-016/020)
- [ ] Memory staging, typed layers and provenance/deletion tests (`foundry.memory.MemoryService` implements staging/quarantine, provenance-required promotion, contradiction, expiry and filtered retrieval as an event-sourced projection, ADR-009; `MemoryConsolidator` is the deterministic 11.5 producer that stages recurring-pattern claims and negative lessons from mission episodes, ADR-014; the privacy deletion/redaction workflow and model-assisted extraction remain open)
- [x] Context builder producing `ContextPackage` (`foundry.memory.ContextBuilder`: cited evidence, warnings for contradicted/expired items, explicit token budget with omitted-item count, retrieval trace, MEMORY_SHOWN events)
- [~] Tool-using workers under governance (`foundry.tools.ContextualWorker` + `ToolAugmentedRuntime` runs a tool-using worker with a least-privilege per-mission capability; every tool call authorized + receipted in the mission ledger; ADR-019). PydanticAI worker adapter and a real MCP tool adapter behind the gateway remain open.
- [ ] Signed bundle supply chain (Cosign/SBOM grade; Stage 1 has HMAC dev signing)
- [ ] Lineage and experiment dashboard

## Stage 3: Bounded self-improvement (report 19.3)

- [x] Diagnosers over mission cohorts (`foundry.improvement.EvidenceDiagnoser`: read-only failure-signature grouping with support minimum and frozen-config attribution; causal accuracy remains open research, RQ1)
- [x] Model-backed proposal adapter (`foundry.adapters.openai_proposer.OpenAIReflectiveProposer`, optional group `openai`: fail-closed output validation, value domains, ledgered model evidence, live loop run under full governance, ADR-011; GEPA/DSPy library wrappers for evolutionary candidate search remain open behind the same `ProposerLike` seam)
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
2. **Weeks 3-4: DONE.** The no-model deterministic sample workflow with crash, resume, cancel and duplicate suppression is done (`DeterministicRuntime`), and the LangGraph `RuntimeAdapter` (`LangGraphRuntime`) passes the same conformance suite with a byte-identical canonical event stream (`tests/test_runtime_conformance.py`).
3. **Weeks 5-6: substrate done, agents blocked.** The coding-task domain with executable-test oracles, trusted-checks restore, command receipts and fail-closed scoring exists and carries full paired experiments (`tests/test_coding_domain.py`); the OpenHands/mini-SWE-agent integrations themselves are blocked on LLM keys plus a real sandbox behind the same `run_checks` interface (ADR-008).
4. **Weeks 7-8: partially done.** Deterministic test service (oracle/harness), project policy (PDP) and capability issuance exist; a tool-path capability gateway and operator trace/evidence screens do not.
5. **Weeks 9-10: largely done.** Manual candidate branching (`BundleRegistry.fork`) and matched replay exist; development, retention and adversarial fixtures exist (seeded corpus). Fixtures are generated, not curated task files.
6. **Weeks 11-12: partially done.** The demo is a pilot experiment, `foundry verify` is the evidence-completeness audit, and `research/protocols/STAGE1_PROTOCOL.md` is the internal protocol; the 20+ experiment campaign and failure report remain open.
