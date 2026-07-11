"""Module conformance, admission and hot-swap (report sections 17.2, 17.3).

The load-bearing cases: conformance is the connector (a module is admitted
only after demonstrating determinism, statelessness and output shape),
seeded incompatibilities are detected and refused, evidence is signed and
verifiable, and a replacement is accepted only when shadow execution shows
byte-identical behavior -- a same-interface behavior change is reported,
never silently coerced.
"""

from __future__ import annotations

from typing import Any

import pytest

from foundry.contracts import ModuleManifest, ModuleType, SystemBundle
from foundry.modules import (
    ConformanceCase,
    ModuleConformanceError,
    ModuleRegistry,
    WorkerConformanceHarness,
    check_replacement,
    resolve_worker,
)
from foundry.registry import HMACSigner
from foundry.runtime import FIXTURE_WORKFLOW_REF
from foundry.workers import FixtureWorker, naive_slugify, robust_slugify

# -- test workers: one conformant family, several seeded incompatibilities ----


class RobustWorker:
    """Conformant: pure robust slugify."""

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        return {"output": robust_slugify(task_input["text"])}


class RobustWorkerAlt:
    """Conformant and behaviorally identical to RobustWorker (a genuine drop-in)."""

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        text = task_input["text"]
        return {"output": robust_slugify(str(text))}  # different code path, same result


class NaiveWorker:
    """Conformant but behaviorally different (a behavior change, same interface)."""

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        return {"output": naive_slugify(task_input["text"])}


class NondeterministicWorker:
    """Seeded incompatibility: output depends on hidden call count."""

    def __init__(self) -> None:
        self._n = 0

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        self._n += 1
        return {"output": robust_slugify(task_input["text"]), "call": self._n}


class StatefulWorker:
    """Seeded incompatibility: accumulates state across calls."""

    def __init__(self) -> None:
        self._seen: list[str] = []

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        self._seen.append(task_input["text"])
        return {"output": robust_slugify(task_input["text"]), "history_len": len(self._seen)}


class BadShapeWorker:
    """Seeded incompatibility: violates the dict-output contract."""

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> Any:
        return robust_slugify(task_input["text"])  # a str, not a dict


class CrashingWorker:
    """Seeded incompatibility: raises on a valid declared input (empty text)."""

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        if not task_input["text"]:
            raise ValueError("cannot handle empty input")
        return {"output": robust_slugify(task_input["text"])}


def manifest(module_id: str, version: str = "1.0.0", **extra: Any) -> ModuleManifest:
    return ModuleManifest(module_id=module_id, module_type=ModuleType.AGENT, version=version, **extra)


@pytest.fixture()
def registry() -> ModuleRegistry:
    return ModuleRegistry()


# -- conformance admits and refuses -------------------------------------------


def test_conformant_worker_is_admitted_and_resolves(registry: ModuleRegistry) -> None:
    evidence = registry.register(manifest("worker.robust"), RobustWorker())
    assert evidence.passed
    assert {c.name for c in evidence.checks} == {"output_shape", "determinism", "statelessness"}
    resolved = registry.resolve("worker.robust@1.0.0")
    assert isinstance(resolved, RobustWorker)
    assert registry.list_refs() == ["worker.robust@1.0.0"]


def test_fixture_worker_conforms(registry: ModuleRegistry) -> None:
    # the real production worker passes its own conformance suite
    evidence = registry.register(manifest("worker.fixture"), FixtureWorker())
    assert evidence.passed


@pytest.mark.parametrize(
    "worker_factory,failing_check",
    [
        (NondeterministicWorker, "determinism"),
        (StatefulWorker, "statelessness"),
        (BadShapeWorker, "output_shape"),
        (CrashingWorker, "output_shape"),
    ],
)
def test_seeded_incompatibility_is_detected_and_refused(
    registry: ModuleRegistry, worker_factory, failing_check: str
) -> None:
    with pytest.raises(ModuleConformanceError) as exc:
        registry.register(manifest("worker.bad"), worker_factory())
    assert "refused admission" in str(exc.value)
    # the module is not admitted
    assert "worker.bad@1.0.0" not in registry.list_refs()
    # and the harness pinpoints the violated semantics
    checks = {c.name: c for c in WorkerConformanceHarness().checks(worker_factory())}
    assert not checks[failing_check].passed


def test_registering_a_ref_with_a_different_manifest_is_refused(registry: ModuleRegistry) -> None:
    registry.register(manifest("worker.robust", purpose="v1"), RobustWorker())
    with pytest.raises(ModuleConformanceError, match="immutable"):
        registry.register(manifest("worker.robust", purpose="v2-different"), RobustWorker())


# -- signed conformance evidence ----------------------------------------------


def test_conformance_evidence_is_signed_and_verifiable() -> None:
    signer = HMACSigner("modtest", b"0" * 32)
    registry = ModuleRegistry(signer=signer)
    registry.register(manifest("worker.robust"), RobustWorker())
    assert registry.verify_evidence("worker.robust@1.0.0", signer) is True
    # a wrong key does not verify; an unsigned registry's evidence does not verify
    assert registry.verify_evidence("worker.robust@1.0.0", HMACSigner("other", b"1" * 32)) is False
    unsigned = ModuleRegistry()
    unsigned.register(manifest("worker.robust"), RobustWorker())
    assert unsigned.verify_evidence("worker.robust@1.0.0", signer) is False


# -- hot-swap via shadow execution (report 17.3) ------------------------------


def test_identical_behavior_is_a_compatible_swap() -> None:
    report = check_replacement(RobustWorker(), RobustWorkerAlt())
    assert report.compatible
    assert report.schema_compatible and report.semantic_compatible
    assert report.divergences == ()


def test_behavior_change_is_reported_case_by_case_not_coerced() -> None:
    report = check_replacement(RobustWorker(), NaiveWorker())
    assert not report.compatible
    assert report.schema_compatible  # both honor the dict contract...
    assert not report.semantic_compatible  # ...but their outputs diverge
    diverged = {d.case for d in report.divergences}
    # naive and robust agree on the simple/empty cases, differ on punctuation/spaces
    assert "punct" in diverged and "spaces" in diverged
    assert "empty" not in diverged


def test_replacement_crash_fails_closed() -> None:
    report = check_replacement(RobustWorker(), CrashingWorker())
    assert not report.compatible
    assert report.error is not None


def test_custom_cases_drive_the_comparison() -> None:
    cases = (ConformanceCase("only", {"text": "Hello  World", "task_id": "x"}, {}),)
    same = check_replacement(RobustWorker(), RobustWorkerAlt(), cases)
    assert same.compatible
    diff = check_replacement(RobustWorker(), NaiveWorker(), cases)
    assert not diff.compatible


# -- resolving a bundle's declared module -------------------------------------


def test_bundle_worker_slot_resolves_through_the_registry(registry: ModuleRegistry) -> None:
    registry.register(manifest("worker.robust"), RobustWorker())
    bundle = SystemBundle(
        workflow_ref=FIXTURE_WORKFLOW_REF,
        config={"strategy": "robust"},
        module_refs={"worker": "worker.robust@1.0.0"},
    )
    worker = resolve_worker(bundle, registry)
    assert isinstance(worker, RobustWorker)
    # a slot the bundle does not declare is an explicit error, not a silent None
    with pytest.raises(KeyError):
        resolve_worker(bundle, registry, slot="planner")


def test_resolving_an_unregistered_module_raises(registry: ModuleRegistry) -> None:
    with pytest.raises(KeyError, match="not registered"):
        registry.resolve("worker.ghost@9.9.9")
