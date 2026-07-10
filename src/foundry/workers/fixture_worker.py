"""FixtureWorker: deterministic stand-in for a coding worker (report 19.5).

Stage 1 validates the control plane with a no-model worker before any real
coding agent (OpenHands, mini-SWE-agent) is integrated behind the same
:class:`~foundry.contracts.WorkerLike` boundary. The worker is a pure
function of ``(task_input, config, seed)``: the ``strategy`` key of the
frozen bundle config selects the naive baseline or the robust ground-truth
transformation, so candidate-vs-control experiments have a known answer.
"""

from __future__ import annotations

from typing import Any

from .fixture_tasks import naive_slugify, robust_slugify

_STRATEGIES = {
    "naive": naive_slugify,
    "robust": robust_slugify,
}


class FixtureWorker:
    """Deterministic slugify worker conforming to ``WorkerLike``.

    The ``seed`` argument is part of the worker contract but unused here:
    the fixture transformations are already deterministic, which is exactly
    what makes them useful for crash/replay conformance testing.
    """

    def invoke(
        self, task_input: dict[str, Any], config: dict[str, Any], seed: int
    ) -> dict[str, Any]:
        strategy = config["strategy"]
        try:
            transform = _STRATEGIES[strategy]
        except KeyError:
            raise ValueError(
                f"unknown fixture strategy {strategy!r}; "
                f"expected one of {sorted(_STRATEGIES)}"
            ) from None
        return {"output": transform(task_input["text"]), "strategy": strategy}
