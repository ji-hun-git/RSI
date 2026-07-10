RESEARCH-GRADE SYSTEMS ARCHITECTURE

# Modular RSI Agent Foundry

Critical Technical Audit and Reference Architecture for Bounded Recursive Self-Improvement

Investigation date: 10 July 2026  |  Scope: model-agnostic agent-system improvement

Direct verdict

The concept is technically feasible now as an experimental control plane for versioned agent systems. It is not defensible as unrestricted or open-ended RSI. The credible research claim is narrower and stronger: a human-governed system can use its own traces to propose bounded changes to prompts, skills, memory policies, routing and workflows; test those changes against protected evidence; retain improvements; reject regressions; and repeat the cycle under immutable security and approval constraints.

Document control

Decision

Prepared from

Recursive Agent Foundry baseline concept and Modular RSI Agent Foundry research brief

Primary framing

Experimental agent-system control plane; not a monolithic autonomous agent

Recommended core

Event-sourced governance layer around one durable workflow runtime

Initial task domain

Small software and web-application production tasks with executable tests

Self-modification boundary

Prompts, skills, retrieval, routing, workflow and selected evaluation artifacts

Protected root

Human authority, policy engine, audit ledger, secret boundaries, holdout vault and rollback

Evidence standard

Paired experiments, protected holdouts, capability-retention tests and multi-objective gates

Research status

Feasible research platform; substantial work remains before production deployment

Prepared as a critical design report, not an endorsement of every element in the original concept.

# Contents

1. Direct verdict on the idea

2. Precise definition of the proposed RSI

3. Research methodology and sources inspected

4. Comparative framework matrix

5. What existing systems do well

6. What existing systems consistently lack

7. Critical flaws in the original concept

8. Reconstructed system concept

9. Final architecture

10. Component-by-component specification

11. Memory architecture

12. Bounded RSI algorithm

13. Evaluation and promotion gates

14. Security and governance

15. Observability and visualization

16. Build-versus-borrow decisions

17. Repository and schema design

18. Experimental validation plan

19. Implementation roadmap

20. Open research questions

21. Claims that remain speculative

22. Strongest potential research contribution

Appendices: manifests, schemas, pseudocode, source catalog and glossary

How to read evidence labels

Implemented means verified in official code or documentation. Research result means reported in a primary paper and not independently reproduced here. Project claim means a repository or vendor claim that should not be treated as comparative proof. Proposed means this report recommends the design but it is not yet implemented.

# 1. Direct verdict on the idea

  VERDICT: PROCEED, BUT NARROW THE CLAIM AND REBUILD THE CONTROL MODEL  

The central idea survives critical review: a modular agent platform can improve persistent parts of its own operating system without modifying foundation-model weights. The technically defensible object of improvement is the surrounding cognitive and operational architecture: prompts, skills, task decomposition, memory policies, context construction, model routing, tool permissions, workflow topology, tests, stopping rules and selected parts of the improvement process. The original baseline correctly emphasizes versioning, sandbox experiments, rollback, human approval and the distinction between product-level and meta-level work. Those are the right foundations. [U1][U2]

The proposed implementation should not be described as an autonomous artificial organization that freely rewrites itself. It should be described as a research platform that manages controlled experiments over versioned agent-system configurations. This change in framing is not cosmetic. It determines the architecture. A free-form multi-agent conversation is a poor substrate for reliable self-modification; a versioned experiment control plane with agents as replaceable workers is a plausible substrate.

The most important design change is to separate four powers that the original concept partially combines: proposing a change, executing a candidate, evaluating evidence and authorizing promotion. No single agent, model family or workflow should possess all four powers. The system may generate a proposal about itself, but production activation must be decided by deterministic policy, independent evaluation and, at higher impact levels, a human approver.

The second major change is to replace role names with explicit module contracts. Butler, Director, Memory Steward, Positive Manager and Negative Manager are useful narrative labels, but labels do not establish software boundaries. Some of those duties are deterministic infrastructure; others are semantic tasks suitable for models. The architecture should therefore define modules by inputs, outputs, permissions, state, budgets, conformance tests and version lineage, not by persona.

The third major change is to make the canonical record event-sourced. Agent messages, tool calls, memory reads and writes, artifacts, tests, approvals, costs and state transitions must be captured as immutable events. Memory graphs, dashboards and workflow views should be projections from that evidence. This gives the system a reproducible history, avoids silent memory rewriting and permits later re-evaluation when judges or rubrics change.

## 1.1 What should be retained

- Bounded self-modification rather than unrestricted rewriting.

- Protected components: human authority, security boundaries, audit requirements, rollback and approval policy.

- Persistent version lineage for agents, workflows, memory policies and evaluators.

- Sandboxed comparative experiments rather than immediate prompt rewriting.

- Separation of source, semantic, procedural, episodic and working memory.

- A human-facing view of product state and system-change state.

- Resource-aware optimization over quality, cost, latency, stability and risk.

- A staged roadmap that begins with prompts, skills, routing and workflow changes before code-level self-modification.

## 1.2 What should be modified or removed

Original element

Decision

Reason

Butler agent

Split

Use a deterministic control API and UI. An optional explanation agent may summarize evidence but cannot approve or mutate production.

Director agent

Split

Use a deterministic mission compiler plus an optional semantic planner. Scheduling, retries and termination are runtime policies.

Memory Steward agent

Replace

Use governed storage and deterministic ingestion services; use models only for extraction, linking and contradiction hypotheses.

Context Engineer

Retain as capability

Implement as a typed context-builder pipeline, with optional agentic query planning and deterministic budget enforcement.

Builder-Designer-User loop

Modify

Keep as task-specific workers, but add deterministic testing and invoke specialist roles only when risk or task type justifies them.

Positive Manager

Rename and constrain

Success-attribution analyzer. Produces evidence and hypotheses, never memory writes or promotion decisions.

Negative Manager

Rename and constrain

Failure-and-risk analyzer. Produces counterevidence, regressions and candidate guardrails; it has no veto by itself.

Policy Governor agent

Remove as agent

Promotion authority belongs to deterministic policy, protected evaluator roots and human approval.

Agent genome

Replace terminology

Use signed, versioned module manifests and immutable bundles.

Strategy-game dashboard

Defer visual theme

Build an experiment, trace and lineage dashboard first. A game metaphor can be a later presentation layer.

## 1.3 The recommended product category

The most defensible category is an experimental agent-system control plane or agent foundry. It is not yet an agent operating system because it does not need to own every execution environment. It should not be a framework-of-frameworks that exposes every framework abstraction directly; that would create an unstable compatibility surface. Instead, it should define a small canonical contract and connect selected runtimes through adapters.

The minimum research claim is cumulative configuration improvement. A stronger claim, bounded recursive self-improvement, becomes justified only after the platform shows that a later system version not only performs tasks better but also produces better subsequent change proposals or experiments than its ancestor, under protected evaluation. One successful prompt rewrite is not RSI.

Decision in one sentence

Build the foundry as a secure, event-sourced experiment manager for agent-system configurations; treat agents as replaceable semantic modules inside it, not as the authorities that define truth, security or promotion.

# 2. Precise definition of the proposed RSI

The phrase recursive self-improvement is frequently applied too loosely. The relevant distinction is not whether an agent says it reflected on itself, but whether a persistent system artifact is modified, whether that modification changes future behavior across tasks, and whether the modified system participates in generating or validating later modifications.

Level

Operational test

Persistent artifact

Classification

0. Static automation

Fixed prompts and workflow execute repeatedly.

No persistent change.

Not learning or RSI.

1. Runtime adaptation

The system selects tools, routes or branches within a run.

Ephemeral state or pre-authored policy.

Adaptation, not persistent improvement.

2. Reflection / self-critique

A model critiques or revises its current output.

Current artifact or transient context.

Test-time iteration; not RSI.

3. Prompt or policy optimization

An optimizer searches persistent text parameters.

Prompt, demonstrations or policy text.

Persistent optimization; usually a fixed outer loop.

4. Memory consolidation

Episodes become summaries, facts, warnings or skills.

Memory items and retrieval indices.

Learning-like behavior; not necessarily validated improvement.

5. Workflow optimization

Search changes nodes, edges, roles, models or tool order.

Workflow graph or module configuration.

System optimization; may be meta-learning.

6. Meta-learning

Experience changes how a task family is solved.

Procedure, router, memory or optimizer state.

Cross-task improvement, but recursion is not guaranteed.

7. Bounded RSI

The system proposes and tests allowed changes to itself; promoted versions affect future task and improvement cycles.

Versioned system configuration under immutable boundaries.

The target of improvement contributes to later improvement.

8. Open-ended RSI

The system can expand its own architecture, objectives or improvement machinery with few external bounds.

Potentially code, evaluators, training and goals.

Not established here and not a near-term product claim.

## 2.1 Formal definition used in this report

Bounded recursive self-improvement

A versioned agent system exhibits bounded RSI when it uses evidence from its own operation to propose modifications to an authorized subset of its persistent configuration; evaluates candidate modifications against an independent baseline, protected tasks and constraints; promotes only supported changes; applies them to future missions; and allows the resulting system version to participate in producing or evaluating subsequent modifications, while immutable governance components remain outside the modification boundary.

## 2.2 Necessary conditions

1. Persistent self-reference: the modified artifact is part of the system that will conduct future missions or future improvement cycles.

2. Evidence-backed change: the modification is linked to observed traces, failures, human feedback or measured resource use, not only to an ungrounded model opinion.

3. Counterfactual comparison: the candidate is compared with a baseline or control under matched tasks, models, budgets and seeds where feasible.

4. Protected evaluation: at least part of the evidence is unavailable to the candidate-generation process, limiting overfitting and evaluator gaming.

5. Capability retention: the candidate is tested for regressions on previously supported task strata and safety properties.

6. Versioned deployment: the change has a parent, scope, monitoring period and rollback target.

7. Recursive continuation: the promoted system contributes to at least one later change cycle, so the improvement mechanism is not merely a one-shot external optimizer.

## 2.3 Where the proposed system falls on the spectrum

System state

Level

Why

Original narrative only

Levels 2-5

It describes reflection, memory and workflow changes, but does not by itself establish independent experiments or recursive continuation.

Stage 1 prototype

Levels 2-4

Artifact revision, reflection and human-authored configuration changes with complete logging.

Stage 2 modular foundry

Levels 4-6

Persistent prompt, skill, memory and workflow optimization across tasks.

Stage 3 governed improvement

Level 7

Candidate changes are generated from system evidence, tested against protected tasks, promoted and used by later cycles.

Stage 4 meta-RSI experiments

Level 7 with limited meta-modification

Selected proposal and evaluation policies may change under a higher-assurance root and delayed approval.

Open-ended RSI

Level 8

Outside the intended claim and safety boundary.

## 2.4 What recursion does not mean here

- It does not mean that a language model modifies its own weights.

- It does not mean unlimited nesting of agents or reflection loops.

- It does not mean that every successful episode becomes a permanent rule.

- It does not mean that a system may rewrite the policy that authorizes the rewrite in the same experiment.

- It does not mean that an LLM judge can certify its own candidate without external checks.

- It does not imply an intelligence explosion or monotonic improvement.

# 3. Research methodology and sources inspected

The technical investigation was conducted on 10 July 2026. It prioritized official repositories, official documentation, published papers, protocol specifications and representative open issues or commits. Repository popularity was not used as a quality proxy. Marketing claims are reported as project claims unless supported by a paper, executable benchmark or independent evidence.

The review focused on architecture rather than feature counting. For each runtime or platform, the investigation considered the core abstraction, orchestration and state model, communication, memory, tool interfaces, human intervention, model independence, observability, evaluation, failure recovery, persistence, parallel execution, security boundaries, extensibility and production maturity. For improvement systems, the review asked what artifact is changed, who proposes the change, who evaluates it, what evidence supports acceptance, whether regressions and evaluator gaming are possible, whether prior capabilities are retained and whether the loop is actually recursive.

## 3.1 Frameworks and protocols inspected

- OpenAI Agents SDK and Codex; LangGraph; Microsoft AutoGen and its current successor Microsoft Agent Framework; CrewAI; MetaGPT; Google Agent Development Kit 2.0; Microsoft Semantic Kernel and its successor notice; PydanticAI; Hugging Face smolagents; OpenHands Agent Canvas and Software Agent SDK; SWE-agent and mini-SWE-agent; Anthropic Claude Agent SDK; Model Context Protocol; Agent2Agent protocol; and the Agent Skills open standard. [F01]-[F19]

- Representative issue patterns were inspected for checkpointing, replay, human approval, session boundaries, context mutation, observability, budgets and state consistency. Examples include LangGraph checkpoint/replay issues, OpenAI Agents session-turn requests and Microsoft Agent Framework checkpoint/HITL issues. [F20]-[F22]

- Recent repository activity was verified before treating a project as current. AutoGen and Semantic Kernel were not treated as the recommended Microsoft starting point because their official repositories direct new development toward Microsoft Agent Framework. SWE-agent similarly directs new users to mini-SWE-agent, and the original Letta server repository identifies itself as legacy. [F03][F04][F08][F13][F14][M01]

## 3.2 Improvement systems inspected

- DSPy and MIPROv2; GEPA; TextGrad; AFlow; Language Agents as Optimizable Graphs; EvoAgentX; Self-Refine; Reflexion; ExpeL; Voyager; Self-Taught Optimizer; A Self-Improving Coding Agent; Darwin Godel Machine; and Agent-as-a-Judge. [I01]-[I14]

- The systems were classified by the actual mutable artifact: current output, episodic text, prompt, demonstration set, code, skill library, graph topology, agent scaffold or improvement program.

- Reported benchmark gains were not assumed to transfer to this architecture. The report uses these systems as evidence of feasible mechanisms, not as proof that a combined foundry will improve monotonically.

## 3.3 Memory and observability systems inspected

- Letta/MemGPT, Mem0, Zep/Graphiti, vector retrieval, temporal knowledge graphs, event-sourced storage and version-controlled procedural memory. [M01]-[M06]

- OpenTelemetry GenAI conventions, Phoenix/OpenInference, MLflow tracing and LangSmith observability for traces, datasets, feedback and experiments. [O01]-[O04]

- The memory comparison emphasized provenance, temporal validity, contradiction handling, confidence, forgetting, consolidation, access control, poisoning, human editability and version history rather than recall alone.

## 3.4 Security and governance sources

- MCP Security Best Practices, including confused-deputy risks, token passthrough, SSRF, session hijacking and local-server compromise. [S01]

- OWASP guidance for LLM and agentic applications, the NIST AI Risk Management Framework and Generative AI Profile, and SLSA software-supply-chain provenance. [S02]-[S05]

- Existing security guidance was translated into concrete trust boundaries, capability tokens, signed manifests, egress controls, sandboxing, holdout isolation, audit requirements and rollback policy.

## 3.5 Limits of this investigation

This report is an architecture and research-design study, not an implementation benchmark. It did not execute every framework on a shared task suite, audit every dependency, reproduce reported paper results or verify vendor-managed performance claims. Rapidly evolving repositories can change after the investigation date. The recommended design therefore minimizes dependency on framework-specific state and treats adapters as replaceable.

The report also avoids logging or demanding hidden model chain-of-thought. Reproducibility should be based on observable messages, tool calls, state transitions, model and prompt identifiers, retrieved evidence, outputs, structured rationales when explicitly emitted, and deterministic artifacts. Hidden internal reasoning is neither reliably accessible nor required for scientific traceability.

Methodological rule

No component is selected because it has the most features. A component is selected only when its abstraction can be isolated behind a stable contract and when replacing it later will not invalidate the event ledger, evaluation evidence or governance model.

# 4. Comparative framework matrix

No reviewed framework supplies the whole foundry. The current ecosystem separates into five useful categories: general agent runtimes, durable workflow engines, coding-agent harnesses, memory services and optimization systems. The foundry should adopt one primary runtime and integrate other systems through narrow adapters. It should not try to preserve each framework's native object model.

## 4.1 Current status and architectural fit

System

Core abstraction

Strengths and limitations

Foundry role

2026 status

OpenAI Agents SDK

Lightweight agent runner with agents, handoffs/agents-as-tools, tools, guardrails, sessions and tracing.

Strong ergonomics, guardrails, MCP and sandbox integration; provider support is broad but the design is naturally aligned with OpenAI APIs.

Adapter or worker runtime; not the sole system-of-record.

Active on investigation date. [F01]

LangGraph

Low-level graph/state-machine runtime for long-running, stateful agents with durable execution and interrupts.

Strong checkpointing model, explicit state and workflow control; persistence and replay details remain operationally subtle.

Recommended primary MVP mission runtime, wrapped by the foundry event model.

Active; representative open issues show checkpoint, cancellation and HITL complexity. [F02][F20]

Microsoft Agent Framework

Python/.NET agent and workflow framework with graph workflows, checkpointing, HITL, OTel and declarative agents.

Broad enterprise surface, provider flexibility and strong Microsoft integration; fast evolution and cross-language surface increase migration risk.

Primary alternative to LangGraph, especially in Microsoft environments.

Official successor path for AutoGen and Semantic Kernel. [F03][F04][F08]

Google ADK 2.0

Code-first agent framework with graph workflows, dynamic nodes, task API, HITL and A2A support.

Strong workflow and interoperability concepts; 2.0 introduced breaking evolution from 1.x.

Useful alternative runtime and A2A boundary adapter.

Active with rapid development. [F07]

PydanticAI

Type-safe, model-agnostic agents and graphs with structured outputs, evals, OTel and approval/durability features.

Excellent contracts, validation and Python developer ergonomics; durable orchestration is less central than in LangGraph/MAF.

Recommended canonical Python agent adapter and schema layer.

Active on investigation date. [F09]

CrewAI

High-level role-based Crews plus event-driven Flows and an enterprise control plane.

Fast construction and useful flow abstraction; role semantics and hidden coordination can be too opinionated for controlled experiments.

Adapter and comparison baseline, not core substrate.

Active; project claims should not substitute for independent evaluation. [F05]

MetaGPT

SOP-oriented software-company simulation with role-generated engineering artifacts.

Useful artifact decomposition and software-production examples; role-heavy architecture and older assumptions are not a neutral foundation.

Benchmark/baseline and idea source only.

Repository remains available; not recommended as control plane. [F06]

smolagents

Minimal code-action agents with model/tool independence and optional sandboxes.

Small, inspectable and useful for baselines; local execution is not automatically a security sandbox.

Minimal semantic worker and experimental baseline.

Active and intentionally lightweight. [F10]

OpenHands Software Agent SDK

Coding-agent SDK and agent server with local or ephemeral Docker/Kubernetes workspaces.

