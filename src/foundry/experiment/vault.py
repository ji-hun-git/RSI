"""Protected holdout vault with blind handles (report sections 13.4, 14.1).

The vault sits outside the self-modification boundary ("Protected holdout
vault, labels, sampling keys and evaluator-root authorization", report
14.1). Candidates and proposers only ever see keyed blind handles
(``blind://<name>/<mac16>``) in a deterministic keyed-shuffled order and
a *redacted* task view -- inputs only, never the true task id and never
the expected output. The single execution path over protected tasks is
:meth:`HoldoutVault.run_blind`: the candidate callback receives a
:class:`BlindTaskView`, the vault scores its output internally against
the sealed ground truth with the scorer fixed at seal time, and only the
float score leaves the vault. Candidate code therefore cannot enumerate,
copy, memorize or echo the holdout (report 13.4: "Do not reuse the final
holdout for repeated optimizer feedback").
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

HANDLE_PREFIX = "blind://"
VAULT_REF_PREFIX = "blind://vault/"


class TaskLike(Protocol):
    """Minimal structural view of an opaque task: only the id is required."""

    task_id: str


@dataclass(frozen=True)
class BlindTaskView:
    """Redacted, candidate-facing view of one protected task.

    ``task_id`` is the blind handle (NOT the true task id), so per-task
    seeds derived from it stay deterministic without identifying the
    task. There is deliberately no ``expected_output`` field: ground
    truth never crosses the vault boundary.
    """

    task_id: str  # the blind handle
    input_text: str
    family: str = ""


#: Trusted scorer fixed at seal time by the sealing principal:
#: ``scorer(task, output) -> float`` over the TRUE task and the candidate output.
Scorer = Callable[[Any, str], float]

#: Untrusted candidate execution callback: ``run(view) -> output``.
BlindRunner = Callable[[BlindTaskView], str]


class HoldoutVault:
    """In-memory protected task store addressed only by blind HMAC handles.

    All task storage is private (``_sets``); the public surface exposes no
    method or callback that receives task contents beyond the redacted
    :class:`BlindTaskView`, and scores are computed inside the vault.
    """

    def __init__(self, secret: bytes) -> None:
        self._secret = secret
        self._sets: dict[str, dict[str, Any]] = {}
        self._scorers: dict[str, Scorer] = {}

    def seal(self, name: str, tasks: list[TaskLike], scorer: Scorer) -> str:
        """Store *tasks* under *name* with their trusted *scorer*.

        The scorer is fixed at seal time by the sealing principal (the
        experiment infrastructure); candidate code never supplies it and
        never calls it. Returns the vault ref ``blind://vault/<name>``.
        """
        if not name or "/" in name:
            raise ValueError(f"invalid vault set name: {name!r}")
        if name in self._sets:
            raise ValueError(f"vault set {name!r} is already sealed; holdouts are immutable")
        by_handle: dict[str, Any] = {}
        for task in tasks:
            handle = self._handle(name, task.task_id)
            if handle in by_handle:
                raise ValueError(f"duplicate task_id in holdout set {name!r}")
            by_handle[handle] = task
        self._sets[name] = by_handle
        self._scorers[name] = scorer
        return VAULT_REF_PREFIX + name

    def handles(self, name: str) -> list[str]:
        """Blind handles for *name* in a deterministic keyed-shuffled order.

        Sorting by the HMAC digest applies a pseudorandom permutation keyed
        by the vault secret: the order is stable across processes and
        platforms but reveals nothing about task contents, ids or the
        original insertion order.
        """
        return sorted(self._sets[name])

    def run_blind(self, name: str, handle: str, run: BlindRunner) -> float:
        """Execute *run* on the redacted view behind *handle*; return only the score.

        This is the only execution path over protected tasks: *run*
        receives a :class:`BlindTaskView` (inputs only -- no expected
        output, no true task id), the vault scores the returned output
        against the sealed ground truth with the seal-time scorer, and
        the caller gets the float score, never the task.
        """
        task = self._sets[name][handle]
        view = BlindTaskView(
            task_id=handle,
            input_text=getattr(task, "input_text", ""),
            family=getattr(task, "family", ""),
        )
        output = run(view)
        return self._scorers[name](task, output)

    def leakage_check(self, name: str, texts: list[str]) -> list[str]:
        """Handles whose task ``input_text`` appears verbatim in any of *texts*.

        Used against proposal evidence and hypothesis text before opening
        protected results; emits nothing itself.
        """
        hits: list[str] = []
        for handle in self.handles(name):
            task = self._sets[name][handle]
            input_text = getattr(task, "input_text", "")
            if input_text and any(input_text in text for text in texts):
                hits.append(handle)
        return hits

    def _handle(self, name: str, task_id: str) -> str:
        mac = hmac.new(self._secret, task_id.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{HANDLE_PREFIX}{name}/{mac[:16]}"
