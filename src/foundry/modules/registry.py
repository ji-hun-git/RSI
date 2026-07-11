"""Module registry: conformance-gated admission and resolution (report 17.2).

Distinct from the bundle registry (which stores content-addressed
configuration bundles), this is a runtime registry of *implementations*
admitted behind their manifests. Its one job is the report 17.3 admission
rule made mechanical: a module is registered only when it passes its
conformance suite, and its (optionally signed) conformance evidence is
retained so any later question of "was this admitted honestly?" resolves
to a record, not a memory. Quarantine is the default: a non-conformant
module is refused, never silently accepted.

A ``SystemBundle`` pins modules by ``module_id@version`` in its
``module_refs``; :meth:`ModuleRegistry.resolve` turns such a ref into the
admitted implementation, so a bundle's declared worker slot is bound to a
module that has actually demonstrated its contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from foundry.contracts import ModuleManifest, WorkerLike

from .conformance import ConformanceEvidence, WorkerConformanceHarness


class ModuleConformanceError(Exception):
    """A module failed conformance and is refused admission (report 17.3)."""


@dataclass(frozen=True)
class RegisteredModule:
    manifest: ModuleManifest
    implementation: Any
    evidence: ConformanceEvidence


class ModuleRegistry:
    """Admits and resolves modules that have passed their conformance suite."""

    def __init__(
        self,
        harness: WorkerConformanceHarness | None = None,
        *,
        signer: Any = None,
    ) -> None:
        self._harness = harness or WorkerConformanceHarness()
        self._signer = signer
        self._modules: dict[str, RegisteredModule] = {}

    def register(
        self, manifest: ModuleManifest, worker: WorkerLike
    ) -> ConformanceEvidence:
        """Admit *worker* under *manifest*, gated on passing conformance.

        Raises :class:`ModuleConformanceError` (quarantine-by-default) if
        any conformance check fails; the failing evidence is included so the
        caller can see exactly which contract semantics were violated.
        """
        evidence = self._harness.evidence(manifest, worker, signer=self._signer)
        if not evidence.passed:
            failures = ", ".join(c.name for c in evidence.checks if not c.passed)
            raise ModuleConformanceError(
                f"module {manifest.ref} failed conformance ({failures}); refused admission"
            )
        ref = manifest.ref
        existing = self._modules.get(ref)
        if existing is not None and existing.manifest.digest() != manifest.digest():
            raise ModuleConformanceError(
                f"module ref {ref} is already registered with a different manifest "
                "digest; versions are immutable"
            )
        self._modules[ref] = RegisteredModule(manifest, worker, evidence)
        return evidence

    def resolve(self, ref: str) -> Any:
        """Return the admitted implementation for ``module_id@version``."""
        if ref not in self._modules:
            raise KeyError(f"module {ref!r} is not registered")
        return self._modules[ref].implementation

    def evidence(self, ref: str) -> ConformanceEvidence:
        return self._require(ref).evidence

    def manifest(self, ref: str) -> ModuleManifest:
        return self._require(ref).manifest

    def list_refs(self) -> list[str]:
        return sorted(self._modules)

    def verify_evidence(self, ref: str, verifier: Any) -> bool:
        """Verify the stored conformance signature against *verifier*.

        Returns False when the evidence is unsigned or the signature does
        not verify; a missing signature is reported as its own outcome, not
        as forgery (the same discipline as bundle/event verification).
        """
        from foundry.contracts import content_digest

        evidence = self._require(ref).evidence
        if evidence.signature is None:
            return False
        digest = content_digest(evidence.signable_payload())
        return verifier.verify(digest.encode("utf-8"), evidence.signature)

    def _require(self, ref: str) -> RegisteredModule:
        if ref not in self._modules:
            raise KeyError(f"module {ref!r} is not registered")
        return self._modules[ref]