Strong coding tools, workspace abstraction, skills and CI integration; domain-specific to software work.

Recommended coding worker backend for Stage 1-2.

OpenHands UI/control center is now distinct from the SDK. [F11][F12]

mini-SWE-agent

Very small bash-only coding agent with linear history and stateless subprocess actions.

Excellent transparent baseline and sandbox portability; deliberately limited orchestration and tool semantics.

Mandatory minimal baseline for coding experiments.

Official SWE-agent repository recommends it as the default successor. [F13][F14]

Claude Agent SDK

SDK around Claude Code with permissions, custom in-process MCP tools and deterministic hooks.

Mature coding harness and permission hooks; tied to Claude Code behavior and distribution.

Optional coding adapter; not the model-agnostic core.

Active on investigation date. [F15]

OpenAI Codex

Local/IDE/cloud coding agent with sandboxes, approvals, instructions, skills, plugins, hooks and app-server interfaces.

Strong production coding environment and governance surface; OpenAI-specific and larger than needed for the canonical contract.

Optional coding adapter and reference for sandbox/approval patterns.

Active and rapidly evolving. [F16]

MCP

Protocol for clients to expose tools, resources and prompts through standardized servers.

Strong tool interoperability; tool descriptions and local/remote servers create material security boundaries.

Use at the tool gateway, never as an implicit trust mechanism.

Current specification and explicit security guidance. [F17][S01]

A2A

JSON-RPC protocol for discovery and collaboration between opaque agent applications.

Useful for organizational or cross-service boundaries; too coarse and network-heavy for every internal module call.

Use only at external agent-service boundaries.

Linux Foundation project contributed by Google. [F18]

Agent Skills

Portable folder standard with SKILL.md, scripts, references and progressive disclosure.

Simple, versionable and increasingly portable; execution permissions and supply-chain provenance remain external concerns.

Adopt as one skill-package format behind signed manifests.

Open standard with multiple ecosystem implementations. [F19]

## 4.2 Capability comparison

Runtime

Model independence

State model

HITL

Observability

Evaluation

Replacement fit

OpenAI Agents SDK

Medium

Sessions

Strong built-in

Strong tracing

External

Good

LangGraph

High

Explicit graph state + checkpointers

Strong interrupts

LangSmith/OTel ecosystem

External

Very good

Microsoft Agent Framework

High

Workflow state + checkpoints

Strong

OTel and integrations

Labs/Foundry evals

Very good

Google ADK 2.0

High

Workflow/task state

Strong

Built-in and ecosystem

External/built-in tools

Very good

PydanticAI

High

Typed deps/messages/graphs

Tool approval

OTel/Logfire

Pydantic Evals

Very good

CrewAI

Medium-high

Crew/flow state and memory

Supported

Control plane/telemetry

External

Moderate

smolagents

High

Simple history/state

Application-defined

Basic

External

Good for small modules

OpenHands SDK

Medium-high

Conversation/workspace state

Application-defined

Agent server/trajectories

Coding benchmarks

Good in coding domain

mini-SWE-agent

High

Linear transcript

Application-defined

Trajectory browser

Benchmark harness

Excellent baseline

Claude Agent SDK

Low-medium

Session/client state

Permissions/hooks

Callbacks/traces

External

Vendor adapter

## 4.3 Improvement-system comparison

System

Artifact improved

Proposer / mechanism

Acceptance evidence

Recursive?

Foundry interpretation

Self-Refine

Current answer

Same model gives feedback and revises

Task metric / human preference

No

Reflection, not persistent system improvement. [I06]

Reflexion

Episodic verbal lessons

Agent reflects on external or simulated feedback

Environment reward and task result

No

Cross-trial adaptation, but system structure remains fixed. [I07]

ExpeL

Extracted lessons and experience retrieval

Agent learns from training episodes

Downstream task performance

No

Memory consolidation and transfer. [I08]

Voyager

Executable skill library and curriculum

LLM proposes programs from environment feedback

Game progress and self-verification

Partial

Open-ended skill acquisition, not architectural RSI. [I09]

DSPy / MIPROv2

Prompts, demonstrations and LM program parameters

Compiler/optimizer searches candidates

User-defined metric on train/validation data

No

Powerful persistent optimization with a fixed optimizer. [I01][I02]

TextGrad

Text variables including prompts, code and solutions

LLM emits textual gradients; optimizer updates variables

Natural-language loss and task metric

No

General text optimization; evaluator quality is critical. [I04]

GEPA

Any textual parameter, including prompts, code and architecture descriptions

Reflective mutation and Pareto-aware evolutionary search

User-provided evaluator plus trace side information

No by default

Best candidate generator for bounded text/config changes; cannot be promotion authority. [I03]

AFlow

Code-represented workflow graph

MCTS modifies nodes/edges using execution feedback

Benchmark score and cost

No

Automated workflow search; vulnerable to benchmark overfit. [I05]

GPTSwarm

Prompts and computational graph connectivity

Graph optimizers change nodes and edges

Task evaluation

No

Useful formalization of agents as optimizable graphs. [I11]

EvoAgentX

Prompts, tools and workflow topology

Unified evolutionary layer using multiple optimizers

Benchmark evaluation

No

Useful research platform; outer evolution policy remains fixed. [I12]

STOP

The improver scaffolding program

Seed improver uses an LM to improve itself

Utility on downstream programs

Yes, narrowly

Early recursive scaffold experiment; fixed model and small task setting. [I10]

Self-Improving Coding Agent

Agent source code and tools

Coding agent edits its own scaffold

SWE-bench and related tasks

Yes, bounded

Close analogue for code-level RSI; benchmark and sandbox dependence remain. [I13]

Darwin Godel Machine

Archive of self-modified coding agents

Agents generate descendants; archive supports open-ended search

Coding benchmark performance

Yes

Strongest empirical RSI analogue reviewed; still benchmark-bounded and externally governed. [I14]

Agent-as-a-Judge

Evaluator behavior, not necessarily the actor

Agent examines outcomes and intermediate trajectory

Agreement with human annotations

No

Useful evaluator component, but must be calibrated and protected from self-preference. [I15]

## 4.4 Memory-system comparison

Approach

Primary representation

Strength

Limitation

Recommended role

Letta / MemGPT

Stateful agent memory and context management

Agent-centric persistence and memory tools

Current product architecture has moved; the original server repository is legacy.

Use as conceptual/adapter reference, not canonical storage. [M01][M02]

Mem0

Extracted user/session/agent memories with hybrid retrieval

Accessible SDKs, entity linking, temporal retrieval and benchmark tooling

Managed service includes proprietary optimizations; memory acceptance is not a governance system.

Optional personalization adapter; not source of truth. [M03]

Graphiti / Zep

Temporal context graph with episodes, facts and validity windows

Strong provenance, temporal history and hybrid retrieval

Graph construction uses models; operational complexity and graph backends must be managed.

Optional temporal read model over canonical events. [M04]

Vector database only

Embedded chunks and metadata

Simple, scalable semantic retrieval

Weak contradiction, time, causality and procedural versioning.

One index, never the memory architecture.

Knowledge graph only

Entities and relationships

Explicit links and graph traversal

Schema/ontology cost; derived graph can become falsely authoritative.

Read model with links back to immutable evidence.

Event-sourced store

Immutable events plus derived projections

Reproducibility, replay, audit, temporal state reconstruction

Requires projection design and careful privacy controls.

Recommended canonical memory/evidence substrate.

Version-controlled files

Prompts, skills, policies and schemas

Human-editable diffs, code review, signatures and rollback

Not sufficient for high-volume episodes or semantic search.

Recommended procedural-memory representation.

Framework decision

Use LangGraph as the first durable mission runtime, Pydantic models as the canonical contract layer, OpenTelemetry as the telemetry contract, Postgres/object storage as the evidence root, OpenHands plus mini-SWE-agent as coding workers, MCP at the tool boundary, and GEPA/DSPy as candidate optimizers. Keep Microsoft Agent Framework as the principal alternative runtime rather than mixing two orchestration kernels in the MVP.

# 5. What existing systems do well

## 5.1 Explicit state and durable execution

LangGraph, Microsoft Agent Framework and Google ADK demonstrate that agent workflows are more reliable when represented as explicit graphs or state machines rather than unconstrained agent chat. Durable checkpoints, interrupts, resumable execution and time-travel or replay features are now normal framework capabilities. This means the foundry does not need to invent a low-level agent loop. It needs to standardize the evidence and governance around that loop. [F02][F04][F07]

The open issue record also shows why the foundry should not equate a framework checkpoint with a scientific record. Cancellation, long tool calls, mutable state, persistence flushing and approval resumption can have edge cases. The foundry must therefore record canonical events outside the selected runtime and test adapter conformance under crash, replay and duplicated-delivery scenarios. [F20]-[F22]

## 5.2 Typed agent and tool interfaces

PydanticAI and similar typed frameworks make structured inputs, outputs and dependency injection practical. MCP provides a common transport for tool discovery and invocation, while Agent Skills provides a simple package convention for procedural knowledge. Together, these systems show that modules can be portable when schemas, capabilities and resources are explicit. [F09][F17][F19]

The lesson is to reuse the portability pattern but add governance fields that the interoperability standards do not provide: write scopes, budget ceilings, security class, test suite, provenance, promotion status, rollback target and signature. A tool protocol is not a trust policy, and a skill folder is not a safe deployment unit.

## 5.3 Coding-agent environments and executable feedback

OpenHands, mini-SWE-agent, Codex and Claude Agent SDK demonstrate effective patterns for repository work: isolated workspaces, explicit shell or editing actions, linear trajectories, tests, permission hooks and resumable sessions. Coding is an attractive first task domain because many outputs can be judged with executable tests, static analysis, accessibility checks and security scanners rather than only subjective LLM scores. [F12][F14]-[F16]

mini-SWE-agent is particularly valuable as a baseline because its linear history and minimal action interface reduce hidden scaffold effects. OpenHands provides the richer worker needed for real product generation. The foundry should keep both: one as a transparent control and one as a capable production worker.

## 5.4 Optimization of persistent text and workflows

DSPy, GEPA and TextGrad establish that prompts and other textual parameters can be treated as optimizable program artifacts. AFlow and graph-optimization systems extend this idea to workflow structure. Their main contribution is not that they guarantee improvement, but that they make candidate generation systematic and separate it from manual prompt editing. [I01]-[I05][I11]

GEPA is especially compatible with the foundry because it can consume complete traces and evaluator side information, propose targeted text changes and maintain a Pareto frontier. The foundry should use it as one proposal generator. It must remain downstream of the evidence ledger and upstream of independent gates. A candidate generator should never own the benchmark vault or promotion decision.

## 5.5 Temporal and provenance-aware memory

Graphiti's episode-to-fact structure, validity windows and source lineage illustrate how agent memory can retain changing facts without overwriting history. Mem0 demonstrates hybrid retrieval and operational memory APIs. Letta demonstrates the value of stateful agents and deliberate memory-management tools. [M01]-[M04]

The combined lesson is that memory should be typed, temporal and source-linked. The foundry should not adopt any one memory product as the canonical truth. It should store immutable evidence first, then build semantic, vector and graph projections that can be regenerated or replaced.

## 5.6 Trace-centered evaluation

OpenTelemetry-compatible tracing, Phoenix, MLflow and LangSmith show that model calls, tools, retrieval, cost, latency, sessions and human annotations can be represented as queryable traces and experiment datasets. Agent-as-a-Judge shows that intermediate trajectory evaluation can add information beyond final-output scoring. [O01]-[O04][I15]

The foundry should adopt these capabilities but add version lineage and promotion semantics. A trace is an observation; an evaluation result is a claim about the observation; a promotion decision is a governed action. These three records must remain distinct.

# 6. What existing systems consistently lack

Missing capability

Why it matters

A framework-neutral system identity

Most systems persist their own agent, graph or session objects. Few define a portable, signed version bundle whose behavior can be compared across runtimes.

Independent promotion governance

Optimization libraries generate and score candidates, while runtimes execute them. Neither typically provides protected holdouts, approval tiers, blast-radius limits and automatic rollback as one protocol.

Causal attribution

A better run may result from sampling variance, model drift, easier tasks or more tokens. Existing systems often record correlation rather than isolate the effect of a proposed change.

Capability-retention guarantees

Aggregate score gains can hide severe regressions on subgroups, safety, latency or previously solved tasks.

Evaluator separation

The same model family often proposes, critiques and judges. This is efficient but creates common-mode error and self-preference.

A trusted benchmark root

Benchmarks are frequently visible to optimizers, static, contaminated or too narrow. Longitudinal RSI needs protected and rotating holdouts.

Governed procedural memory

Skill and memory systems make writing easy, but rarely require experimental evidence, lineage, conflict checks and rollback before a lesson becomes production policy.

Cross-layer lineage

Prompt, workflow, model, memory and evaluator versions are often tracked separately. Reproducing a system version requires all of them plus tool and environment versions.

Meta-improvement safeguards

Few systems specify how an optimizer may change an evaluator without circularly lowering its own acceptance standard.

Scientific resource accounting

Token, cost and latency are logged, but the full cost of search, failed variants, human review and maintenance is often omitted from improvement claims.

## 6.1 The integration gap

The ecosystem is rich in mechanisms and poor in constitutional structure. It is now easy to connect a model to tools, persist a thread, run a graph, inspect traces, search a memory store and optimize a prompt. It remains difficult to prove that a persistent system modification caused a general improvement, did not remove capabilities, did not game its evaluator and can be safely rolled back.

This gap is exactly where the foundry can contribute. It should not compete with every runtime, memory store or coding agent. It should standardize the experiment, evidence and authority model that sits above them.

## 6.2 Why combining every framework would make the problem worse

- Each runtime has different checkpoint, retry, cancellation and tool semantics. A direct framework-of-frameworks would make trajectories incomparable.

- Multiple memory products would create competing write paths and inconsistent truth.

- Multiple tracing schemas would obscure the causal chain between configuration and outcome.

- Framework upgrades would change the experimental substrate during longitudinal studies.

- Security policy would be duplicated in each adapter rather than enforced once at the gateway.

Integration principle

One runtime should own mission control in a given deployment. Other frameworks should appear as leaf workers or alternate experimental backends behind the same contracts, not as co-equal orchestration kernels in the same mission.

# 7. Critical flaws in the original concept

## 7.1 Over-agentization

The original concept assigns agent identities to duties such as memory management, scheduling, policy and approval. Many of these duties are better implemented as ordinary software because their correct behavior can be specified and tested. A model may suggest a relation between two memories; a deterministic service should enforce provenance, retention and write permissions. A model may propose a workflow; a deterministic runtime should execute its state transitions and budgets.

Over-agentization increases nondeterminism, coordination cost and attack surface. It also weakens scientific attribution because a change in one persona can alter multiple hidden interactions. The default should be deterministic infrastructure, with agents introduced only for semantic judgment, open-ended generation or uncertain classification.

## 7.2 Role personas are not module boundaries

Builder, Designer and Mock User are intuitive role names, but they do not define compatibility. A replaceable module needs explicit input and output schemas, permissions, context budgets, failure signals, state-transfer rules and tests. Without these, replacing the model in a slot may silently change tool-call format, confidence semantics or handoff expectations.

The proposed module manifest and conformance suite replace the informal agent genome. Narrative role descriptions may remain as one field, but they are not the architecture.

## 7.3 The memory pool risks becoming an ungoverned belief store

A visually connected memory pool is appealing, but a single store that mixes sources, facts, summaries, hypotheses, failures, prompts and preferences will become contradictory and vulnerable to poisoning. A graph link does not prove a claim. An embedding similarity does not justify retrieval. A successful episode does not justify a universal procedure.

The corrected design separates immutable evidence from derived claims, and separates both from procedural policy. Agents may write observations and candidate lessons to staging areas. Only governed pipelines may promote verified claims or experimentally supported procedures.

## 7.4 Positive and negative managers create an artificial dualism

Success amplification and failure prevention are useful analytical views, but two privileged manager agents are not sufficient evaluators. A successful outcome may be caused by luck, extra cost or an easier task. A failure may reveal a missing capability rather than a rule to prohibit. The system needs outcome evaluation, process diagnosis, safety evaluation and causal experiment design, not merely optimistic and pessimistic commentary.

The corrected architecture retains two complementary analyses as optional diagnosers, but neither can directly write production memory or decide promotion.

## 7.5 Separating process and outcome evaluation too strongly is incorrect

The original idea considered a governor that might inspect only the process. That boundary is untenable. Process quality is meaningful only in relation to outcome, constraints and cost. A fast workflow that produces the wrong artifact is not efficient; a long workflow may be justified for a high-risk task. The foundry therefore uses separate evaluators with a joined evidence record: outcome, process, safety and resource evaluation are independent dimensions, not isolated systems.

## 7.6 The visual metaphor could dominate the research

A strategy-game interface can communicate resource trade-offs and lineage, but it can also encourage anthropomorphism and decorative complexity. The first dashboard should answer scientific and operational questions: Which version ran? What evidence was retrieved? What changed? Which tests improved? Which capabilities regressed? Why was a candidate promoted? Can the exact run be replayed?

Game-like visualizations should be a skin over these data, not the data model.

## 7.7 Missing causal and statistical design

The baseline concept compares candidate versions but does not specify matched experimental design, uncertainty, task stratification, multiple comparisons or stopping rules. Without these, the system will promote noise. The corrected design uses paired trials, repeated seeds, protected holdouts, confidence intervals, non-inferiority gates for retained capabilities and explicit search-budget accounting.

## 7.8 Missing security boundary around the improvement mechanism

A system that can change prompts, skills, tools and evaluators can also expand its permissions indirectly. Tool descriptions may induce unsafe actions; retrieved instructions may poison memory; a candidate may lower an evaluator threshold or hide failures from telemetry. The modification surface must therefore be typed and policy-checked, and the trusted root must remain immutable to the experiment. MCP's own security guidance illustrates that interoperability adds confused-deputy, token, SSRF, session and local-code risks; it does not remove them. [S01]

Unsupported assumption

Problem

Correction

More agents imply more capability

Unsupported. Coordination and correlated failure can dominate.

Add a role only after an ablation shows net value.

A memory graph is learning

Retrieval and consolidation can improve behavior but do not prove learning or generalization.

Measure held-out transfer and harmful retrieval.

Self-critique is RSI

Self-critique can revise one output without any persistent system change.

Reserve RSI for multi-generation, persistent, validated modification.

Human approval alone makes a change safe

Humans may miss subtle regressions or be overloaded.

Use automated gates, clear diffs, scope limits and rollback in addition to approval.

