"""Replacement / hot-swap protocol via shadow execution (report 17.3).

Report 17.3 step 6: "Shadow execution: run old and new module on identical
inputs without production side effects where feasible." This is that check
made concrete for ``WorkerLike`` modules: given the old and new
implementations and a set of conformance cases, run both on the identical
inputs and report whether their outputs agree.

The rule is deliberately conservative (report 17.3 step 7: "never silently
coerce incompatible semantics"). A swap is *compatible* only when both
modules produce byte-identical canonical outputs on every case. Any
divergence is reported case-by-case, not smoothed over -- an operator sees
exactly where the replacement would change behavior and decides, rather
than discovering it in production.

Both `naive` and `robust` fixture workers conform to ``WorkerLike`` yet
behave differently; this check is what distinguishes a genuine drop-in
replacement from a behavior change wearing the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from foundry.contracts import WorkerLike, canonical_json

from .conformance import DEFAULT_WORKER_CASES, ConformanceCase


@dataclass(frozen=True)
class Divergence:
    case: str
    old_output: str
    new_output: str


@dataclass(frozen=True)
class ReplacementReport:
    schema_compatible: bool
    semantic_compatible: bool
    divergences: tuple[Divergence, ...] = ()
    error: str | None = None

    @property
    def compatible(self) -> bool:
        return self.schema_compatible and self.semantic_compatible and self.error is None


def check_replacement(
    old: WorkerLike,
    new: WorkerLike,
    cases: tuple[ConformanceCase, ...] = DEFAULT_WORKER_CASES,
) -> ReplacementReport:
    """Shadow-execute *old* and *new* on identical inputs; report agreement.

    Schema compatibility requires both to return the contract ``dict`` on
    every case; semantic compatibility requires byte-identical canonical
    outputs. A crash in either module fails the check with the error, never
    a silent pass.
    """
    divergences: list[Divergence] = []
    for case in cases:
        try:
            old_out = old.invoke(dict(case.task_input), dict(case.config), case.seed)
            new_out = new.invoke(dict(case.task_input), dict(case.config), case.seed)
        except Exception as exc:
            return ReplacementReport(
                schema_compatible=False,
                semantic_compatible=False,
                error=f"case {case.name!r} raised during shadow execution: {exc}",
            )
        if not isinstance(old_out, dict) or not isinstance(new_out, dict):
            return ReplacementReport(
                schema_compatible=False,
                semantic_compatible=False,
                error=f"case {case.name!r}: a module did not return the contract dict",
            )
        old_canon = canonical_json(old_out).decode("utf-8")
        new_canon = canonical_json(new_out).decode("utf-8")
        if old_canon != new_canon:
            divergences.append(Divergence(case=case.name, old_output=old_canon, new_output=new_canon))

    return ReplacementReport(
        schema_compatible=True,
        semantic_compatible=not divergences,
        divergences=tuple(divergences),
    )


def resolve_worker(bundle: Any, registry: Any, slot: str = "worker") -> WorkerLike:
    """Resolve a bundle's declared worker module through the module registry.

    A bundle pins modules by ``module_id@version`` in ``module_refs``; this
    binds the declared slot to an admitted (conformance-passed) module, so
    the worker a mission runs under is one that demonstrated its contract.
    """
    ref = bundle.module_refs.get(slot)
    if ref is None:
        raise KeyError(f"bundle {bundle.bundle_id} declares no {slot!r} module")
    return registry.resolve(ref)
