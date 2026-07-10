"""Deterministic exact-match oracle (report sections 13.5, 17.4).

A deterministic oracle is the highest-objectivity evaluator type in the
triangulation table (13.5): given the same (expected, actual) pair it
always produces the same score, so its results are admissible evidence
for paired comparison without judge-variance corrections. Stage 1 ships
exact string match; richer oracles (tests, schemas, simulation
invariants) plug in behind the same ``EvaluationResult`` contract.

Every result carries the 17.4 integrity block: the digest is always
filled, and when the oracle holds a signer the digest is signed, so
evaluation records are individually tamper-evident (report 17.5).
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from foundry.contracts import EvaluationResult, ModuleRef, ResultIntegrity


@runtime_checkable
class ResultSignerLike(Protocol):
    """Duck type for the optional evaluation-result signer."""

    @property
    def key_id(self) -> str: ...

    def sign(self, data: bytes) -> str: ...


def exact_match(expected: str, actual: str) -> float:
    """Score callable for experiments: 1.0 on exact string match, else 0.0."""
    return 1.0 if expected == actual else 0.0


class DeterministicOracle:
    """Exact-match oracle producing contract-conformant evaluation results.

    Evaluator identity is mandatory on every result (report 17.4); this
    oracle pins its own ``ModuleRef`` so downstream analysis can attribute
    and, if needed, revoke its claims.
    """

    evaluator: ClassVar[ModuleRef] = ModuleRef(id="eval.exact_match", version="1.0.0")

    def __init__(self, signer: ResultSignerLike | None = None) -> None:
        self._signer = signer

    def score(
        self,
        task_id: str,
        expected: str,
        actual: str,
        *,
        subject_run_id: str,
        bundle_id: str | None = None,
        dataset_item_handle: str | None = None,
    ) -> EvaluationResult:
        """Score one task output: metric ``task_success``, value 1.0 or 0.0."""
        value = exact_match(expected, actual)
        result = EvaluationResult(
            subject_run_id=subject_run_id,
            subject_bundle_id=bundle_id,
            evaluator=self.evaluator,
            dataset_item_handle=dataset_item_handle,
            metric="task_success",
            value=value,
            detail={"task_id": task_id, "match": value == 1.0},
        )
        digest = result.digest()
        integrity = ResultIntegrity(
            digest=digest,
            signature=self._signer.sign(digest.encode("utf-8")) if self._signer else None,
            signer=self._signer.key_id if self._signer else None,
        )
        return result.with_integrity(integrity)