An LLM judge is an objective evaluator

Judges have bias, variance, self-preference and prompt sensitivity.

Triangulate deterministic tests, independent judges and sampled human review.

Every successful strategy should be remembered

This creates rule accumulation and overfit.

Require recurrence, causal evidence and scope-limited promotion.

# 8. Reconstructed system concept

  PROPOSED: A VERSIONED EXPERIMENT CONTROL PLANE FOR AGENT SYSTEMS  

The reconstructed concept is a modular research platform that executes missions through replaceable agent and software modules while maintaining a separate, trusted control plane for evidence, experimentation, security and promotion. It is best described as an agent foundry or experimental control plane, not an agent operating system and not a framework-of-frameworks.

The platform has two linked but independently governed loops. The mission loop produces an artifact under a frozen system bundle. The improvement loop studies completed missions, creates candidate bundle diffs, evaluates those candidates in isolated experiments and promotes only changes that pass protected gates. A production run is never silently modified while it is in progress. The recursive property appears only across version generations: an accepted version becomes the parent that later proposes or enables further changes.

## 8.1 First-principles design rules

Design rule

Operational meaning

Deterministic by default

Use ordinary software for policy, scheduling, validation, storage, retries, budgets, signatures and deployment. Use models where semantic judgment or generation is necessary.

Configuration is the mutable genome

The unit of self-modification is a typed, versioned system bundle, not an unconstrained conversation or model personality.

Evidence precedes memory

Raw source, events and artifacts are immutable evidence. Semantic and procedural memories are governed projections or versioned derivatives.

No self-approval

A proposer cannot also authorize promotion. The evaluator root and policy root are protected from the candidate under test.

One runtime owns control flow

Choose one orchestration kernel per deployment. External workers are invoked through adapters with conformance tests.

Capabilities, not personas

Modules declare input/output contracts, permissions, budgets, tests and failure semantics. Role language is optional metadata.

Paired comparison, not impressions

Every claimed improvement is tested against a frozen baseline under matched tasks, seeds, budgets and environments.

Non-regression is first-class

A candidate must retain protected capabilities and safety properties, not merely raise an aggregate score.

Scope is part of the decision

Promotion can target one module, task family, model, project or canary cohort. Global deployment is never the default.

Rollback is executable

Every promoted bundle names its parent, migration, monitoring window and automated rollback trigger.

## 8.2 Five system planes

Plane

Contents

Authority boundary

1. Human and observability plane

Control UI, mission submission, approvals, trace inspection, experiment comparison, lineage and rollback.

Read broad; write through authenticated commands.

2. Governance and security plane

Policy decision point, capability tokens, secret broker, signed manifests, holdout vault, audit ledger and emergency stop.

Protected root; outside autonomous modification.

3. Mission execution plane

Mission compiler, workflow runtime, model router, semantic workers, tool gateway and deterministic tests.

Runs one frozen system bundle per mission.

4. Evidence and memory plane

Event ledger, artifact/source store, memory staging, projections, context builder and module registry.

Immutable raw evidence; governed derived writes.

5. Experiment and RSI plane

Diagnosers, change proposer, variant generator, sandbox manager, experiment scheduler, evaluation harness and deployment controller.

May create candidate branches but cannot alter trusted roots.

## 8.3 Two-loop operating model

### Mission loop

1. Authenticate the human request, resolve project policy and create an immutable MissionSpec.

2. Resolve a signed SystemBundle that pins agent modules, prompts, skills, models, workflow, tools, memory policy, evaluator set and budgets.

3. Build a task-specific ContextPackage from governed evidence and memory projections.

4. Execute the workflow in a sandboxed workspace while emitting canonical events.

5. Run deterministic and semantic evaluations, preserve artifacts and close the mission without changing the active bundle.

### Improvement loop

1. Select a cohort of completed missions and diagnose repeatable process or outcome failures.

2. Create a typed ChangeProposal with one primary causal hypothesis, explicit target, expected effect, risks and rollback condition.

3. Generate one or more candidate SystemBundle diffs plus an unchanged control.

4. Run candidates and control on matched replay, held-out and adversarial tasks inside isolated sandboxes.

5. Evaluate quality, safety, robustness, cost, latency, reproducibility, maintainability and capability retention.

6. Apply deterministic promotion policy, independent review and the required human approval tier.

7. Canary the accepted bundle, monitor the predicted effect, roll back on trigger and record the complete evidence chain.

## 8.4 Autonomy levels

Level

Mutable surface

Governance rule

Level 0 - Observe only

No persistent self-modification. Log missions, build datasets and validate replay.

Start here.

Level 1 - Memory and retrieval tuning

Adjust retrieval weights, chunking, context budgets, retention and ranking within hard bounds.

Automatic promotion permitted only for low-risk, reversible changes after gates.

Level 2 - Prompt, skill and routing changes

Modify instructions, demonstrations, skills, model-role assignments and handoff schemas.

Human approval for first deployment; later scope-limited automation may be studied.

Level 3 - Workflow and test-order changes

Change topology, parallelism, role composition, stopping rules and test placement.

Always sandboxed; human approval and canary required in initial platform.

Level 4 - Evaluator or improvement-policy changes

Modify metrics, judges, candidate-generation policy, thresholds or benchmark composition.

Protected meta-experiment only; old and new evaluator roots must cross-audit each other. No self-ratification.

Level 5 - Code or training-pipeline changes

Modify trusted runtime code, policy engine, sandbox layer or model-training pipeline.

Outside the near-term autonomous boundary; conventional secure software lifecycle required.

Recommended initial boundary

Implement Levels 0-2 first. Add selected Level 3 changes only after crash-safe event capture, deterministic replay, protected holdouts, signed version bundles and automated rollback are demonstrated. Treat Level 4 as a separate research protocol, not a normal feature flag.

## 8.5 Decision on original components

Original element

Disposition

Reason

Human-facing Butler

Replace with Control UI/API plus optional Explanation Worker

The UI owns commands and approvals; a model may summarize evidence but has no authority.

Director

Split into Mission Compiler and optional Planner Worker

Compiler validates and freezes a plan; runtime owns scheduling, retries and termination.

Memory Pool

Split into evidence store, typed memories and replaceable projections

No mixed universal belief store.

Memory Steward

Replace with Memory Service and governed ingestion jobs

Deterministic access and provenance; model-assisted extraction remains quarantined until validation.

Context Engineer

Retain as Context Builder pipeline

Agentic query planning is permitted inside hard source, token and trust budgets.

Builder / Designer / Mock User

Retain as optional semantic workers

Invoked by task policy; not every mission needs all three.

Positive / Negative Managers

Replace with Success Attribution and Failure/Risk Diagnosers

They produce structured hypotheses and counterevidence only.

Change Synthesizer

Retain as Change Proposer

Must emit typed diffs and a falsifiable evaluation plan.

Variant Generator

Retain as pluggable optimizer

May use GEPA, DSPy, search or human-designed variants.

Sandbox Experimenter

Split into Sandbox Manager and Experiment Controller

Isolation and scheduling are infrastructure; candidate generation remains separate.

Policy Governor

Replace with deterministic Promotion Gate plus human authority

The trusted decision point cannot be an improvable conversational agent.

Strategy-game dashboard

Defer and reinterpret

Build trace, evidence, experiment and lineage views first; game styling is optional presentation.

# 9. Final architecture

The final architecture is organized around a protected control plane and a replaceable execution plane. The mission runtime is deliberately not trusted to define its own evidence, permissions or promotion standard. Every mission is linked to a frozen SystemBundle and every experiment produces a branch with a parent, diff and reproducible environment specification.

Figure 1. System-level architecture. The governance root and canonical evidence ledger remain outside the candidate modification boundary.

## 9.1 System bundle as the unit of identity

A SystemBundle is the complete, content-addressed identity of the behavior under test. It includes the workflow graph; module manifests; prompts and skills; model adapter and parameter policy; tool allowlists; memory and context policy; evaluator versions; resource profile; environment image; and dependency lock. A run that cannot resolve its exact bundle is not admissible evidence for promotion.

The bundle is immutable after signing. Changes create a child bundle with a machine-readable diff. This prevents the common experimental error in which a prompt change, model update, dependency update and test change are bundled together and attributed to one cause.

Bundle field

Contents

Purpose

bundle_id

Content digest plus semantic version

Unique identity and reproducibility.

parent_bundle_id

Previous promoted or experimental parent

Lineage and rollback.

workflow_ref

Versioned graph and state schema

Execution topology.

module_refs

Pinned manifests for agents, tools, skills and services

Replaceability and capability negotiation.

model_policy_ref

Provider, model family, fallback and sampling policy

Model routing and drift control.

memory_policy_ref

Read/write scopes, retrieval and consolidation rules

Context and persistent knowledge behavior.

evaluation_profile_ref

Metrics, datasets, judges and thresholds

Defines evidence without embedding promotion authority.

resource_profile_ref

Token, time, cost, concurrency and human-attention budgets

Comparable operating profile.

environment_ref

Container/microVM image, dependency lock and tool versions

Executable reproducibility.

signature_set

Author, reviewer and policy signatures

Integrity and authorization.

## 9.2 End-to-end data flow

Figure 2. Data flow from a human mission through a frozen execution bundle, evidence capture, evaluation, candidate experimentation and governed deployment.

1. The Control API validates the request and emits MissionRequested.

2. The Mission Compiler creates a MissionSpec and resolves an approved SystemBundle.

3. The Context Builder retrieves evidence through policy-filtered projections and records every source reference.

4. The workflow runtime invokes semantic workers, deterministic services and tools through capability-scoped adapters.

5. The event collector commits state transitions, inputs, outputs, tool calls, costs and artifacts to the canonical ledger.

6. Outcome, process, safety and resource evaluators create versioned EvaluationResults; none modifies the run record.

7. The improvement pipeline converts evidence into candidate bundle branches and executes matched experiments.

8. The Promotion Gate verifies evidence and policy, requests the appropriate human approval and canaries the winner.

## 9.3 Runtime and adapter boundaries

The runtime adapter exposes a small internal interface: compile, start, suspend, resume, cancel, snapshot and emit event. It must not expose native checkpoint objects to downstream modules. The foundry's event and state schemas remain canonical, while runtime-specific checkpoints are opaque recovery artifacts.

Worker adapters expose invoke, stream, cancel, resource report and artifact references. A coding worker may be OpenHands, mini-SWE-agent, Codex or Claude Agent SDK; a semantic worker may use PydanticAI or OpenAI Agents SDK. The same MissionSpec and evaluator profile can therefore compare workers without rewriting the control plane.

## 9.4 Human oversight points

Checkpoint

Trigger

Human authority

Mission acceptance

High-risk domain, external side effects, sensitive data or unusual budget

Approve, edit scope, deny or require additional controls.

Tool action

Irreversible, monetary, privileged or external communication action

Approve specific invocation or grant time-limited capability.

Memory promotion

Unverified claim, sensitive content or new procedural rule

Accept, edit, quarantine or reject.

Candidate experiment

Change touches Level 3+, evaluator, tool permission or broad data scope

Approve experiment scope before execution.

Production promotion

First deployment, moderate/high impact, uncertain evidence or wide scope

Accept candidate and scope, require more tests or reject.

Canary anomaly

Rollback threshold, safety event or unexpected cost/latency

Automatic rollback first; human investigates before re-enable.

Meta-RSI

Any change to evaluator root, thresholds, benchmark composition or approval policy

Two-person or committee review with old-root cross-evaluation.

## 9.5 Deployment profiles

Profile

Policy emphasis

Use

Research

Maximum trace detail, repeated seeds, broad evaluator set, no automatic global promotion.

Architecture and RSI experiments.

High reliability

Conservative model routing, strict gates, narrow tools, larger retention and safety budget.

Important internal workflows.

Low cost

Smaller models, lower candidate count, early stopping and cost-normalized promotion.

High-volume low-risk tasks.

Fast response

Reduced debate, parallel retrieval, cached deterministic checks and bounded context.

Interactive assistance.

Experimental

New modules or topology in isolated namespaces; no sensitive data and no external side effects.

Candidate exploration.

# 10. Component-by-component specification

The following specification contains only components that survive the audit. Each component is marked as deterministic infrastructure, a semantic agent/worker, or a hybrid pipeline. Replacement is governed by the universal module contract in Section 17 and the conformance suite in the module registry.

## 10.1 Human, governance and control components

Component

Type

Inputs

Outputs

Permissions

Failure modes

Evaluation

Replacement

Control UI/API

Deterministic

Mission requests, authenticated commands, approvals and queries

MissionSpec drafts, decisions, views and rollback commands

No direct model or tool credentials; project-scoped access

Missing audit link, stale view, confused approval

API contract, authorization tests, usability study

Replace frontend independently; API is versioned.

Explanation Worker

Agent, optional

Selected evidence, diffs and uncertainty

Plain-language summaries with citations

Read-only; no approval or mutation

Overconfident or selective summary

Citation coverage, calibration, human comprehension

Any model behind a typed summarization contract.

Policy Decision Point

Deterministic

Action, subject, resource, environment and signed policy bundle

Permit, deny, obligations and approval tier

Protected root; no candidate write access

Policy conflict, stale policy, fail-open

Policy unit tests, mutation tests, fail-closed drills

OPA or Cedar adapter; semantic policy content reviewed conventionally.

Capability Issuer

Deterministic

Policy decision, mission identity and requested scope

Short-lived scoped capability token

May mint only bounded, auditable grants

Overbroad or replayed token

Scope, expiry, replay and revocation tests

Pluggable token implementation with stable claims.

Secret Broker

Deterministic

Approved capability and tool identity

Ephemeral secret handle or proxied action

Secrets never enter model-visible context

Leakage, confused deputy, stale credential

Exfiltration tests, rotation and audit

Vault/KMS implementation behind broker API.

Audit Ledger

Deterministic

Signed governance and deployment events

Append-only tamper-evident records

Protected from candidate and runtime mutation

Dropped or reordered event, clock skew

Hash-chain verification and recovery drills

Storage backend replaceable if integrity proof is preserved.

Emergency Stop

Deterministic

Human command or critical detector event

Revoke capabilities, stop schedulers, isolate namespaces

Highest-priority control path

Partial shutdown or unrevoked side effect

Quarterly drills and dependency inventory

Implementation may change; command semantics are fixed.

## 10.2 Mission execution components

Component

Type

Inputs

Outputs

Permissions

Failure modes

Evaluation

Replacement

Mission Compiler

Hybrid

Human request, project policy, available modules

Immutable MissionSpec and acceptance criteria

Read registry/policy; no tool execution

Ambiguous requirements, hidden assumptions

Schema validity, requirement coverage, human correction rate

Semantic planner can change; compiler and schema remain stable.

Workflow Runtime

Deterministic infrastructure

MissionSpec, SystemBundle, context and events

State transitions, work requests and completion

Only capabilities explicitly bound to nodes

Duplicate action, lost state, stalled loop

Crash/replay, idempotency, cancellation and checkpoint conformance

LangGraph first; MAF/ADK adapters later.

Model/Module Router

Hybrid

Task features, profile, registry, budgets and policy

Chosen module/model and fallback plan

May select only approved modules

Cost drift, weak routing, hidden model change

Offline replay, regret, latency and failure-rate metrics

Rule-based first; learned router as candidate module.

Context Builder

Hybrid

Information need, memory policy and evidence projections

Cited ContextPackage with budget and uncertainty

Read only approved scopes; no source rewrite

Missing evidence, contamination, overlong context

Retrieval recall/precision, citation validity, harmful retrieval rate

Pluggable retrievers and graph/vector projections.

Semantic Worker

Agent

Typed task, context, tools and budget

Structured result, artifacts, confidence and unresolved issues

Least-privilege capabilities per invocation

Hallucination, tool misuse, role drift

Task metrics, schema validity, cost and safety

Model/provider/framework interchangeable through adapter.

Coding Worker

Agent/harness

Repository snapshot, issue, tests and sandbox

Patch, logs, test results and artifact diff

Workspace and bounded network only

Unsafe command, test tampering, dependency drift

Executable tests, static analysis, patch review, adversarial tasks

OpenHands primary; mini-SWE-agent control; Codex/Claude optional.

Tool Gateway

Deterministic

Validated tool request and capability

Normalized result, receipt and side-effect record

Network/filesystem/secret policy enforcement

Injection, SSRF, excessive output, non-idempotent retry

Contract, fuzz, policy and fault-injection tests

MCP and native tools behind same internal interface.

Deterministic Test Service

Deterministic

Artifact, requirement set and test profile

Signed test evidence and coverage map

Read artifact; isolated execution; no prompt changes

Flaky test, false oracle, environment mismatch

Reproducibility, mutation score and oracle validation

Test engines replaceable; result schema is stable.

## 10.3 Evidence and memory components

Component

Type

Inputs

Outputs

Permissions

Failure modes

Evaluation

Replacement

Event Collector

Deterministic

Runtime, tool, model and human events

Validated canonical Event records

Append only; reject malformed or unsigned events

Dropped event, duplicate, bad correlation

Schema, ordering, idempotency and backpressure tests

OTel collector or custom ingest behind event schema.

Event Store

Deterministic

Canonical events

Ordered immutable event streams and snapshots

No in-place mutation; controlled redaction tombstones

Data loss, corruption, privacy overretention

Backup/restore, checksum, replay and retention audits

Postgres/event log initially; storage can migrate.

Artifact/Source Store

Deterministic

Files, datasets, source captures and run outputs

Content-addressed blobs with provenance

Immutable objects; access by capability

Blob substitution, secret retention, missing lineage

Digest, access, retention and restore tests

S3-compatible object store or local equivalent.

Memory Service

Deterministic/hybrid

Evidence, extraction candidates, policies and review decisions

Typed memory items and projection updates

Stage first; promotion through policy

Poisoning, duplicate/conflict, stale fact

Provenance, contradiction, expiry and write-scope tests

Custom service; optional Mem0/Graphiti adapters.

Projection Builders

Deterministic/hybrid

Events and approved memories

Vector index, temporal graph, summaries and views

Can rebuild; never authoritative over source

Index drift, lossy summary, inconsistent graph

Rebuild equivalence, retrieval and temporal tests

Graphiti/vector backend replaceable.

Module Registry

Deterministic

Signed module packages and test evidence

Resolvable versions, compatibility and status

Only authorized publishers; quarantine by default

Dependency confusion, unsigned artifact, incompatible schema

Signature, dependency, conformance and rollback tests

OCI/Git-backed registry with stable manifest.

## 10.4 Improvement and experiment components

Component

Type

Inputs

Outputs

Permissions

Failure modes

Evaluation

