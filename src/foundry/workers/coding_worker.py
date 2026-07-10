"""DeterministicCodingWorker: no-model coding worker for the coding corpus.

The coding analog of :class:`FixtureWorker` (report 19.5): a pure function
of ``(task_input, config, seed)`` whose ``strategy`` selects the naive
baseline (fixes only the boundary family) or the robust repair procedure
(fixes boundary and comparison families), so candidate-vs-control
experiments on executable-test tasks have a known answer.

Repairs are targeted line edits keyed on the issue text, sharing their
exact bug/fix strings with the corpus generator -- the same
single-source-of-truth arrangement as ``robust_slugify``. A repair never
rewrites the file wholesale, which is what the adversarial tasks (unicode
canary, CRLF integrity assertions) exist to punish.

Real coding agents (OpenHands, mini-SWE-agent) integrate behind the same
``WorkerLike`` boundary and the same ``make_coding_run_arm`` wiring; this
worker stays as the conformance and replay baseline.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from foundry.contracts import SystemBundle, WorkerLike, canonical_json

from .coding_tasks import (
    BOUNDARY_BUG,
    BOUNDARY_FIX,
    COMPARISON_BUG,
    COMPARISON_FIX,
    SOLUTION_FILE,
)

_STRATEGIES = ("naive", "robust")


class DeterministicCodingWorker:
    """WorkerLike coding worker: input is a repo + issue, output a patched repo."""

    def invoke(
        self, task_input: dict[str, Any], config: dict[str, Any], seed: int
    ) -> dict[str, Any]:
        strategy = config["strategy"]
        if strategy not in _STRATEGIES:
            raise ValueError(
                f"unknown coding strategy {strategy!r}; expected one of {sorted(_STRATEGIES)}"
            )
        files = dict(task_input["files"])
        issue = str(task_input.get("issue", ""))
        repairs: list[str] = []

        source = files.get(SOLUTION_FILE, "")
        if "off-by-one" in issue and BOUNDARY_BUG in source:
            files[SOLUTION_FILE] = source.replace(BOUNDARY_BUG, BOUNDARY_FIX, 1)
            repairs.append("boundary")

        if strategy == "robust":
            source = files.get(SOLUTION_FILE, "")
            if "comparison is" in issue and COMPARISON_BUG in source:
                files[SOLUTION_FILE] = source.replace(COMPARISON_BUG, COMPARISON_FIX, 1)
                repairs.append("comparison")

        return {"files": files, "repairs": repairs, "strategy": strategy}


def make_coding_run_arm(worker: WorkerLike) -> Callable[[SystemBundle, Any, int], str]:
    """Build the experiment ``RunArm`` callable for the coding domain.

    Accepts both clear-role :class:`~foundry.workers.coding_tasks.CodingTask`
    objects and the vault's redacted ``BlindTaskView`` (whose ``input_text``
    carries the same candidate-visible JSON), so one wiring serves open and
    protected roles. The arm output is the worker result as canonical JSON,
    matching the ``RunArm -> str`` contract.
    """

    def run_arm(bundle: SystemBundle, task: Any, seed: int) -> str:
        if hasattr(task, "files"):  # clear-role CodingTask
            payload: dict[str, Any] = {"issue": task.issue, "files": dict(task.files)}
        else:  # BlindTaskView: only the candidate-visible serialization
            payload = json.loads(task.input_text)
        task_input = {
            "task_id": task.task_id,
            "family": getattr(task, "family", ""),
            **payload,
        }
        result = worker.invoke(task_input, bundle.config, seed)
        return canonical_json(result).decode("utf-8")

    return run_arm
