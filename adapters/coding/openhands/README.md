# OpenHands coding worker (not yet implemented)

Home of the OpenHands Software Agent SDK integration (report 16: recommended coding worker backend for Stages 1-2). The seam it must fill is now fully specified and exercised by the deterministic coding domain:

- Implement `foundry.contracts.WorkerLike`: `invoke(task_input, config, seed) -> dict`. For coding tasks, `task_input` is `{"task_id", "family", "issue", "files": {relative_path: content}}` and the result must be `{"files": {relative_path: content}, ...}` (the patched repository).
- Wire into experiments with `foundry.workers.make_coding_run_arm(worker)`; scoring stays with `foundry.evaluation.DeterministicTestService.score`, which force-restores the trusted checks file before executing (read-only tests, report 14.2), so an agent that edits tests to pass is scored against the originals.
- `DeterministicCodingWorker` remains the conformance and replay baseline; compare against it and against the mini-SWE-agent baseline under matched budgets (report 18.2 B6/B7).

Blockers, stated honestly: an OpenHands run needs an LLM provider key and an isolated Docker/Kubernetes workspace. Per the security boundary in `foundry/evaluation/test_service.py`, model-generated code must NOT be executed by the local-subprocess test service; a real sandbox (rootless container or microVM, report 14.4) has to sit behind the same `run_checks` interface first. Do not integrate this adapter before that exists.