Replacement

Outcome Evaluator

Hybrid

Artifact, requirements, test outputs and references

Metric vector, critique and uncertainty

Read-only; evaluator version pinned

Judge bias, prompt sensitivity, weak oracle

Calibration, inter-rater agreement and human audit

Multiple evaluator adapters; no single judge is canonical.

Process Diagnoser

Agent/hybrid

Trajectories, costs, state and outcomes

Causal hypotheses, bottlenecks and supporting episodes

Read-only; cannot alter memory or policy

Post hoc story, correlation mistaken for cause

Counterfactual checks and experiment success rate

Success/failure analyzers are replaceable modules.

Change Proposer

Agent/optimizer

Diagnosis, target schema, constraints and prior experiments

Typed ChangeProposal and candidate diffs

Writes only experimental branches

Scope creep, evaluator gaming, invalid diff

Proposal validity, novelty, acceptance and regression rates

Human, GEPA, DSPy, TextGrad or search adapter.

Experiment Controller

Deterministic

Proposal, candidates, task set and budget

Matched run matrix and ExperimentRecord

No production mutation; blind holdout handles

Unequal budgets, leakage, missing control

Design validation, randomization and completion checks

Scheduler can change; protocol remains stable.

Sandbox Manager

Deterministic

Environment spec, capabilities and task payload

Isolated workspace, receipts and teardown proof

No host secret access; default-deny egress

Escape, residue, cross-run leakage

Escape tests, image attestation, cleanup and quota tests

Docker initially; microVM/Kubernetes providers later.

Evaluation Harness

Deterministic/hybrid

Candidate and control runs, protected datasets and evaluator profile

Paired metrics, uncertainty, regressions and evidence bundle

Holdout contents hidden from candidate/proposer

Data leakage, flaky judge, multiple-testing error

Reproducibility, blinded audits and benchmark rotation

MLflow/Phoenix datasets plus custom statistical layer.

Promotion Gate

Deterministic

Evidence bundle, policy, scope and approvals

Reject, quarantine, retest, canary or promote

Protected root; cannot be modified by candidate

Fail-open, threshold drift, omitted subgroup

Policy mutation tests and retrospective audit

Policy engine implementation replaceable, rules versioned.

Deployment/Rollback Controller

Deterministic

Approved bundle, scope, canary and triggers

Activated bundle or rollback to parent

May deploy only signed approved bundles

Partial rollout, state migration failure, delayed rollback

Canary drills, health checks and rollback time

GitOps/feature-flag backend behind stable state machine.

## 10.5 Minimal agent roster for the first prototype

- Planner/Spec Worker: converts ambiguous requests into candidate requirements for deterministic validation.

- Builder/Coding Worker: produces the implementation in an isolated repository workspace.

- Designer/UX Reviewer: invoked only for interface tasks and produces structured, testable issues.

- User-Simulation Worker: explores task flows and edge cases; never substitutes for human testing.

- Evidence Verifier: checks claims and citations when external knowledge is required.

- Process Diagnoser: identifies repeatable mechanisms and formulates testable hypotheses.

- Change Proposer: produces typed candidate diffs. It has no production, benchmark-vault or approval access.

# 11. Memory architecture

Memory is not one database and it is not synonymous with learning. The foundry needs a canonical evidence layer plus several typed memory views with different write authorities, retention rules and evaluation standards. The architecture follows a write-once evidence principle: source material and execution history are preserved; corrections create new records or validity intervals rather than silent replacement.

Vector search, temporal graphs and summaries are projections. They may improve retrieval, but they are disposable and rebuildable. Procedural memory is the highest-risk memory because it changes future behavior; it therefore uses version-controlled packages and the same promotion lifecycle as other system modifications.

Figure 3. Memory lifecycle from immutable evidence through staged extraction, validation, typed promotion, projection, retrieval evaluation, expiry and reversible consolidation.

## 11.1 Memory layers

Layer

Contents

Writer

Retention

Critical rule

Working memory

Current task state, active hypotheses, unresolved issues and context package

Mission runtime and workers

Mission or subtask

Not a truth store; archive selected state as events.

Source memory

Original files, pages, datasets, repository snapshots, human instructions and captured external evidence

Authenticated ingestion service

Project policy or legal retention

Immutable content digest; annotations are separate records.

Episodic memory

Actions, messages, tool calls, state transitions, outcomes, costs and environment for prior runs

Canonical event collector

Long enough for audit and research; privacy-limited

Complete provenance to mission and bundle.

Semantic memory

Claims, entities, relationships, summaries, confidence and temporal validity

Governed extraction and review pipeline

Until superseded/expired; history retained

Every claim links to supporting and contradicting evidence.

Procedural memory

Prompts, skills, workflows, handoff contracts, routing and test procedures

Module registry after experiment/promotion

Versioned indefinitely with deprecation

Primary bounded-RSI target; signed and rollbackable.

Evaluative memory

Metrics, critiques, judge outputs, benchmark versions, human feedback and calibration

Evaluation harness and authorized reviewers

Longitudinal research retention

Evaluator identity and uncertainty are mandatory.

Negative memory

Known failed strategies, unsafe actions, invalid assumptions and regression signatures

Failure pipeline after validation

Until evidence changes or policy expires

A warning and test source, not an absolute prohibition.

Governance memory

Policies, approvals, exceptions, deployments, incidents, audit proofs and rollback history

Protected governance services and humans

Immutable or legally governed

Outside autonomous write boundary.

## 11.2 Universal memory-item fields

Field

Meaning

memory_id

Stable identifier and content digest

memory_type

source, episode, claim, procedure, evaluation, negative or governance

content_ref

Inline structured content or immutable artifact reference

source_refs

One or more evidence identifiers; empty only for explicitly labeled hypotheses

created_at / observed_at

Record time and event time, kept distinct

valid_from / valid_to

Temporal validity interval for claims and policies

confidence

Calibrated estimate with method; never a substitute for verification status

verification_status

unverified, corroborated, contradicted, human-confirmed, experimentally-supported, deprecated

supporting / contradicting evidence

Directed links with extraction method and span/locator

author / reviewer

Module and version identities, plus human identity where applicable

applicability

Task families, domains, projects, models and preconditions

security_class

Public, internal, confidential, restricted or secret-reference-only

read_scope / write_scope

Projects, roles and capability requirements

lineage

Parent records, transformation version and revision chain

expiration_policy

TTL, review date, event trigger or no automatic expiry

quality_evidence

Retrieval usefulness, downstream effect and harmful-use observations

## 11.3 Write authority and quarantine

Record

Authorized writer

Quarantine / promotion rule

Raw source

Ingestion service after authentication and malware/content checks

No

Run event

Event collector using runtime/tool/model adapters

No; corrections are new events.

Extracted claim candidate

Extraction worker

Yes; staging namespace only.

Verified semantic claim

Validation pipeline plus policy or reviewer

Yes; requires evidence and status.

Episodic summary

Consolidation job

Yes; raw episode remains available.

Procedural candidate

Change proposer or human

Yes; experiment branch only.

Production procedure

Promotion gate after evidence and approval

No in-place edit; new version only.

Negative lesson

Diagnoser proposes; evaluation/review confirms scope

Yes; must include conditions for reconsideration.

Governance record

Authorized human or protected service

No autonomous path.

## 11.4 Retrieval protocol

1. Classify the information need: factual evidence, task episode, procedure, policy, user preference or negative warning.

2. Apply project, identity, security-class and purpose filters before semantic retrieval.

3. Retrieve from multiple projections as appropriate: exact metadata, BM25, embeddings, temporal graph and lineage links.

4. Rerank using source quality, temporal validity, task applicability, contradiction status and retrieval cost.

5. Assemble a ContextPackage with citations, confidence, unresolved conflicts and explicit token allocation.

6. Record which items were shown to which module and how they influenced the result when observable.

7. After the mission, score retrieval usefulness, missed evidence and harmful retrieval to update retrieval policy through an experiment rather than a hidden online rewrite.

### ContextPackage contract

Field

Requirement

package_id / version

Immutable identifier for exactly what context was supplied.

mission_id / node_id

Consumer and workflow location.

information_need

Structured query and assumptions.

evidence_items

Source-linked facts, excerpts or artifact references.

procedures

Pinned skill or instruction versions.

warnings

Contradictions, negative memories, security limitations and stale items.

token_allocation

Budget by section plus omitted-item summary.

retrieval_trace

Queries, filters, ranks, projection versions and latency.

freshness

Cutoff time, validity window and cache state.

## 11.5 Consolidation without premature universal rules

Consolidation is an inference process and must not convert every success into a general rule. An episode can be compressed for navigation while remaining linked to the full trace. A candidate lesson is promoted to semantic or procedural memory only when its scope is explicit and evidence survives counterexamples.

1. Cluster related episodes by task family, failure signature, environment and active bundle.

2. Generate a candidate pattern that states preconditions, action, expected effect, counterevidence and uncertainty.

3. Search for disconfirming episodes and unchanged-baseline cases before creating a rule.

4. For a factual claim, require source corroboration and temporal validity. For a procedural claim, require an experiment.

5. Promote narrowly: one task family or model first. Generalize only after cross-domain evidence.

6. Retain failures and rejected candidates as negative or evaluative memory so future search does not repeatedly rediscover them.

7. Apply controlled forgetting to derived projections, not to protected evidence required for audit or research reproducibility.

## 11.6 Recommended storage implementation

Data class

Recommendation

Rationale

Canonical events and relational metadata

PostgreSQL with append-only tables, row-level security, temporal columns and migration-controlled schemas

Strong transactions, queryability and modest operational complexity.

Artifacts and source captures

S3-compatible object store or content-addressed local store for prototype

Immutable blobs, large-file scale and digest verification.

Procedural memory and manifests

Git plus signed release artifacts or OCI registry

Human-readable diffs, code review, tags, provenance and rollback.

Vector projection

pgvector initially; dedicated vector system only if scale requires

Avoid premature multi-database complexity.

Temporal graph projection

Graphiti with Neo4j/FalkorDB only after temporal graph queries are demonstrated to add value

Useful provenance/validity model, but not required for Stage 1.

Cache and transient coordination

Redis or runtime-native store

Explicitly non-canonical and safe to discard.

Memory safety invariant

No model-generated statement becomes a production fact, procedure, policy or negative rule merely because it appears in a successful trajectory. Permanent behavioral memory requires provenance, scope, review and, for procedures, comparative evidence.

# 12. Bounded RSI algorithm

The bounded RSI algorithm is a controlled search over SystemBundle variants. It is recursive only when an approved child bundle is later used to generate, execute or evaluate new candidate descendants. A single optimization campaign that repeatedly mutates a prompt under a fixed external optimizer is prompt optimization, not necessarily RSI. The foundry records both the system-under-improvement version and the improvement-policy version so that recursion can be tested rather than asserted.

Figure 4. Bounded RSI cycle. Observation and candidate generation are separated from protected evaluation, policy, deployment and rollback.

## 12.1 Formal objects

Object

Definition

SystemBundle S_t

The complete frozen system configuration used at generation t.

Mission distribution D_t

The task population, profiles and environmental conditions for the generation.

Evidence E_t

Canonical events, artifacts, evaluations, human feedback and costs produced by S_t.

Improvement policy I_t

Diagnosis, proposal and search modules that generate candidate diffs.

Evaluation root R_t

Protected datasets, deterministic tests, judges, metrics, thresholds and policy.

Candidate set C_t

One or more child bundles plus unchanged control and relevant human-designed alternatives.

Promotion decision P_t

Scope-limited reject, quarantine, retest, canary or promote action.

## 12.2 Algorithm

function BOUNDED_RSI(parent_bundle S_t, mission_cohort H_t, policy_root G):    assert verify_signature(S_t)    evidence = freeze_and_query_evidence(H_t, bundle=S_t)    diagnoses = run_diagnosers(evidence, read_only=True)    proposals = generate_change_proposals(        diagnoses=diagnoses,        mutable_schema=G.allowed_mutations,        search_budget=G.modification_budget    )    for proposal in proposals:        validate_typed_diff(proposal)        require_one_primary_hypothesis(proposal)        require_risk_scope_rollback_and_evaluation_plan(proposal)        candidates = fork_candidates(S_t, proposal)        candidates.add(control=S_t)        candidates.add(human_baseline_when_available=True)        plan = design_matched_experiment(            candidates=candidates,            replay_tasks=sample_replays(evidence),            development_tasks=G.development_set,            protected_holdouts=blind_handles(G.holdout_vault),            adversarial_tasks=G.security_suite,            repeated_seeds=G.seed_policy,            equalized_budgets=True        )        runs = execute_in_isolated_sandboxes(plan)        evidence_bundle = evaluate_with_pinned_root(runs, root=G.evaluation_root)        decision = apply_promotion_policy(evidence_bundle, proposal.scope)        if decision.requires_human:            decision = obtain_explicit_approval(decision, evidence_bundle, proposal.diff)        if decision.action == "canary":            deployment = deploy_canary(decision.candidate, decision.scope)            monitor_predicted_effects_and_rollback_triggers(deployment)            decision = finalize_or_rollback(deployment)        append_governance_record(proposal, plan, evidence_bundle, decision)        if decision.action == "promote":            S_t_plus_1 = sign_and_publish_child_bundle(decision.candidate, parent=S_t)            return S_t_plus_1    return S_t  # no change is a valid result

## 12.3 Change proposal requirements

- Target component and exact mutable field path.

- Parent bundle and current behavior, with representative evidence identifiers.

- One primary causal hypothesis and optional secondary hypotheses clearly marked.

- Candidate diff or generation procedure, including dependency and state-migration effects.

- Expected quality, safety, cost, latency and maintainability effects.

- Known risks, affected task families, blast radius and autonomy level.

- Matched experiment design, required tasks, evaluators and statistical decision rule.

- Capability-retention set and unacceptable regression thresholds.

- Canary scope, monitoring window and executable rollback trigger.

- Proposer identity, model/version, prompt/version and all source evidence.

## 12.4 Candidate generation strategies

Strategy

Mechanism

Foundry use

Human-designed diff

Expert proposes a specific change.

Strong baseline and interpretability; limited scale.

Template mutation

Bounded edits to known manifest fields.

Safest first automation; low expressiveness.

DSPy/GEPA optimizer

Uses task feedback and traces to evolve prompts or textual configurations.

High relevance for prompts/skills; evaluator dependence must be controlled. [I01]-[I03]

TextGrad

Uses textual loss feedback to update text artifacts.

Useful for local improvement experiments; metaphor does not imply true gradients. [I04]

Workflow search / AFlow

Searches graph nodes, operators or topology.

Potential Level 3 mechanism; high experiment cost and overfit risk. [I05][I11]

Population/evolution

Maintains diverse variants and recombines successful components.

Supports Pareto diversity; needs strict lineage and search-cost accounting.

Repair from failure signatures

Maps known failure classes to constrained candidate transformations.

Efficient and interpretable; can become rule-heavy.

## 12.5 Stopping conditions

- Search budget exhausted: total tokens, cost, runtime, candidate count or human review limit.

- No candidate exceeds the minimum practical effect while satisfying non-regression gates.

- Repeated proposals converge on previously rejected diffs without new evidence.

- Evaluator disagreement or instability exceeds the allowed uncertainty.

- A security, privacy or sandbox incident occurs.

- Complexity growth exceeds the allowed maintenance budget.

- The best candidate improves only exposed development tasks and not protected holdouts.

- Human authority pauses the campaign or changes the operational objective.

## 12.6 Test for recursive status

Criterion

Required question

Persistence

Did the accepted change alter a versioned component used by future missions?

Self-reference

Was the changed component part of the same system that produced or enabled later changes?

Independent validation

Was the change accepted through protected comparative evidence rather than self-assertion?

Intergenerational effect

Did S_t+1 affect the generation, quality or efficiency of candidate S_t+2?

Retention

Were prior capabilities and governance constraints preserved?

Traceability

Can the lineage and causal experiment be replayed or audited?

Claim rule

Describe a run as bounded RSI only after at least two accepted generations demonstrate persistent, independently validated changes and the newer system participates in producing or improving the next generation. Until then, describe the mechanism as governed system optimization.

## 12.7 Meta-RSI without circular self-ratification

Level 4 changes create a circularity: an evaluator could make itself easier to satisfy, hide a failure class or change the objective after seeing results. Meta-RSI therefore uses a constitutional split. The candidate improvement policy may propose a new evaluator or threshold, but it cannot access protected labels, replace the old root or approve the new root.

1. Freeze the old evaluation root R_t and create proposed root R_candidate as an experimental artifact.

2. Run both roots on historical incidents, fresh blinded samples, adversarial examples and human-labeled calibration sets.

3. Measure not only agreement and predictive validity but also which candidate bundles each root would promote.

4. Require the new root to preserve protected invariants and to explain material decision differences.

5. Use an external human committee or separately governed root R_external for authorization.

6. Canary the evaluator on shadow decisions before it gains any production authority.

7. Retain the previous root for rollback and periodic baseline comparison.

# 13. Evaluation and promotion gates

Promotion is a safety-critical statistical decision, not a leaderboard comparison. The foundry evaluates a vector of outcomes and applies hard constraints before preference optimization. A candidate that improves average quality but violates security, cost, latency, reproducibility or retained capability limits is rejected or restricted to a narrower profile.

Figure 5. Module-promotion lifecycle from proposal and validation through matched experiments, protected gates, canary deployment, monitoring, promotion or rollback.

## 13.1 Gate sequence

Gate

Evidence

Decision rule

G0 - Integrity and scope

Signed parent, valid typed diff, allowed mutation, dependency closure, declared state migration and rollback.

Any failure rejects before execution.

G1 - Static and deterministic checks

Schema, unit, type, lint, security, policy, data-leakage and reproducible build checks.

All mandatory checks pass; no severity-1 finding.

G2 - Development replay

Matched candidate/control runs on prior tasks and synthetic failures.

Practical gain or a justified trade-off; no unexplained catastrophic case.

G3 - Protected holdout

Blinded fresh tasks unavailable to proposer and candidate.

Predeclared improvement/non-inferiority rule passes with uncertainty bound.

G4 - Capability retention

Previously solved tasks, subgroup minima and critical behavior tests.

No hard capability loss; bounded allowed regression on soft metrics.

G5 - Adversarial and safety

Prompt injection, memory poisoning, tool abuse, privilege, secret, sandbox and evaluator-gaming tests.

Zero critical violations; residual risk below task-specific threshold.

G6 - Resource and maintainability

Total search cost, run cost, p95 latency, iteration count, complexity and operational burden.

Fits selected profile and improvement is worth full lifecycle cost.

