# mini-SWE-agent baseline worker (not yet implemented)

Home of the mini-SWE-agent integration: the mandatory transparent baseline for coding experiments (report 5.3, 18.2). Its linear history and minimal action interface make it the control that exposes hidden scaffold effects in richer workers.

The seam is identical to the OpenHands adapter (see `adapters/coding/openhands/README.md`): implement `foundry.contracts.WorkerLike` over the coding `task_input`/`files` shape, wire through `foundry.workers.make_coding_run_arm`, score with `foundry.evaluation.DeterministicTestService.score` (trusted checks are force-restored; doctored tests buy nothing).

Blockers, stated honestly: mini-SWE-agent needs an LLM key, and it drives a POSIX shell (its actions are bash), so on Windows it requires WSL or a container. The same sandbox rule applies as for OpenHands: model-generated commands and code must not run under the local-subprocess test service; a real sandbox (report 14.4) must sit behind the same interface first.
