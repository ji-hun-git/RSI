"""Module conformance harness (report sections 17.2, 17.3).

The report's LEGO principle is explicit: "Replacement means more than
matching an input and output type... The conformance suite is part of the
connector." A module is admitted not because it has the right method name
but because it demonstrably preserves the semantics its slot requires.

For a ``WorkerLike`` module those semantics are:

* determinism -- the same ``(task_input, config, seed)`` yields the same
  output on every call (the foundation of replay and paired experiments);
* statelessness -- a call's result is independent of what ran before it,
  so interleaving invocations cannot change an answer (no hidden state
  leaks across missions);
* output shape -- the contract's ``dict`` result;
* declared-input tolerance -- valid input for the module's task family is
  handled without raising.

A module that fails any check is non-conformant and is refused admission
(seeded-incompatibility detection). Conformance evidence is signable so
the module registry can bind admission to a trusted harness run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from foundry.contracts import (
    ModuleManifest,
    WorkerLike,
    canonical_json,
    content_digest,
)

WORKER_SUITE = "worker-like/1"


@dataclass(frozen=True)
class ConformanceCase:
    """One deterministic input the harness exercises a worker with."""

    name: str
    task_input: dict[str, Any]
    config: dict[str, Any]
    seed: int = 0


class ConformanceCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    detail: str = ""


class ConformanceEvidence(BaseModel):
    """Signed record that a module passed its conformance suite (report 17.3)."""

    model_config = ConfigDict(frozen=True)

    module_ref: str
    manifest_digest: str
    suite: str
    checks: list[ConformanceCheck] = Field(default_factory=list)
    signer: str | None = None
    signature: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def signable_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"signer", "signature"})


#: A default slugify-family case set (matches ``FixtureWorker``'s task shape).
DEFAULT_WORKER_CASES: tuple[ConformanceCase, ...] = (
    ConformanceCase("plain", {"task_id": "c1", "text": "Hello World", "family": "slugify"}, {"strategy": "robust"}),
    ConformanceCase("punct", {"task_id": "c2", "text": "A, B; C!", "family": "slugify"}, {"strategy": "robust"}),
    ConformanceCase("spaces", {"task_id": "c3", "text": "x   y", "family": "slugify"}, {"strategy": "robust"}),
    ConformanceCase("empty", {"task_id": "c4", "text": "", "family": "slugify"}, {"strategy": "robust"}),
)


@dataclass
class WorkerConformanceHarness:
    """Runs the ``WorkerLike`` conformance suite and produces evidence."""

    cases: tuple[ConformanceCase, ...] = field(default_factory=lambda: DEFAULT_WORKER_CASES)

    def checks(self, worker: WorkerLike) -> list[ConformanceCheck]:
        """Run every conformance check; each returns pass/fail with detail."""
        return [
            self._check_output_shape(worker),
            self._check_determinism(worker),
            self._check_statelessness(worker),
        ]

    def evidence(
        self,
        manifest: ModuleManifest,
        worker: WorkerLike,
        *,
        signer: Any = None,
    ) -> ConformanceEvidence:
        """Run the suite and build (optionally sign) conformance evidence."""
        checks = self.checks(worker)
        evidence = ConformanceEvidence(
            module_ref=manifest.ref,
            manifest_digest=manifest.digest(),
            suite=WORKER_SUITE,
            checks=checks,
        )
        if signer is not None and evidence.passed:
            digest = content_digest(evidence.signable_payload())
            evidence = evidence.model_copy(
                update={
                    "signer": getattr(signer, "key_id", "signer"),
                    "signature": signer.sign(digest.encode("utf-8")),
                }
            )
        return evidence

    # -- individual checks ----------------------------------------------------

    def _invoke(self, worker: WorkerLike, case: ConformanceCase) -> Any:
        return worker.invoke(dict(case.task_input), dict(case.config), case.seed)

    def _check_output_shape(self, worker: WorkerLike) -> ConformanceCheck:
        for case in self.cases:
            try:
                result = self._invoke(worker, case)
            except Exception as exc:  # declared-input tolerance
                return ConformanceCheck(
                    name="output_shape",
                    passed=False,
                    detail=f"case {case.name!r} raised: {exc}",
                )
            if not isinstance(result, dict):
                return ConformanceCheck(
                    name="output_shape",
                    passed=False,
                    detail=f"case {case.name!r} returned {type(result).__name__}, not dict",
                )
        return ConformanceCheck(name="output_shape", passed=True)

    def _check_determinism(self, worker: WorkerLike) -> ConformanceCheck:
        for case in self.cases:
            try:
                first = canonical_json(self._invoke(worker, case))
                second = canonical_json(self._invoke(worker, case))
            except Exception as exc:  # a module that cannot complete cannot conform
                return ConformanceCheck(
                    name="determinism", passed=False, detail=f"case {case.name!r} raised: {exc}"
                )
            if first != second:
                return ConformanceCheck(
                    name="determinism",
                    passed=False,
                    detail=f"case {case.name!r} produced two different outputs",
                )
        return ConformanceCheck(name="determinism", passed=True)

    def _check_statelessness(self, worker: WorkerLike) -> ConformanceCheck:
        if not self.cases:
            return ConformanceCheck(name="statelessness", passed=True)
        # Baseline each case in isolation, then run them all in sequence and
        # re-check the first: a stateful worker's first answer would drift.
        try:
            baseline = {c.name: canonical_json(self._invoke(worker, c)) for c in self.cases}
            for case in self.cases:
                self._invoke(worker, case)
            replay = canonical_json(self._invoke(worker, self.cases[0]))
        except Exception as exc:
            return ConformanceCheck(name="statelessness", passed=False, detail=f"raised: {exc}")
        if replay != baseline[self.cases[0].name]:
            return ConformanceCheck(
                name="statelessness",
                passed=False,
                detail="output changed after interleaved calls (hidden state)",
            )
        return ConformanceCheck(name="statelessness", passed=True)