G7 - Reproducibility

Repeated seeds/runs, environment recreation and independent evaluator replication.

Effect direction stable; unexplained variance within tolerance.

G8 - Human authorization

Readable diff, evidence, uncertainties, scope and rollback plan.

Required approver signs the exact candidate and deployment scope.

G9 - Canary and monitoring

Shadow/canary traffic, predicted metrics and rollback triggers.

Effect persists in deployment; no alert or distribution-shift breach.

## 13.2 Metric vector

Dimension

Representative measures

Use in gate

Task success

Executable completion, requirement coverage, human usefulness or domain score

Primary objective, stratified by task family.

Factuality

Citation entailment, source accuracy, contradiction and unsupported-claim rate

Hard floor for evidence-sensitive tasks.

Robustness

Perturbations, failure recovery, long context, tool faults and conflicting information

Protects against narrow benchmark fit.

Generalization

Fresh task families, time slices, repositories, domains and models

Required for broad scope promotion.

Safety/security

Policy violations, exploit success, unsafe side effects and secret exposure

Hard constraint, not traded for quality.

Capability retention

Performance on protected prior capabilities and subgroups

Non-inferiority or zero-loss for critical skills.

Cost

Mission inference plus candidate search, evaluation, storage, human review and maintenance

Report total improvement cost, not only steady-state run cost.

Latency

End-to-end and p50/p95/p99 node and mission latency

Profile-specific ceiling.

Stability

Variance, timeout, retry, rollback and nondeterministic failure rate

Effect must survive repeated runs.

Interpretability

Diff size, evidence chain, attributable mechanism and operator comprehension

Complexity penalty and approval quality.

Maintainability

Dependency count, rule count, workflow nodes, test burden and upgrade coupling

Reject recursive complexity growth without benefit.

Reproducibility

Exact bundle/environment recovery and independent rerun agreement

Required for scientific claims.

## 13.3 Multi-objective decision policy

A single weighted score is convenient but dangerous because it permits compensation: a severe security regression can be hidden by a quality gain. The recommended policy first applies hard constraints and subgroup floors. Among candidates that satisfy them, it uses Pareto dominance or profile-specific utility with transparent weights. The unchanged parent remains a valid winner.

eligible(c) =    integrity_pass(c)    and safety_critical_violations(c) == 0    and capability_retention(c) >= retention_floor    and reproducibility(c) >= reproducibility_floor    and cost(c) <= profile.cost_ceiling    and latency_p95(c) <= profile.latency_ceilingwinner = pareto_select(    candidates = [c for c in candidates if eligible(c)],    objectives = [quality_gain, robustness_gain, cost_reduction,                  latency_reduction, interpretability, maintainability],    prefer_parent_when_effect_is_uncertain = True)

## 13.4 Statistical design

- Use paired tasks and, where possible, identical environment snapshots so candidate-control differences have lower variance.

- Pre-register the primary endpoint, minimum practical effect, subgroup floors, seed policy and stopping rule before opening protected results.

- Use repeated seeds or repeated model samples for stochastic modules; report distributions rather than the best run.

- Use paired bootstrap intervals or hierarchical models for heterogeneous task families; do not rely only on a global mean.

- Control multiple comparisons across candidates and metrics, or use sequential procedures designed for adaptive search.

- Distinguish superiority from non-inferiority. Retained capabilities often require a one-sided non-inferiority decision.

- Do not reuse the final holdout for repeated optimizer feedback. Rotate and refresh protected tasks over time.

- Include task and time fixed effects when comparing generations across model-provider or environment drift.

## 13.5 Evaluator triangulation

Evaluator type

Examples

Role and limitation

Deterministic oracle

Tests, schemas, exact match, static analysis, simulation invariants

High objectivity where available; incomplete for open-ended quality.

Reference-based metric

Gold labels, expected facts, patch tests or requirement map

Strong but vulnerable to stale or narrow references.

Independent LLM judge

Rubric-scored artifact or trajectory with pinned model/prompt

Scales semantic review; biased and variable.

Adversarial judge

Searches for counterexamples, unsupported claims or exploit paths

Improves failure discovery; may over-penalize.

Cross-model panel

Judges from independent providers/families with aggregation and disagreement

Reduces some common-mode error; increases cost and does not guarantee truth.

Human review

Blinded expert or target-user assessment

Highest-value calibration for ambiguous utility; expensive and limited.

Deployment signal

Canary task success, operator correction, user feedback, rollback and incident rate

External validity; affected by distribution and confounding.

## 13.6 Promotion statuses

Status

Meaning

Draft

Created but not yet validated.

Quarantined

Invalid, unsafe, incomplete or awaiting evidence; cannot execute except in analysis sandbox.

Experimental

May run only in isolated experiments with synthetic or approved data.

Shadow

Evaluates real inputs without affecting production outputs or side effects.

Canary

Serves a small, explicit scope under automatic rollback.

Scoped production

Approved for defined task family, project, profile or model.

General production

Approved broadly after longitudinal evidence; still monitored and reversible.

Deprecated

May support rollback or replay but cannot be newly selected.

Revoked

Blocked because of security, integrity or critical regression.

# 14. Security and governance

The foundry is a system that executes untrusted text, code, tools and self-generated configuration. Its primary security objective is not to make model behavior perfectly safe; it is to ensure that model behavior cannot escape bounded capabilities, corrupt the trusted evidence root, expose protected evaluation data or silently acquire authority.

Security controls must be enforced outside the candidate system. Prompt instructions and agent constitutions are defense-in-depth only. The trusted computing base should be small, deterministic, reviewable and conventional: identity, policy, capability issuance, secret brokerage, sandboxing, artifact verification, audit, holdout isolation, promotion and rollback.

Figure 6. Trust boundaries. Human authority and protected services control capabilities; untrusted content, workers and candidate bundles execute in isolated zones.

## 14.1 Components outside the self-modification boundary

- Human identity, role assignment and final authority for high-impact changes.

- Policy decision point, approval-tier rules and fail-closed behavior.

- Canonical event and governance ledgers, integrity keys and audit requirements.

- Secret broker, credential scopes, network boundary and capability-token semantics.

- Sandbox escape protections, host configuration and base-image admission policy.

- Protected holdout vault, labels, sampling keys and evaluator-root authorization.

- Signing keys, trusted publishers, supply-chain verification and rollback mechanism.

- Emergency stop, resource hard ceilings and incident-response procedures.

## 14.2 Threat-control matrix

Threat

Attack / failure

Primary controls

Residual risk

Prompt injection in retrieved content

Untrusted text instructs a worker to ignore mission or exfiltrate data.

Label content as data, isolate instructions, allowlist tools, context provenance, injection tests and output validation.

Residual semantic manipulation remains; minimize privileges.

Tool abuse

Valid tool invoked with harmful arguments or excessive scope.

Capability-bound tool gateway, argument policy, dry-run, HITL for irreversible actions, idempotency keys and receipts.

Domain-specific policies require maintenance.

Memory poisoning

Malicious or hallucinated content becomes trusted context or procedure.

Staging, provenance, verification status, scoped write authority, contradiction checks and procedural promotion gates.

Subtle poisoning may survive automated checks.

Malicious document or repository

Content exploits parsers, build steps, agents or dependency resolution.

Content scanning, no implicit execution, isolated parse/build, dependency allowlist, network deny and artifact quarantine.

Zero-days and logic bombs remain possible.

Cross-agent privilege escalation

A low-privilege worker delegates to a high-privilege module or passes crafted capability.

Non-transferable capability tokens, receiver-side policy check, no authority inheritance and explicit delegation graph.

Complex workflows can hide indirect data flow.

Secret leakage

Keys enter prompts, logs, artifacts or external requests.

Secret broker/proxy, redaction, no raw secret in context, egress allowlist, canary secrets and leakage scanning.

Model may infer sensitive non-secret data.

Unauthorized code execution

Generated code reaches host or production resources.

Ephemeral sandbox, read-only base image, user namespaces/microVM, seccomp, resource quotas and no host socket.

Sandbox escapes require rapid patching.

Supply-chain compromise

Skill, tool, image or dependency is replaced or malicious.

Signed manifests, pinned digests, SLSA provenance, SBOM, trusted publishers, reproducible build and revocation. [S05]

Third-party transitive risk persists.

Evaluator manipulation

Candidate detects benchmark, tampers with tests or crafts judge-targeted output.

Blind holdout handles, read-only tests, separate evaluator process, canary tasks, adversarial judges and hidden perturbations.

Adaptive systems may infer distributions over time.

Self-approved modification

Candidate changes approval logic, threshold or evidence presented to approver.

Immutable promotion gate, signed evidence bundle, exact-diff approval and separation of duties.

Human social-engineering risk remains.

Hidden goal drift

Optimized system pursues proxy metrics instead of user objective.

Multi-objective metrics, subgroup floors, qualitative review, deployment feedback and periodic baseline reset.

Objectives are never perfectly specified.

Runaway resource consumption

Loops, candidate search or tool calls consume excessive resources.

Hard token/time/cost/concurrency limits, kill switch, diminishing-return stopping and per-campaign budget.

Distributed external costs require connector-level accounting.

Unbounded recursion

System spawns uncontrolled descendants or recursively edits trusted code.

Maximum generation depth per campaign, mutation allowlist, signed parent lineage and no code-level self-modification in MVP.

Manual expansion of scope still needs governance.

Unsafe propagation of rules

A local lesson becomes global policy.

Applicability fields, narrow default scope, staged promotion and cross-domain holdouts.

Sparse evidence may still misestimate scope.

Privacy and data retention

Trace or memory stores sensitive content beyond purpose.

Data classification, field-level encryption, minimization, redaction, retention schedules, deletion workflow and access audit.

Deletion can conflict with reproducibility; policy must define exceptions.

## 14.3 MCP and external-tool security

MCP improves interoperability but introduces explicit authorization and deployment responsibilities. The protocol does not make a server trustworthy. The foundry should terminate MCP at the Tool Gateway and translate calls into its internal capability and receipt model. Direct agent-to-server credentials, token passthrough and unrestricted local MCP installation should be prohibited. MCP's security guidance specifically highlights confused-deputy attacks, token passthrough, SSRF, session hijacking and compromise of local servers. [S01]

- Maintain a registry of approved MCP servers pinned by digest, publisher and transport configuration.

- Separate tool discovery from authorization; presence in a catalog never implies permission to invoke.

- Validate schemas and size limits, normalize output and mark all server text as untrusted data.

- Use per-mission OAuth audience/scope or gateway-issued capabilities; never relay client tokens to arbitrary servers.

- Apply outbound DNS, domain, method and path restrictions where possible; block metadata and internal-network targets.

- Bind sessions to authenticated clients and reject session identifiers as authorization evidence.

- Sandbox local servers and deny filesystem, process and network access not declared in the signed manifest.

- Record server version, arguments, capability, request, response digest, latency and side-effect receipt for every call.

## 14.4 Sandbox requirements

Property

Requirement

Isolation

Ephemeral container or microVM; no host Docker socket; separate user, process, mount, IPC and network namespaces.

Filesystem

Read-only base; writable workspace and scratch volumes; explicit mounted inputs; no home or secret directories.

Network

Default deny; egress proxy with domain/method/path policy and DNS logging; no cloud metadata.

Secrets

Brokered per-action or ephemeral scoped credentials; no environment-wide long-lived key.

Resources

CPU, memory, process, disk, token, time and network quotas; killable from outside sandbox.

Image trust

Pinned digest, SBOM, vulnerability policy, signed provenance and rebuild schedule.

Execution receipts

Command, args, executable digest, start/end, exit code, stdout/stderr digest and changed-file manifest.

Cleanup

Verified teardown, artifact export allowlist and no reuse across security domains.

Nested agents

Subagents inherit narrower or equal capabilities; no privilege amplification.

## 14.5 Human approval policy

Tier

Trigger

Authorization

A0 - Automatic

Reversible Level 1 change, no sensitive data or external side effects, all gates pass, narrow scope.

Machine policy records decision and canary.

A1 - Single reviewer

Level 2 prompt/skill/routing change or first low-risk deployment.

One authorized reviewer signs candidate and scope.

A2 - Dual control

Level 3 topology, new tool permission, confidential data scope or broad production rollout.

Two independent reviewers or owner plus security reviewer.

A3 - Governance committee

Level 4 evaluator/policy change, security boundary, high-impact domain or incident exception.

Documented review, external evidence and rollback rehearsal.

A4 - Conventional SDLC only

Level 5 trusted code, training pipeline, policy engine, audit or sandbox root change.

Code review, CI/CD, security testing and organizational change control; no autonomous promotion.

## 14.6 Anti-degeneration controls

- Complexity budgets for prompt length, rule count, workflow nodes, dependencies and evaluator count.

- Periodic comparison with a simple baseline and the last stable long-term bundle.

- Diversity preservation across candidate generators, judge models and worker families.

- Protected negative tasks and incident replays that cannot be removed by the candidate.

- Rule-conflict detection and forced consolidation review before adding overlapping procedures.

- Performance-by-subgroup dashboards to prevent aggregate gains from hiding local collapse.

- Rotating holdouts and time-split evaluation to reduce benchmark memorization.

- Controlled deprecation and forgetting of derived rules whose benefit no longer reproduces.

- Change-rate limits and blast-radius limits so generations cannot compound faster than monitoring can detect harm.

Security invariant

The candidate under test may influence what it proposes and how it performs a mission. It may not influence the identity of the protected data it is judged on, the policy that authorizes its capabilities, the integrity of its evidence, or the keys that promote it.

# 15. Observability and visualization

Observability is part of the scientific apparatus. The dashboard must make it possible to reconstruct what system version ran, which evidence it saw, which capabilities it held, which actions occurred, how the artifact changed, how it was evaluated and why a modification was promoted or rejected. Decorative animation is secondary.

The foundry should emit OpenTelemetry-compatible traces for interoperability while retaining a richer canonical event model for version lineage, memory writes, experiment assignments and governance decisions. Phoenix, MLflow or LangSmith can consume traces and support datasets, annotations and experiments, but none should be the sole evidence root. [O01]-[O04]

## 15.1 Canonical event envelope

Field

Purpose

event_id

Globally unique, idempotency-safe identifier.

event_type / schema_version

Stable event name and versioned payload schema.

occurred_at / recorded_at

Event time and ledger ingestion time.

mission_id / run_id / node_id

Hierarchical execution correlation.

experiment_id / arm_id

Experimental assignment; absent for ordinary missions.

system_bundle_id

Exact behavior bundle active for the event.

module_id / module_version

Originating or affected module.

actor / subject / project

Authenticated principal, resource and tenancy scope.

parent_event_ids

Causal or dependency links.

input_refs / output_refs

Content-addressed payload or artifact references.

capability_ref

Authorization grant used for an action, without exposing secret value.

model_ref

Provider, model identifier, endpoint policy and sampling settings.

tool_ref

Tool/server version, request digest and side-effect class.

usage

Tokens, cost, latency, retries, CPU/memory and network where available.

security_class / retention

Data handling and deletion policy.

integrity

Producer signature, event digest and ledger sequence.

## 15.2 Required event families

Family

Representative event types

Mission

requested, accepted, rejected, compiled, started, suspended, resumed, completed, failed, cancelled

Workflow

node_ready, node_started, state_updated, handoff, retry, timeout, checkpoint, duplicate_suppressed

Model

request, response, validation_failed, fallback, refusal, usage

Tool

discovered, authorized, denied, called, result, side_effect_receipt, rollback

Memory

query, item_retrieved, item_shown, candidate_written, reviewed, promoted, expired, contradicted

Artifact

created, modified, tested, signed, exported, deleted

Evaluation

scheduled, metric_computed, judge_result, disagreement, human_annotation, calibration

Experiment

designed, randomized, arm_started, arm_completed, leakage_detected, stopped, analyzed

Governance

proposal_submitted, approval_requested, decision, policy_denial, canary, promotion, rollback, incident

Resource

budget_reserved, budget_warning, budget_exhausted, quota_violation

## 15.3 Dashboard views

View

Minimum data

Question answered

Command Center

Current missions, objectives, bundle, budget, risk class, approvals and incidents

What is running and what needs human action?

Workflow Trace

Graph, node state, messages, tools, retries, blocked work and timeline

Where is the mission and why?

Evidence Inspector

Context package, source lineage, memory reads, contradictions and confidence

What information influenced the system?

Artifact Workshop

Repository/file diffs, build outputs, tests, screenshots and issue history

What changed in the product and what remains broken?

Evaluation Console

Metric vector, judge rationales, disagreement, subgroup and failure examples

How good is the outcome and how certain is the assessment?

Experiment Lab

Arms, task assignments, budgets, paired results, uncertainty and stopping rule

Does the candidate beat the control fairly?

Governance Chamber

Typed diff, risk, policy decision, approval evidence, deployment scope and rollback

Why may this change affect production?

Evolution Tree

Bundle lineage, mutations, promoted/rejected branches, regressions and rollbacks

How has the system changed across generations?

Resource Economy

Inference, tools, compute, human review, storage and total improvement cost

Is the improvement worth its complete cost?

Incident and Audit

Policy denials, security alerts, integrity verification and reconstruction tools

Can operators contain and explain a failure?

## 15.4 Useful transparency versus decorative visualization

Class

Examples

Useful

Exact version and dependency identity; trace-to-artifact links; evidence provenance; permissions; evaluation uncertainty; diffs; lineage; rollback status.

Potentially useful

Agent map, animated workflow, memory graph and resource metaphor when each visual maps to canonical data and supports filtering.

Decorative or misleading

Personality avatars, unexplained confidence meters, simulated emotions, unreadable network graphs and game rewards without measured capability.

Actively harmful

Interfaces that hide uncertainty, omit failed branches, imply causality from correlation or encourage approval without showing the exact diff and protected-gate results.

## 15.5 Reproducibility log versus privacy minimization

Category

Policy

Must retain for reproducibility

Bundle and environment digests; explicit inputs/outputs; visible model messages; tool requests/results; state transitions; artifact diffs; dataset/evaluator versions; seeds where supported; costs; approvals; incidents.

Retain only when necessary

Full retrieved document bodies, screenshots, browser content, user conversations, source repositories and human annotations; prefer content references and scoped encryption.

Do not seek or store by default

Hidden model chain-of-thought, unrelated personal data, raw long-lived secrets, unrestricted environment variables and host-level telemetry.

Redact or tokenize

Access tokens, API keys, passwords, private keys, session cookies, regulated identifiers and unnecessary file paths.

Deletion tension

When privacy deletion affects research replay, retain non-reversible digests and governance evidence while removing content according to policy; mark the run as no longer fully replayable.

