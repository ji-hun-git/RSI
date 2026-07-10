"""Evaluation package: deterministic oracle, executable-test service and
metric-vector harness.

Report sections 10.2, 13.2, 13.5, 14.4, 17.4.
"""

from .harness import EvaluationHarness
from .oracle import DeterministicOracle, exact_match
from .test_service import CommandReceipt, DeterministicTestService, TestReport

__all__ = [
    "CommandReceipt",
    "DeterministicOracle",
    "DeterministicTestService",
    "EvaluationHarness",
    "TestReport",
    "exact_match",
]
