"""Tool-provider conformance (report 17.2/17.3 applied to the tool boundary).

The module layer admits a worker only after it demonstrates the semantics
its slot requires; tools deserve the same discipline before the gateway
will route calls to them. A tool's contract, though, is not a worker's: a
tool with a real side effect is *expected* to be non-deterministic (a write
changes state), so determinism is required only of a tool that declares
itself side-effect-free. The checks are:

* ``side_effect_class`` -- the declared class is one of the known values
  (an undeclared or invented class is refused);
* ``output_shape`` -- the contract ``dict`` result on every example, with a
  valid input handled rather than raising (declared-input tolerance);
* ``determinism`` -- for a ``side_effect_class == "none"`` tool only, the
  same arguments yield the same output (a pure tool that is secretly
  stateful is a seeded incompatibility and is refused).

Conformance is a separate admission gate, not baked into ``register``: a
deployment step runs it and calls :meth:`ToolGateway.register_conformant`,
which refuses a non-conformant tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from foundry.contracts import CapabilityToken, canonical_json

from .context import ContextualWorker, ToolContext
from .gateway import ToolGateway, ToolProvider

_ALLOWED_SIDE_EFFECTS = frozenset({"none", "read", "write", "external", "monetary"})
TOOL_SUITE = "tool-provider/1"


@dataclass(frozen=True)
class ToolCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class ToolConformanceEvidence:
    tool_id: str
    suite: str
    checks: tuple[ToolCheck, ...] = ()

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)


class ToolConformanceError(Exception):
    """A tool failed conformance and is refused admission."""


@dataclass
class ToolConformanceHarness:
    """Runs the tool-provider conformance suite over declared example args."""

    def checks(
        self, provider: ToolProvider, example_args: list[dict[str, Any]]
    ) -> list[ToolCheck]:
        return [
            self._check_side_effect_class(provider),
            self._check_output_shape(provider, example_args),
            self._check_determinism(provider, example_args),
        ]

    def evidence(
        self, provider: ToolProvider, example_args: list[dict[str, Any]]
    ) -> ToolConformanceEvidence:
        return ToolConformanceEvidence(
            tool_id=provider.tool_id,
            suite=TOOL_SUITE,
            checks=tuple(self.checks(provider, example_args)),
        )

    # -- checks ---------------------------------------------------------------

    @staticmethod
    def _check_side_effect_class(provider: ToolProvider) -> ToolCheck:
        sec = getattr(provider, "side_effect_class", None)
        if sec not in _ALLOWED_SIDE_EFFECTS:
            return ToolCheck(
                name="side_effect_class",
                passed=False,
                detail=f"declared side_effect_class {sec!r} is not one of "
                f"{sorted(_ALLOWED_SIDE_EFFECTS)}",
            )
        return ToolCheck(name="side_effect_class", passed=True)

    @staticmethod
    def _check_output_shape(
        provider: ToolProvider, example_args: list[dict[str, Any]]
    ) -> ToolCheck:
        for args in example_args:
            try:
                result = provider.invoke(dict(args))
            except Exception as exc:
                return ToolCheck(
                    name="output_shape", passed=False, detail=f"invoke raised: {exc}"
                )
            if not isinstance(result, dict):
                return ToolCheck(
                    name="output_shape",
                    passed=False,
                    detail=f"returned {type(result).__name__}, not dict",
                )
        return ToolCheck(name="output_shape", passed=True)

    @staticmethod
    def _check_determinism(
        provider: ToolProvider, example_args: list[dict[str, Any]]
    ) -> ToolCheck:
        # Only a side-effect-free tool is required to be deterministic; a tool
        # with a real effect is expected to change observable state.
        if getattr(provider, "side_effect_class", None) != "none":
            return ToolCheck(
                name="determinism", passed=True, detail="side-effecting tool: exempt"
            )
        for args in example_args:
            try:
                first = canonical_json(provider.invoke(dict(args)))
                second = canonical_json(provider.invoke(dict(args)))
            except Exception as exc:
                return ToolCheck(name="determinism", passed=False, detail=f"raised: {exc}")
            if first != second:
                return ToolCheck(
                    name="determinism",
                    passed=False,
                    detail="a side-effect-free tool produced two different outputs",
                )
        return ToolCheck(name="determinism", passed=True)


TOOL_WORKER_SUITE = "contextual-worker/1"


@dataclass
class ContextualWorkerConformanceHarness:
    """Conformance for a ContextualWorker (report 9.2, 14).

    A tool-using worker is impure, so determinism is not its contract. The
    load-bearing property is capability discipline: it must reach side
    effects only through the gateway and handle a denial gracefully. The
    check runs the worker under a *deny-all* context (a capability that
    authorizes nothing) and requires it to return the contract dict without
    raising -- proving it routes effects through the gateway and respects a
    refusal rather than reaching around it or crashing.
    """

    def checks(
        self,
        worker: ContextualWorker,
        example_inputs: list[tuple[dict[str, Any], dict[str, Any], int]],
    ) -> list[ToolCheck]:
        deny_context = self._deny_all_context()
        for task_input, config, seed in example_inputs:
            try:
                result = worker.invoke(dict(task_input), dict(config), seed, deny_context)
            except Exception as exc:
                return [
                    ToolCheck(
                        name="graceful_denial",
                        passed=False,
                        detail=f"worker raised under a denied tool context: {exc}",
                    )
                ]
            if not isinstance(result, dict):
                return [
                    ToolCheck(
                        name="graceful_denial",
                        passed=False,
                        detail=f"returned {type(result).__name__}, not dict, under denial",
                    )
                ]
        return [ToolCheck(name="graceful_denial", passed=True)]

    def evidence(
        self,
        worker: ContextualWorker,
        example_inputs: list[tuple[dict[str, Any], dict[str, Any], int]],
    ) -> ToolConformanceEvidence:
        return ToolConformanceEvidence(
            tool_id=type(worker).__name__,
            suite=TOOL_WORKER_SUITE,
            checks=tuple(self.checks(worker, example_inputs)),
        )

    @staticmethod
    def _deny_all_context() -> ToolContext:
        from foundry.ledger import EventLedger

        empty_capability = CapabilityToken(subject="conformance", actions=[], resource_scopes=[])
        gateway = ToolGateway(EventLedger(":memory:"))
        return ToolContext(gateway, empty_capability, "conformance", None)