## 15.6 Observability stack

Layer

Recommendation

Reason

Instrumentation

OpenTelemetry SDKs plus runtime/tool/model adapters

Portable trace and metric emission. [O01]

Collector

OpenTelemetry Collector with redaction, sampling and routing processors

Central enforcement before export.

Canonical ledger

PostgreSQL event tables plus object store

Authoritative versioned evidence and lineage.

Trace/eval UI

Phoenix or MLflow; LangSmith when LangGraph ecosystem convenience is valuable

Fast trace inspection, datasets, annotations and experiment comparison. [O02]-[O04]

Lineage UI

Foundry-specific service over bundle, proposal, experiment and deployment records

The missing RSI-specific governance and evolution view.

# 16. Build-versus-borrow decisions

The foundry should be an orchestration and governance layer over mature primitives, not a new implementation of every agent, database, sandbox and evaluator. The build boundary is where the research contribution lies: versioned system bundles, canonical cross-runtime evidence, governed improvement experiments, promotion gates, evaluator governance and lineage.

Capability

Decision

Technology

Rationale

Mission workflow runtime

Adopt/wrap

LangGraph first; Microsoft Agent Framework as principal alternative

Do not build a graph scheduler. Wrap state, lifecycle and events behind a foundry adapter.

Typed semantic agents

Adopt/wrap

PydanticAI; optionally OpenAI Agents SDK

Use structured schemas and provider adapters; retain foundry permissions and events.

Coding worker

Adopt/wrap

OpenHands Software Agent SDK

Strong workspace/tool base; isolate behind worker contract.

Minimal coding baseline

Adopt

mini-SWE-agent

Transparent control with minimal scaffold.

Other coding systems

Integrate later

Codex and Claude Agent SDK

Useful comparison/production adapters; avoid core dependency in MVP.

Tool protocol

Adopt at boundary

MCP

Use for interoperability but terminate authorization at foundry gateway.

Cross-service agent protocol

Avoid initially / adopt later

A2A

Use only when external opaque agent services are required.

Skill package format

Adopt and extend

Agent Skills-compatible folders plus signed foundry manifest

Reuse portability and progressive disclosure; add governance metadata.

Model gateway

Adopt/wrap

Provider SDKs or a narrow gateway such as LiteLLM where needed

Centralize model identity, cost, fallback and policy; do not hide provider semantics relevant to experiments.

Canonical event store

Build thin layer on standard DB

PostgreSQL plus object storage

Custom event schema and lineage are core; storage engine is not.

Vector memory

Adopt minimally

pgvector first

One infrastructure stack for prototype; swap only after measurement.

Temporal graph memory

Integrate later

Graphiti with supported graph backend

Add only after temporal graph retrieval beats simpler projections. [M04]

Personalization memory

Optional adapter

Mem0

Useful product feature, not governance/evidence root. [M03]

Tracing standard

Adopt

OpenTelemetry GenAI conventions

Portability and ecosystem integration. [O01]

Trace/eval workbench

Adopt/wrap

Phoenix or MLflow; optionally LangSmith

Avoid rebuilding trace UI and dataset operations.

Prompt/text optimizer

Adopt as plugin

GEPA/DSPy; TextGrad for comparison

Candidate generation only; foundry owns evidence and promotion.

Workflow optimizer

Research integration

AFlow-style search or custom typed mutations

Not Stage 1; high overfit and resource risk.

Policy engine

Adopt

OPA/Rego or Cedar

Conventional, testable authorization outside model control.

Secrets

Adopt

Vault/KMS/cloud secret manager

No custom cryptographic secret store.

Sandbox

Adopt/wrap

Docker rootless for prototype; gVisor/Kata/Firecracker or managed sandbox for higher assurance

Build policy adapter and receipts, not a new isolation kernel.

Supply-chain integrity

Adopt

Sigstore/Cosign, SBOM tooling and SLSA provenance

Standard artifact integrity and revocation. [S05]

RSI experiment controller

Build

Foundry-specific

Core research contribution: paired branches, blinded holdouts, lineage and budgets.

Promotion/rollback protocol

Build on policy/GitOps primitives

Foundry-specific state machine plus deployment backend

Core safety and scientific governance contribution.

Evolution/lineage dashboard

Build

Foundry-specific UI over canonical records

Existing trace tools do not model recursive system generations.

## 16.1 Primary stack recommendation

Layer

Recommended first implementation

Language/runtime

Python 3.12+ for control plane and experiments; TypeScript/React for UI as needed

API and schemas

FastAPI, Pydantic v2, JSON Schema/OpenAPI and protobuf only where streaming/distribution requires

Mission orchestration

LangGraph behind RuntimeAdapter

Semantic workers

PydanticAI and direct provider adapters; OpenAI Agents SDK adapter optional

Coding execution

OpenHands Software Agent SDK; mini-SWE-agent baseline

Data

PostgreSQL + pgvector, S3-compatible object store, Redis only for transient coordination

Observability

OpenTelemetry Collector + Phoenix or MLflow + Prometheus-compatible metrics

Experiments

Foundry controller, datasets in canonical DB/object store, GEPA/DSPy plugin

Policy/security

OPA or Cedar, Vault/KMS, rootless Docker initially, Cosign/SBOM/SLSA

Deployment

GitOps or signed release registry, feature flags/canary routing and automated rollback

## 16.2 Technologies deliberately not combined in the MVP

- Do not run LangGraph and Microsoft Agent Framework as co-equal schedulers in one mission. Implement the second only as an alternate runtime adapter after the canonical event suite is stable.

- Do not combine Mem0, Graphiti and a separate vector database as independent writeable memory systems. Use one evidence root and optional read projections.

- Do not place CrewAI or MetaGPT role graphs inside the primary runtime merely to increase agent count. Use them as external baselines when scientifically useful.

- Do not make MCP the internal message bus. It is a tool/context interoperability boundary, not the foundry state model.

- Do not use A2A for in-process module calls. Its value appears across opaque service or organizational boundaries.

- Do not deploy automatic workflow search before the task suite, replay fidelity and promotion gates are proven.

## 16.3 Defensible product/research framing

Label

Verdict

Reason

New agent framework

No

The project should reuse a runtime and avoid competing on basic agent-loop APIs.

Framework-of-frameworks

Mostly no

Adapters are required, but exposing every native abstraction would destroy comparability.

Agent operating system

Premature

Implies broad resource/process authority and production maturity not yet justified.

Agent foundry

Yes

Conveys replaceable modules, versioned assembly, testing and promotion.

Experimental control plane

Yes, most precise

Captures frozen bundles, evidence, experiments, governance and deployment.

Production platform

Not initially

Security, reliability and longitudinal validation must precede this claim.

# 17. Repository and schema design

The repository should enforce architectural separation. Core schemas and policy interfaces are small, stable packages. Runtime, model, memory and evaluator integrations live behind adapters. Experiments, bundles and deployment records are data, not hidden code paths. The module contract is the LEGO connector; compatibility is established by schema, capability and conformance evidence rather than by class inheritance alone.

Figure 7. Universal module contract and replacement boundary. A module is admitted by manifest, schemas, policy, conformance tests and signed evidence.

## 17.1 Proposed repository layout

agent-foundry/├── apps/│   ├── control-api/              # mission, approval, experiment and lineage APIs│   ├── operator-ui/              # trace, evidence, experiment and governance views│   └── worker-gateway/           # runtime/model/tool streaming ingress├── packages/│   ├── contracts/                # Pydantic/JSON schemas and compatibility rules│   ├── event-ledger/             # canonical event ingestion and projections│   ├── policy/                   # OPA/Cedar client, approval tiers, capability claims│   ├── registry/                 # signed module and SystemBundle resolution│   ├── mission-compiler/         # request -> validated MissionSpec│   ├── context-builder/          # evidence retrieval and ContextPackage assembly│   ├── experiment-controller/    # matched designs, randomization, budgets, stopping│   ├── evaluation/               # metrics, judge adapters, statistics and gates│   ├── deployment/               # canary, activation, monitoring and rollback│   └── sdk/                      # module authoring, local conformance and fixtures├── adapters/│   ├── runtimes/langgraph/│   ├── runtimes/microsoft-agent-framework/│   ├── runtimes/google-adk/│   ├── agents/pydantic-ai/│   ├── agents/openai-agents/│   ├── coding/openhands/│   ├── coding/mini-swe-agent/│   ├── coding/codex/│   ├── coding/claude-agent-sdk/│   ├── tools/mcp/│   ├── memory/graphiti/│   ├── memory/mem0/│   ├── optimizers/gepa-dspy/│   └── observability/{phoenix,mlflow,langsmith}/├── modules/│   ├── agents/                   # versioned module packages│   ├── skills/│   ├── tools/│   ├── evaluators/│   └── workflows/├── bundles/                      # signed development bundle declarations├── benchmarks/│   ├── public/│   ├── protected-manifests/      # handles only; labels live in separate vault│   ├── adversarial/│   ├── retention/│   └── incidents/├── policies/│   ├── capabilities/│   ├── promotion/│   ├── retention/│   └── sandbox/├── schemas/                      # generated JSON Schema and migrations├── tests/│   ├── conformance/│   ├── integration/│   ├── fault-injection/│   ├── security/│   └── replay/├── infra/│   ├── containers/│   ├── kubernetes/│   ├── otel/│   └── database/├── research/│   ├── protocols/│   ├── preregistrations/│   ├── analyses/│   └── reports/└── pyproject.toml

## 17.2 Universal module manifest

Manifest group

Required fields

Identity

module_id, module_type, version, digest, publisher, license, created_at, status

Purpose

purpose, responsibilities, non_responsibilities, task_tags, risk_class

Interfaces

input_schema, output_schema, event_schema, streaming, error_schema

Capabilities

allowed_tools, requested_permissions, network/file scopes, secret classes

Models

model_requirements, supported_providers, parameter constraints, fallback policy

Memory/context

read_scope, write_scope, context_budget, retention obligations

Resources

token, cost, latency, wall-time, concurrency, storage and human-attention budgets

Reliability

preconditions, postconditions, idempotency, retry, timeout, cancellation and recovery

Safety

safety_constraints, forbidden effects, data classes, sandbox profile

Quality

metrics, acceptance floors, known failure modes, calibration and test suite

Dependencies

module and environment dependencies, compatibility ranges and migration hooks

Lifecycle

promotion status, parent version, rollback target, deprecation and monitoring

Provenance

source repository, build attestation, SBOM, signatures and approval evidence

## 17.3 Compatibility and replacement protocol

1. Schema compatibility: validate structural inputs, outputs, errors and events against declared versions.

2. Semantic compatibility: run contract examples and task-specific behavioral conformance, not only JSON validation.

3. Capability negotiation: compare requested tools, permissions, modalities, streaming and environment needs with host policy.

4. Dependency resolution: pin transitive modules and images; reject ambiguous or unsigned versions.

5. State transfer: require explicit migration schema and reversible transformation for persistent module state.

6. Shadow execution: run old and new module on identical inputs without production side effects where feasible.

7. Backward compatibility: support declared version ranges or introduce an adapter; never silently coerce incompatible semantics.

8. Rollback: retain parent package, state snapshot and migration reversal or restore procedure.

## 17.4 Core schemas

### MissionSpec

{  "mission_id": "mis_...",  "project_id": "proj_...",  "request_ref": "artifact://...",  "task_type": "software.web_app",  "objectives": [{"id": "OBJ-1", "text": "...", "priority": "must"}],  "constraints": [{"type": "security", "rule_ref": "policy://..."}],  "acceptance_criteria": [{"id": "AC-1", "oracle": "test://..."}],  "risk_class": "moderate",  "operating_profile": "research",  "system_bundle_id": "sha256:...",  "resource_budget": {"max_cost_usd": 20, "max_wall_seconds": 3600},  "human_checkpoints": ["external_side_effect", "production_deploy"],  "data_policy_ref": "policy://retention/project-default/v3"}

### Canonical event

{  "event_id": "evt_...",  "event_type": "tool.call.completed",  "schema_version": "1.0.0",  "occurred_at": "2026-07-10T04:00:00Z",  "recorded_at": "2026-07-10T04:00:00.120Z",  "mission_id": "mis_...",  "run_id": "run_...",  "node_id": "builder.execute",  "system_bundle_id": "sha256:...",  "module": {"id": "tool.git", "version": "2.1.0", "digest": "sha256:..."},  "parent_event_ids": ["evt_parent"],  "input_refs": ["artifact://tool-request/..."],  "output_refs": ["artifact://tool-result/..."],  "capability_ref": "cap_...",  "usage": {"wall_ms": 421, "cost_usd": 0.0},  "security_class": "internal",  "integrity": {"producer": "gateway-1", "digest": "sha256:...", "signature": "..."}}

### MemoryItem

{  "memory_id": "mem_...",  "memory_type": "semantic_claim",  "content": {"subject": "...", "predicate": "...", "object": "..."},  "source_refs": [{"artifact_ref": "artifact://source/...", "locator": "p.12"}],  "observed_at": "2026-07-09T00:00:00Z",  "valid_from": "2026-07-09T00:00:00Z",  "valid_to": null,  "confidence": {"value": 0.82, "method": "calibrated_extractor_v2"},  "verification_status": "corroborated",  "contradicting_refs": [],  "applicability": {"projects": ["proj_..."], "task_tags": ["architecture"]},  "security_class": "internal",  "lineage": {"derived_by": "extractor@1.4.2", "parent_ids": ["evt_..."]},  "expiration_policy": {"review_after": "2026-10-01"}}

### EvaluationResult

{  "evaluation_id": "eval_...",  "subject_run_id": "run_...",  "evaluator": {"module_id": "eval.requirement_coverage", "version": "1.3.0"},  "dataset_item_handle": "blind://holdout/item-184",  "metric": "requirement_coverage",  "value": 0.94,  "uncertainty": {"kind": "bootstrap_ci", "low": 0.90, "high": 0.97},  "subgroups": {"accessibility": 0.88},  "evidence_refs": ["artifact://test-report/..."],  "judge_output_ref": null,  "status": "valid",  "integrity": {"digest": "sha256:...", "signature": "..."}}

### ImprovementProposal

{  "proposal_id": "prop_...",  "parent_bundle_id": "sha256:parent",  "target": {"module_id": "agent.builder", "field_path": "/prompt/handoff"},  "current_behavior": "Free-form designer comments",  "hypothesis": "Structured severity and validation criteria reduce ambiguous revisions",  "evidence_refs": ["evt_...", "eval_..."],  "candidate_diffs": ["artifact://diff/candidate-a"],  "expected_effects": {"iterations": -1.0, "quality": 0.03, "token_cost": 0.05},  "risks": ["Longer handoff", "Over-structured minor feedback"],  "autonomy_level": 2,  "deployment_scope": {"task_types": ["software.web_app"], "percent": 5},  "experiment_plan_ref": "expplan://...",  "rollback_condition": "p95 iterations > parent + 1 or quality non-inferiority fails",  "proposer": {"module_id": "optimizer.gepa", "version": "..."}}

### ExperimentRecord

{  "experiment_id": "exp_...",  "protocol_version": "2.0.0",  "preregistration_ref": "artifact://protocol/...",  "arms": [    {"arm_id": "control", "bundle_id": "sha256:parent"},    {"arm_id": "candidate_a", "bundle_id": "sha256:child-a"}  ],  "task_sets": {    "development": "dataset://dev/v4",    "protected": "blind://vault/rotation-12",    "retention": "dataset://retention/v6",    "adversarial": "dataset://security/v3"  },  "randomization": {"unit": "task", "paired": true, "seed_ref": "secret://exp-seed"},  "budgets": {"per_arm_cost_usd": 500, "max_runs": 300},  "primary_endpoint": "paired_task_success_delta",  "decision_rule_ref": "policy://promotion/research-v5",  "status": "completed",  "analysis_ref": "artifact://analysis/..."}

## 17.5 Schema migration and governance

- Every schema uses semantic versioning and machine-readable migration metadata.

- Backward-compatible additions may be accepted by adapters; semantic changes require a new major version and conformance rerun.

- Canonical events are never rewritten to a new schema in place. Projection jobs may materialize upgraded views while retaining original payloads.

- A module cannot declare itself compatible. The registry records conformance evidence produced by an authorized harness.

- Evaluation and promotion schemas are protected because changing fields can hide evidence or alter decisions.

- Migration code is treated as a privileged module with tests, signatures, backups and rollback rehearsal.

LEGO principle made concrete

Replacement means more than matching an input and output type. A compatible module must preserve required semantics for cancellation, idempotency, events, permissions, budgets, state transfer, errors and evaluation. The conformance suite is part of the connector.

# 18. Experimental validation plan

The research question is not whether agents can rewrite prompts. It is whether a governed agent-system can produce cumulative, generalizable improvements at acceptable total cost while preserving prior capabilities, safety and human control. The evaluation must therefore be longitudinal, multi-objective and generation-aware.

## 18.1 Primary hypotheses

Hypothesis

Testable claim

H1 - Cumulative performance

Bounded RSI increases held-out task utility across generations more than static iteration, after accounting for total improvement cost.

H2 - Retention

Governed promotion gates reduce harmful capability regressions compared with unconstrained optimizer acceptance.

H3 - Generalization

Changes selected using diverse replay, holdout and adversarial tasks transfer better than changes selected on one benchmark.

H4 - Memory governance

Provenance-aware typed memory reduces harmful retrieval and repeated failure without excessive context cost.

H5 - Negative evidence

Including failed trajectories and negative memory improves stability compared with success-only consolidation.

H6 - Process/outcome separation

Independent outcome, process and safety evaluators produce better promotion decisions than a single holistic judge.

H7 - Modularity

Typed module replacement preserves downstream behavior more reliably than role-prompt replacement without contracts.

H8 - Meta-improvement

A protected cross-audit protocol can improve evaluator predictive validity without increasing self-favoring promotion errors.

H9 - Human control

Lineage/diff/evidence visualization improves reviewer calibration, decision quality and rollback response.

## 18.2 Baseline systems

Condition

Definition

B0 Static single agent

One model, fixed prompt, tools and no persistent memory.

B1 Static multi-agent

Fixed specialized workflow with identical models/budgets across study.

B2 Multi-agent plus memory

Fixed workflow with episodic/semantic retrieval but no procedural change.

B3 Reflection-only

Self-Refine/Reflexion-style within-task or episodic critique; no governed system mutation. [I06][I07]

B4 Prompt optimizer

DSPy/GEPA optimization under the same train/validation budget; prompts only. [I01]-[I03]

B5 Workflow optimizer

AFlow or typed topology search under matched search budget. [I05]

