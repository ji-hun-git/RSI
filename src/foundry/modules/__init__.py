"""Module conformance and hot-swap (report sections 17.2, 17.3).

The LEGO-connector layer: a module is admitted to the registry only after
its conformance suite demonstrates the semantics its slot requires, and a
replacement is accepted only after shadow execution shows the new module
agrees with the old. Conformance evidence is the connector, not the type
signature alone.

    from foundry.modules import ModuleRegistry, WorkerConformanceHarness, check_replacement
"""

from .conformance import (
    DEFAULT_WORKER_CASES,
    WORKER_SUITE,
    ConformanceCase,
    ConformanceCheck,
    ConformanceEvidence,
    WorkerConformanceHarness,
)
from .registry import ModuleConformanceError, ModuleRegistry, RegisteredModule
from .runtime import ModuleResolvingRuntime
from .swap import Divergence, ReplacementReport, check_replacement, resolve_worker

__all__ = [
    "DEFAULT_WORKER_CASES",
    "WORKER_SUITE",
    "ConformanceCase",
    "ConformanceCheck",
    "ConformanceEvidence",
    "Divergence",
    "ModuleConformanceError",
    "ModuleRegistry",
    "ModuleResolvingRuntime",
    "RegisteredModule",
    "ReplacementReport",
    "WorkerConformanceHarness",
    "check_replacement",
    "resolve_worker",
]