B6 Human-designed improvement

Experts inspect the same evidence and submit bounded changes.

B7 Full bounded RSI

Typed proposals, candidates, protected gates, promotion, canary and recursive generations.

B8 Unconstrained self-rewrite ablation

Candidate edits selected components and self-evaluates with minimal gates; sandbox only.

## 18.3 Initial task domain and benchmark families

Small software and web-application tasks are the best first domain because they combine open-ended generation with executable evidence. Standard benchmarks are useful but insufficient: they are static, exposed, often optimized for one-shot resolution and do not measure cumulative system change, human approval or rollback. The foundry therefore needs a mixture of public benchmarks, private generated tasks, longitudinal project tasks and incident replays.

Task family

Examples

Purpose

Repository issue resolution

SWE-bench and time-sliced variants; internal issue sets

Executable patch correctness and coding-agent comparison. [E01][E02]

Terminal/system tasks

Terminal-Bench or analogous isolated tasks

Tool use, environment recovery and deterministic success. [E08]

Web interaction

WebArena-style tasks

Browser workflow robustness and side-effect control. [E03]

General assistant tasks

GAIA-style multi-tool tasks

Broad reasoning/tool integration. [E04]

Computer use

OSWorld-style tasks in isolated environments

Long-horizon GUI action and recovery. [E05]

Tool-agent reliability

tau-bench-style domain interactions

Policy, tool correctness and conversational state. [E06]

Multi-agent comparison

AgentBench-style environments

Cross-environment agent evaluation. [E07]

Web app construction

Foundry-generated briefs with functional, visual, accessibility, security and requirement tests

Primary longitudinal domain and designer/user-simulation ablations.

Adversarial/incident tasks

Prompt injection, poisoned memory, flaky tools, dependency compromise, evaluator gaming and prior incidents

Safety and recovery retention.

Longitudinal maintenance

Same projects revisited for feature, bug, refactor and dependency tasks over time

Cumulative memory, regression and generation effects.

## 18.4 Experimental phases

Phase

Scale / design

Exit question

Phase A - Infrastructure validation

50-100 deterministic fixture missions

Event completeness, replay, adapter conformance, sandbox, policy and rollback. No RSI claim.

Phase B - Static system characterization

Public and private task matrix with repeated runs

Variance, baseline performance, cost, failure taxonomy and judge calibration.

Phase C - Single-component optimization

Prompt, skill, retrieval, router and handoff experiments

Causal attribution and promotion-gate validation.

Phase D - Multi-generation study

At least 3-5 frozen generations on fresh time-split task cohorts

Cumulative improvement, retention, cost and recursive status.

Phase E - Meta-RSI study

Shadow evaluator/policy variants with external calibration

Whether improvement mechanisms can improve safely.

Phase F - Human oversight study

Blinded reviewer comparison of dashboard conditions

Trust calibration, decision quality, time and rollback performance.

## 18.5 Longitudinal protocol

1. Freeze model/provider versions or log provider snapshots and include time as a factor when freezing is impossible.

2. Create an initial bundle S0 and characterize its variance on development, holdout, retention and adversarial sets.

3. Run a fixed improvement budget for generation t. Record all candidates, including failed and rejected branches.

4. Promote at most one primary bundle per generation for the main lineage; preserve alternatives as branches.

5. Evaluate S_t on a fresh time-split cohort before its evidence can guide S_t+1.

6. Re-evaluate selected ancestors periodically to distinguish system improvement from task or model drift.

7. Measure whether S_t improves the quality or efficiency of proposals for S_t+1, not only mission output.

8. Stop or reset when complexity, cost or retained-capability debt grows faster than utility.

## 18.6 Core outcome measures

Measure

Operationalization

Initial performance

Utility vector for S0 on each task family and subgroup.

Improvement rate

Held-out utility delta per generation and per unit total improvement cost.

Time/iterations to improvement

Campaign runs, candidates and wall time until accepted practical gain.

Generalization

Transfer to unseen tasks, repositories, domains, time slices, models and profiles.

Capability retention

Worst-case and subgroup performance relative to protected ancestor baselines.

Stability

Variance, failure, timeout, rollback and catastrophic-regression frequency.

Reproducibility

Independent rerun agreement and exact-bundle restoration success.

Human intervention

Review minutes, correction count, disagreement and escalation rate.

Harmful modification rate

Candidates/promotions with safety, quality or cost harm, by severity.

Rollback frequency and recovery

Canary rollback rate, detection delay and restoration completeness.

Improvement-process quality

Precision of diagnoses, proposal success, search efficiency and evaluator predictive validity.

Complexity debt

Prompt/rule/node/dependency growth and maintenance hours per accepted gain.

## 18.7 Ablation studies

Ablation

Question

Typed memory versus raw transcript retrieval

Does structure/provenance improve utility and reduce harmful context?

Semantic memory versus episodic only

Are extracted claims worth their risk and maintenance cost?

Negative memory removed

Does failure retention improve stability or merely create caution/rule accumulation?

Designer removed

Does UI quality fall enough to justify coordination cost?

User simulator removed

Does early issue discovery and generalization change?

Process diagnoser removed

Can outcome-only optimization identify equally useful changes?

Adversarial evaluator removed

How many unsafe or judge-gaming candidates pass?

Human approval removed in sandbox

Does automated policy preserve decisions and where does it fail?

Model routing fixed

How much gain is routing versus prompt/workflow change?

Workflow mutation disabled

Are Level 2 changes sufficient for most improvement?

Protected holdout exposed

Quantify overfitting/evaluator-gaming risk under leakage.

Simple baseline removed

Does architecture complexity appear beneficial only because the control is weak?

## 18.8 Evidence required to call the result bounded RSI

- At least two accepted descendant generations beyond the initial system, with complete lineage and protected evaluation.

- Persistent changes to the agent-system architecture, not only current-answer revision or transient context.

- The improved system participates in producing, selecting or executing the next generation of improvements.

- Fresh held-out gains that exceed a predeclared practical threshold and are not explained by extra resources or model upgrades.

- Capability retention, safety, reproducibility and cost results reported alongside quality.

- Rejected and rolled-back changes reported, including harmful-modification frequency.

- Ablation showing that the recursive improvement mechanism contributes beyond static human iteration or fixed optimization.

- Human authority and immutable governance preserved throughout the study.

## 18.9 Why standard benchmarks are insufficient

Most benchmarks treat the agent as a fixed policy evaluated on independent tasks. RSI research instead studies a sequence of policies, adaptive exposure to evidence, changing memory and potentially changing evaluators. Static public tasks invite contamination and do not measure whether a change remains useful after the environment, model or task distribution shifts. A credible study must therefore use sealed time-split cohorts, repeated ancestor comparisons, full search-cost accounting and tasks that require maintenance over multiple generations.

Minimum publishable experiment

A strong first paper would compare static, memory-only, reflection-only, prompt-optimized, human-improved and bounded-RSI systems over multiple frozen generations of software tasks; use protected time-split holdouts and incident suites; report quality, retention, safety, total improvement cost and rollback; and release the event, bundle and promotion schemas with reproducible fixtures.

# 19. Implementation roadmap

The roadmap deliberately separates scientific validity from feature breadth. Stage 1 proves that a run is reproducible and a change can be compared fairly. Stage 2 proves modular replacement. Stage 3 introduces bounded self-improvement. Stage 4 supports longitudinal and meta-level research. Building the full visualization or autonomous optimizer before the evidence substrate would create an impressive demo with weak claims.

Complexity ranges below are planning estimates for a small experienced research-engineering team, assuming use of existing runtimes, databases and sandbox technologies. They exclude institutional security certification, large-scale benchmark labeling and production support.

## 19.1 Stage 1 - Minimal research prototype

Dimension

Stage 1 plan

Research objective

Can one frozen agent-system bundle execute software tasks reproducibly, emit complete evidence and support a fair manual candidate comparison?

Scope

Small repository and web-app tasks; one primary runtime; local or single-cluster deployment; human promotion only.

Core components

MissionSpec, SystemBundle, LangGraph adapter, OpenHands worker, mini-SWE-agent baseline, deterministic tests, event ledger, object store, basic trace UI, manual experiment runner and rollback to parent.

Technical stack

Python/FastAPI/Pydantic; LangGraph; PostgreSQL/pgvector; S3-compatible object store; rootless Docker; OpenTelemetry; Phoenix or MLflow.

Exit criteria

At least 95% required event coverage on fixtures; exact bundle resolution; crash/replay and duplicate-action tests pass; 20+ paired candidate/control experiments reproducible; rollback restores parent artifact and configuration.

Primary risks

Runtime events do not map cleanly; flaky tests; hidden environment drift; coding worker overprivilege; excessive trace data.

Do not build yet

Automatic prompt mutation, workflow search, graph memory, A2A, meta-RSI, global module marketplace or strategy-game UI.

Estimated complexity

High prototype complexity: roughly 3-5 engineer-months plus research/evaluation design and task curation.

## 19.2 Stage 2 - Modular Agent Foundry

Dimension

Stage 2 plan

Research objective

Can agents, workers, skills, tools, models, memories and workflows be replaced through stable contracts without corrupting evidence or downstream behavior?

Scope

Multiple module versions; structured context; signed registry; limited alternate workers; richer human dashboard.

Core components

Universal manifest, conformance SDK, module registry, capability gateway, memory staging and typed layers, context builder, PydanticAI worker adapter, MCP tool adapter, optional alternate runtime in test-only mode, experiment datasets and lineage UI.

Technical stack

Stage 1 plus OPA/Cedar, Vault/KMS adapter, Cosign/SBOM, Git/OCI packages, optional Graphiti read-model experiment.

Exit criteria

Hot-swap tests pass for at least three worker modules and two tool providers; schema/semantic conformance detects seeded incompatibilities; memory provenance and deletion tests pass; signed bundle supply chain is verifiable.

Primary risks

Manifest becomes too broad; semantic compatibility remains underspecified; adapters leak framework behavior; memory write paths proliferate.

Do not build yet

Automatic production promotion, evaluator mutation, broad external agent federation or Level 5 self-modification.

Estimated complexity

Very high platform complexity: additional 6-10 engineer-months plus UX, security and benchmark work.

## 19.3 Stage 3 - Bounded self-improvement

Dimension

Stage 3 plan

Research objective

Can the foundry propose, test and retain low- and medium-impact system changes with lower regression risk than fixed optimization or human-only iteration?

Scope

Autonomy Levels 1-2 and selected Level 3; prompt, skill, retrieval, routing, handoff and bounded topology changes.

Core components

Diagnosers, GEPA/DSPy proposal adapter, typed mutation library, experiment controller, blind holdout service, retention/adversarial suites, statistical analysis, promotion gate, shadow/canary deployment and automatic rollback.

Technical stack

Stage 2 plus experiment scheduler, protected dataset vault, policy-as-code promotion, canary routing and monitoring alerts.

Exit criteria

At least two accepted descendant generations on fresh cohorts; gains exceed practical thresholds; no critical safety regression; complete search-cost accounting; harmful-modification and rollback rates reported.

Primary risks

Benchmark leakage, judge gaming, multiple-comparison error, search cost, rule accumulation, false causal narratives and human approval fatigue.

Do not build yet

Autonomous evaluator-root replacement, trusted code modification, training-pipeline changes or unrestricted cross-project rule propagation.

Estimated complexity

Research-intensive: additional 8-14 engineer/researcher-months plus protected task creation and human evaluation.

## 19.4 Stage 4 - Research-grade RSI platform

Dimension

Stage 4 plan

Research objective

Can improvement remain cumulative, generalizable, auditable and human-controlled over long horizons, including controlled changes to the improvement process itself?

Scope

Longitudinal multi-project studies, multiple runtimes/workers, Level 4 shadow experiments, federated evaluation and advanced lineage visualization.

Core components

Evaluator cross-audit, benchmark rotation, causal analysis, ancestor re-evaluation, multi-runtime conformance, incident corpus, privacy-preserving research exports, governance committee workflows and evolution dashboard.

Technical stack

Hardened deployment, stronger isolation such as microVMs, multi-tenant policy, durable queues, data warehouse and reproducible research packaging.

Exit criteria

Multi-generation gains replicate across time/task/model slices; evaluator changes improve external predictive validity; rollback and incident response are demonstrated; independent researchers can reproduce core analyses from released fixtures.

Primary risks

Distribution and model drift, unbounded operational complexity, institutional governance burden, privacy/reproducibility conflict and mistaken claims of open-ended RSI.

Do not build without separate program

Autonomous modification of policy root, sandbox root, audit ledger, signing infrastructure, foundation-model training or organizational human authority.

Estimated complexity

Program scale: additional 12-24+ engineer/researcher-months, plus ongoing benchmark operations, security and governance.

## 19.5 First 90-day build sequence

1. Weeks 1-2: Freeze canonical MissionSpec, SystemBundle and event schemas; implement fixture-only ledger and bundle resolver.

2. Weeks 3-4: Build LangGraph RuntimeAdapter and a no-model deterministic sample workflow; validate crash, resume, cancel and duplicate suppression.

3. Weeks 5-6: Integrate OpenHands and mini-SWE-agent in isolated repositories; normalize artifacts, commands, usage and test evidence.

4. Weeks 7-8: Add deterministic test service, project policy, capability gateway and basic operator trace/evidence screens.

5. Weeks 9-10: Implement manual candidate branching and matched replay; create initial development, retention and adversarial fixtures.

6. Weeks 11-12: Run pilot experiments, audit evidence completeness, calibrate evaluators and publish a Stage 1 internal protocol and failure report.

## 19.6 Stage-gate checklist

Transition

Required evidence

Before modularity

Event completeness, exact bundle identity, replay and rollback work on deterministic fixtures.

Before memory learning

Source provenance, quarantine, access controls, contradiction and expiry are implemented.

Before automated proposals

Human-designed candidate experiments demonstrate fair comparison and reliable gates.

Before workflow mutation

Single-component attribution, retention suite and search-budget accounting are reliable.

Before automatic canary

Policy denial, capability revocation, alerts and rollback have been exercised in drills.

Before meta-RSI

Independent evaluator calibration, protected root and governance committee process exist.

Before production framing

External security review, SLOs, incident response, privacy policy and longitudinal evidence are complete.

# 20. Open research questions

Question

Research problem

RQ1 Causal diagnosis

How accurately can models infer which process component caused an outcome, and which structured evidence most improves that accuracy?

RQ2 Search allocation

How should candidate budgets be divided among prompts, skills, retrieval, routing and topology under a multi-objective profile?

RQ3 Retention frontier

What is the best practical test for preserving capabilities when task distributions and foundation models change?

RQ4 Benchmark leakage

How can a continually improving system use past evidence without gradually inferring protected holdouts?

RQ5 Evaluator predictive validity

Which combinations of deterministic checks, model judges and human samples best predict deployment utility and incidents?

RQ6 Judge independence

How much does provider/model-family separation reduce common-mode error when proposers and evaluators share training data?

RQ7 Memory consolidation

When does a recurring episode justify a scoped semantic claim or procedural rule, and how should that scope be learned?

RQ8 Negative memory

When do failure warnings prevent repeated harm, and when do they create excessive caution or brittle prohibitions?

RQ9 Topology search

Can workflow mutations generalize beyond the task families used to discover them, or do they mostly encode benchmark-specific shortcuts?

RQ10 Model routing

Can routing improvements be disentangled from model-provider drift, changing prices and hidden server updates?

RQ11 Complexity debt

What complexity metric best predicts when accumulated prompts, rules and agents will lower future adaptability?

RQ12 Recursive depth

Does improvement efficiency continue beyond a few generations, plateau, oscillate or degrade under fixed model capability?

RQ13 Meta-evaluator safety

What external evidence is sufficient to authorize a change to the mechanism that judges future changes?

RQ14 Human oversight

Which explanation and visualization designs improve calibrated intervention rather than automation bias?

RQ15 Cross-runtime portability

Can one system bundle preserve semantics across LangGraph, Microsoft Agent Framework and other runtimes, or only approximate behavior?

RQ16 Incident learning

How should real incidents update negative memory and tests without allowing one rare event to dominate all future policy?

RQ17 Privacy versus replay

How can sensitive traces be minimized or deleted while retaining enough evidence to validate longitudinal claims?

RQ18 Improvement economics

When does total campaign cost, including failed candidates and human review, outweigh the steady-state benefit of an accepted change?

RQ19 Adversarial adaptation

How should security evaluation evolve when the candidate can learn recurring test patterns and defenses?

RQ20 Definition boundary

What empirical threshold separates governed optimization from bounded RSI in a way that is useful across research communities?

## 20.1 Priority ordering

Priority

Questions

Immediate

Causal diagnosis, evidence completeness, evaluator calibration, retention, search-cost accounting and secure replay.

After Stage 2

Memory consolidation, role ablations, routing, cross-runtime conformance and complexity debt.

After Stage 3

Recursive depth, workflow generalization, benchmark leakage and incident learning.

Meta-level

Evaluator governance, human oversight calibration and definition of bounded RSI.

# 21. Claims that remain speculative

The architecture is feasible, but the strongest benefits are hypotheses. The report distinguishes what can be engineered now from what requires controlled evidence or remains unjustified.

Claim

Status

Evidence needed / qualification

A modular foundry can execute frozen multi-agent workflows with complete lineage.

Feasible now

Existing graph runtimes, typed schemas, event stores and signing tools are sufficient; integration quality remains to be proven.

Prompts, skills, retrieval and routing can be optimized automatically.

Demonstrated in bounded research settings

DSPy, GEPA, TextGrad and related work support feasibility, not guaranteed transfer. [I01]-[I04]

Workflow topology can be improved by automated search.

Experimentally feasible

AFlow and graph-optimization work provide evidence, but cost and overfitting are substantial. [I05][I11]

Typed provenance-aware memory will improve long-horizon production tasks.

Plausible, unproven for this system

Memory systems demonstrate useful mechanisms; the foundry-specific causal effect needs ablation. [M01]-[M04]

Positive and negative analysis together improve stability.

Plausible

Complementary evidence may help, but a two-manager structure is not itself validated.

The platform will improve monotonically across generations.

Unsupported

Plateaus, oscillation, drift and regression are expected; no monotonicity claim should be made.

An LLM can reliably discover causal process improvements from traces.

Speculative

Trace reflection can generate hypotheses, but causal accuracy is an open empirical question.

Meta-RSI can safely improve evaluators and thresholds.

High-risk experimental

Requires protected cross-audit and external authorization; useful gains are not guaranteed.

Visualization will increase trust.

Misleading as stated

Visualization may improve understanding or may increase automation bias. Measure calibration and decision quality, not trust alone.

The system is model-agnostic.

Architecturally achievable, behaviorally limited

Adapters can be provider-neutral, but model capabilities, tool schemas and context behavior are not interchangeable.

A universal module manifest enables drop-in semantic compatibility.

Partly speculative

Structural compatibility is straightforward; behavioral semantics require task-specific conformance.

The system constitutes open-ended RSI.

Currently unjustified

The proposed boundary is intentionally bounded and depends on human authority and protected infrastructure.

Level 5 autonomous code/training modification is a natural next step.

Not justified by this project

It changes the threat model and trusted computing base and should require a separate research and governance program.

## 21.1 Claims language for publications and demos

Guidance

Language

Use

"Governed system optimization," "bounded agent-system self-modification," "multi-generation procedural improvement," or "bounded RSI" only when recursive criteria are met.

Avoid

"Self-aware," "autonomous organization," "unrestricted self-improvement," "learns from everything," "guaranteed improvement" and "production-ready" without evidence.

Report

All search cost, rejected variants, regressions, rollbacks, human effort, evaluator identity, model drift and protected-holdout design.

Separate

Implemented features, proposed architecture, primary-paper results, project/vendor claims and the foundry team's own empirical results.

# 22. The single strongest research contribution

Proposed contribution

An evidence-carrying, versioned and independently governed protocol for recursive improvement of agent-system configurations, in which every persistent modification is linked from causal hypothesis to typed diff, matched experiment, protected evaluation, scoped promotion, deployment monitoring and rollback.

The strongest contribution is not a new cast of agent roles. It is a scientific and operational protocol that makes agent-system evolution inspectable and falsifiable. Existing runtimes execute agents; optimizers mutate prompts or workflows; memory systems retain experience; observability tools record traces. The foundry's contribution is to connect these into a single evidence model without granting the optimizer authority over its own truth conditions.

A successful implementation would provide three reusable artifacts to the field. First, a framework-neutral SystemBundle and module contract that identifies the full behavior under test. Second, a canonical event and lineage model that supports replay across runtime, model, memory and evaluator versions. Third, a promotion protocol that treats self-modification as a protected experiment with retained-capability, security, resource and rollback gates.

This contribution is scientifically valuable even if recursive improvement is modest. It would make negative results legible: the field could measure where improvement plateaus, which changes overfit, how much search costs, when memory harms, how evaluators fail and how often rollback is necessary. That is more defensible than demonstrating an agent that rewrites its prompt and declaring success.

## 22.1 Final architecture decision

Decision area

Chosen direction

System identity

Signed, content-addressed SystemBundle with full lineage.

Primary runtime

LangGraph for the first implementation, behind a foundry RuntimeAdapter.

Worker model

Pydantic-typed semantic modules; OpenHands coding worker; mini-SWE-agent control.

Evidence root

Append-only Postgres event ledger plus content-addressed object store.

Memory

Typed governed memories and rebuildable vector/temporal projections; procedural memory in signed version control.

Improvement

Pluggable human/GEPA/DSPy/typed mutation proposers with no promotion authority.

Evaluation

Deterministic tests plus independent judges, protected holdouts, retention and adversarial suites.

Governance

OPA/Cedar-style policy, capability gateway, secret broker, signed manifests and tiered human approval.

Deployment

Shadow, canary, scoped production and automatic rollback to parent.

Claim

Experimental agent-system control plane capable of bounded RSI after multi-generation evidence.

## 22.2 Immediate next artifact

The next artifact should be a small, executable reference repository, not another architecture expansion. It should implement the Stage 1 schemas, deterministic fixture workflow, LangGraph adapter, OpenHands and mini-SWE-agent workers, event ledger, paired experiment runner and manual promotion record. The first success criterion is not autonomous improvement. It is that an independent researcher can reproduce a mission and candidate comparison from the bundle, events and artifacts.

# Appendix A. Full module manifest template

module_id: agent.buildermodule_type: agentversion: 1.3.0digest: sha256:...publisher: org.example.foundrycreated_at: 2026-07-10T00:00:00Zpromotion_status: experimentalparent_version: 1.2.0rollback_target: agent.builder@1.2.0purpose: Implement a software task in an isolated repository workspace.responsibilities:  - inspect the repository and requirements  - propose and implement a bounded patch  - run declared tests and report unresolved issuesnon_responsibilities:  - change user requirements  - approve deployment  - alter evaluation or governance policytask_tags: [software, coding]risk_class: moderateinputs:  schema_ref: schema://builder-input/2.0.0outputs:  schema_ref: schema://builder-output/2.0.0errors:  schema_ref: schema://module-error/1.0.0events:  schema_ref: schema://worker-events/1.1.0streaming: trueidempotency:  key_fields: [mission_id, node_id, attempt]preconditions:  - repository_snapshot_verified  - acceptance_criteria_presentpostconditions:  - changed_files_manifest_present  - command_receipts_present  - unresolved_issues_explicitallowed_tools:  - tool.terminal@^2  - tool.file_editor@^1  - tool.test_runner@^3requested_permissions:  filesystem:    read: [workspace]    write: [workspace]  network:    mode: deny_by_default    allow: [pypi.org, registry.npmjs.org]  secrets:    classes: []  side_effects:    external: forbiddenpermission_inheritance: narrower_onlymodel_requirements:  modalities: [text]  tool_calling: optional  structured_output: required  min_context_tokens: 32000supported_providers: [openai, anthropic, google, local]model_policy_ref: model-policy://coding/research-v2memory_read_scope:  - project.source  - project.semantic_verified  - procedural.coding  - negative.codingmemory_write_scope:  - working  - episodic_candidatecontext_budget:  max_input_tokens: 60000  source_fraction: 0.55  procedure_fraction: 0.15  working_fraction: 0.30resource_budget:  max_output_tokens: 24000  max_cost_usd: 8.00  max_wall_seconds: 1800  max_tool_calls: 120  max_iterations: 40  max_parallelism: 1quality_metrics:  - requirement_coverage  - executable_test_pass_rate  - patch_scope  - security_findings  - cost_usd  - wall_secondsacceptance_floors:  critical_tests: 1.0  requirement_coverage: 0.90safety_constraints:  - no_secret_access  - no_host_filesystem  - no_test_deletion_without_explicit_requirement  - no_external_communicationsandbox_profile: sandbox://coding/rootless-v3data_classes: [internal]known_failure_modes:  - edits tests to fit incorrect implementation  - changes unrelated files  - installs unnecessary dependencies  - repeats failing command without diagnosisretry_policy:  max_attempts: 2  retryable_errors: [transient_model, transient_tool]timeout_policy:  node_seconds: 1800cancellation:  supported: true  cleanup_required: trueescalation_policy:  - condition: conflicting_requirements    action: request_human  - condition: external_side_effect_required    action: deny_and_request_humanfallback_module: agent.builder.safe@1.0.0dependencies:  modules:    - tool.terminal@^2.1    - tool.file_editor@^1.5    - evaluator.patch@^3  environment: oci://registry/foundry/coding-worker@sha256:...state_schema_ref: schema://builder-state/1.0.0state_migration_ref: nullconformance_suite:  - conformance://agent-base/2  - conformance://coding-worker/3  - security://prompt-injection/4  - security://workspace-isolation/2test_suite:  unit: artifact://tests/builder-unit-v5  integration: artifact://tests/builder-integration-v7  retention: dataset://retention/coding-v6monitoring:  required_metrics: [success, cost, latency, retries, policy_denials]  canary_window_missions: 50  rollback_triggers:    - critical_security_finding > 0    - test_pass_rate_delta < -0.02    - cost_delta > 0.25 and quality_delta < 0.01provenance:  source_repo: https://example.org/foundry/modules/builder  commit: abcdef...  sbom_ref: artifact://sbom/...  build_attestation_ref: artifact://attestation/...  signatures:    - signer: org.example.release      signature: ...approval_evidence_refs: [approval://...]

# Appendix B. Promotion policy example

package foundry.promotiondefault decision := {"action": "reject", "reason": "requirements_not_met"}critical_violation if input.security.critical_count > 0critical_violation if input.integrity.valid == falsecritical_violation if input.holdout.leakage_detected == trueretention_ok if input.retention.minimum_delta >= input.policy.retention_floorquality_ok if input.primary.lower_confidence_bound >= input.policy.min_practical_gaincost_ok if input.resource.cost_delta <= input.profile.max_cost_deltalatency_ok if input.resource.p95_latency <= input.profile.p95_latency_ceilingreproducible if input.reproducibility.pass_rate >= input.policy.reproducibility_flooreligible if {  not critical_violation  retention_ok  quality_ok  cost_ok  latency_ok  reproducible}decision := {  "action": "canary",  "scope": input.proposal.requested_scope,  "approval_tier": required_approval_tier,  "rollback_target": input.parent_bundle_id} if eligiblerequired_approval_tier := "A3" if input.proposal.autonomy_level >= 4required_approval_tier := "A2" if input.proposal.autonomy_level == 3required_approval_tier := "A1" if input.proposal.autonomy_level == 2required_approval_tier := "A0" if input.proposal.autonomy_level <= 1

## Appendix B.1 Decision evidence checklist

- Exact parent and candidate bundle digests resolve and signatures validate.

- Proposal target is inside allowed mutation schema and no undeclared file changed.

- Control, candidate and human baseline used matched tasks, environment and budgets.

- Protected holdout remained blind and leakage detector passed.

- Primary endpoint, minimum practical effect and stopping rule match preregistration.

- All critical subgroups and retained capabilities meet floors.

- Adversarial/security suite has no critical failure and residual risks are documented.

- Total search, evaluation, human and steady-state costs are reported.

- Canary scope, monitoring duration, state migration and rollback are executable.

- Approver sees exact diff, counterevidence, uncertainty and rejected alternatives.

# Appendix C. Threat-control ownership

Threat

Primary control owner

Accountable role

Detection evidence

Identity spoofing

Control API / identity provider

Security owner

Auth failure and anomalous principal alerts

Policy bypass

Policy Decision Point and Tool Gateway

Platform security

Denied/allowed action audit and policy mutation tests

Prompt injection

Context Builder, worker adapter and Tool Gateway

Agent safety lead

Injection suite and unexpected tool-attempt rate

Memory poisoning

Memory Service and projection builders

Data governance

Unverified promotion, contradiction and harmful retrieval metrics

Sandbox escape

Sandbox Manager and infrastructure

Infrastructure security

Escape drills, kernel/image advisories and containment telemetry

Secret exposure

Secret Broker and egress proxy

Security owner

Canary secret, log scan and egress anomaly

Evaluator gaming

Evaluation Harness and holdout vault

Research governance

Leakage alarms, judge disagreement and shadow audit

Supply-chain compromise

Module Registry and CI release process

Release engineering

Signature/SBOM/provenance verification and revocation

Runaway cost

Runtime, Experiment Controller and model gateway

Platform operations

Budget alarms, kill events and cost attribution

Unsafe promotion

Promotion Gate and human approver

Governance authority

Decision replay, canary alerts and rollback drills

Audit tampering

Audit Ledger

Independent compliance/security

Hash-chain/signature verification and offsite backup

# Appendix D. Source catalog

Sources were checked as of 10 July 2026. Repository status and product details can change rapidly. Primary papers and official repositories/documentation were preferred. Repository benchmark numbers and vendor statements are treated as project claims unless independently reproduced.

## D.1 User-provided design sources

[U1] Recursive Agent Foundry. User-provided baseline concept audited in this report; local document, placeholder URL used only because DOCX hyperlinks require a target.

[U2] Master Research and Architecture Prompt: A Modular RSI Agent Foundry. User-provided execution brief and required deliverable structure; local document.

## D.2 Agent frameworks, coding systems and protocols

[F01] OpenAI Agents SDK for Python. Official repository.

[F02] LangGraph. Official repository and runtime source.

[F03] AutoGen. Official repository; current README directs new users toward Microsoft Agent Framework.

[F04] Microsoft Agent Framework. Official successor framework repository.

[F05] CrewAI. Official repository.

[F06] MetaGPT. Official repository.

[F07] Google Agent Development Kit for Python. Official repository.

[F08] Microsoft Semantic Kernel. Official repository; current README identifies Microsoft Agent Framework as successor.

[F09] PydanticAI. Official repository.

[F10] Hugging Face smolagents. Official repository.

[F11] OpenHands Agent Canvas / control center. Official repository and transition notice.

[F12] OpenHands Software Agent SDK. Official coding-agent SDK repository.

[F13] SWE-agent. Official repository; recommends mini-SWE-agent for current default use.

[F14] mini-SWE-agent. Official repository.

[F15] Claude Agent SDK for Python. Official repository.

[F16] OpenAI Codex. Official open-source coding-agent repository.

[F17] Model Context Protocol specification. Official specification repository.

[F18] Agent2Agent Protocol. Official Linux Foundation project repository.

[F19] Agent Skills specification. Open skill-package standard.

[F20] Representative LangGraph persistence and HITL issues. Issues 7417, 8026, 8298 and related records inspected to test operational limitations.

[F21] Representative OpenAI Agents SDK session/state issues. Issues 3738 and 2671 inspected.

[F22] Representative Microsoft Agent Framework checkpoint/budget issues. Issues 5621 and 6934 inspected.

## D.3 Improvement and evaluation research

[I01] DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines. ICLR 2024 paper and official DSPy repository.

[I02] Optimizing Instructions and Demonstrations for Multi-Stage Language Model Programs (MIPROv2). Prompt/program optimization research.

[I03] GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning. Reflective evolutionary optimization; see also official GEPA repository.

[I04] TextGrad: Automatic Differentiation via Text. Textual feedback optimization; published in Nature in 2025.

[I05] AFlow: Automating Agentic Workflow Generation. Workflow search research.

[I06] Self-Refine: Iterative Refinement with Self-Feedback. Within-task output refinement.

[I07] Reflexion: Language Agents with Verbal Reinforcement Learning. Episodic verbal feedback and reflection.

[I08] ExpeL: LLM Agents Are Experiential Learners. Cross-task experiential lessons.

[I09] Voyager: An Open-Ended Embodied Agent with Large Language Models. Skill-library and curriculum mechanisms in Minecraft.

[I10] STOP: Self-Taught Optimizer. Recursive improvement of an improver program under a narrow scaffold.

[I11] Language Agents as Optimizable Graphs. Graph-based optimization of agent systems.

[I12] EvoAgentX. Agent workflow evolution framework; treat reported results as research claims.

[I13] A Self-Improving Coding Agent. Research on agent self-improvement for coding.

[I14] Darwin Godel Machine: Open-Ended Evolution of Self-Improving Agents. Research prototype for open-ended self-modification; not a direct production blueprint.

[I15] Agent-as-a-Judge: Evaluate Agents with Agents. Trajectory-aware agent evaluation.

## D.4 Memory systems

[M01] Letta. Official repository; current README marks the original server as legacy and points to current agent products.

[M02] MemGPT: Towards LLMs as Operating Systems. Foundational stateful-agent memory paper.

[M03] Mem0. Official memory-layer repository; managed-platform benchmark claims are not treated as independent proof.

[M04] Graphiti. Official temporal context-graph repository.

[M05] Zep: A Temporal Knowledge Graph Architecture for Agent Memory. Temporal graph memory research.

[M06] Event Sourcing pattern. General software architecture reference for immutable event-ledger design.

## D.5 Observability, security and governance

[O01] OpenTelemetry Semantic Conventions for Generative AI. Official semantic-convention documentation.

[O02] Arize Phoenix tracing documentation. Official tracing and evaluation workbench documentation.

[O03] MLflow GenAI tracing. Official tracing documentation.

[O04] LangSmith observability. Official documentation.

[S01] MCP Security Best Practices. Official protocol security guidance.

[S02] OWASP Top 10 for LLM Applications 2025. Community security guidance.

[S03] NIST AI Risk Management Framework. Official risk-management framework.

[S04] NIST AI 600-1: Generative Artificial Intelligence Profile. Official generative-AI risk profile.

[S05] SLSA specification v1.2. Software supply-chain provenance framework.

## D.6 Benchmark and evaluation families

[E01] SWE-bench. Official repository; see also arXiv:2310.06770.

[E02] SWE-bench-Live. Time-evolving software-engineering benchmark.

[E03] WebArena. Realistic web-agent benchmark.

[E04] GAIA. General AI assistant benchmark.

[E05] OSWorld. Computer-use benchmark.

[E06] tau-bench. Tool-agent interaction benchmark.

[E07] AgentBench. Multi-environment agent benchmark.

[E08] Terminal-Bench. Terminal task benchmark and evaluation environment.

# Appendix E. Glossary

Term

Definition

Agent

A model-driven module that selects or generates actions under an explicit contract and capability set.

Agent system

The full configuration of models, prompts, skills, tools, memory, workflow, evaluation and governance used to perform tasks.

Bounded RSI

Multi-generation persistent improvement of selected agent-system components under protected constraints, independent evaluation and rollback.

Candidate

An experimental child SystemBundle created by a typed change proposal.

Capability

A time- and scope-limited authorization to read, write, call a tool or cause a side effect.

Canonical event

Append-only, versioned observation used to reconstruct execution and governance history.

ContextPackage

The exact, cited and budgeted evidence/procedure set supplied to one module invocation.

Control

The unchanged parent bundle executed under the same experimental conditions as candidates.

Evaluator root

Protected set of datasets, tests, judges, metrics and thresholds used to assess candidates.

Evidence

Source, event, artifact, test, evaluation or human record with provenance and integrity.

Improvement policy

Modules and rules that diagnose runs and generate candidate modifications.

Memory projection

Rebuildable vector, graph, summary or search view derived from canonical evidence and approved memories.

Module

Replaceable unit with a signed manifest, schemas, permissions, budgets, tests and lifecycle status.

Promotion

Governed activation of a candidate for a defined scope after gates and approvals.

Procedural memory

Versioned prompts, skills, workflows, tests and policies that influence future behavior.

Replay

Re-execution or reconstruction of a mission from a frozen bundle, inputs, environment and event history.

Rollback

Restoration of a known parent bundle and compatible state after a trigger or human command.

SystemBundle

Content-addressed identity of the complete agent-system behavior and environment under test.

Trusted root

Human authority and protected security, evidence, evaluation, signing and rollback services outside autonomous modification.

# Closing note

The design is ambitious but technically coherent once the self-improvement claim is made conditional on evidence. The most important implementation discipline is to resist adding autonomy before adding observability, replay, protected evaluation and rollback. A foundry that can explain why it refused to improve is more scientifically credible than one that always produces a new version.

End of report  |  Investigation date: 10 July 2026