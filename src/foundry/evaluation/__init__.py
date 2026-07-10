"""Evaluation package: deterministic oracle and metric-vector harness.

Report sections 13.2, 13.5, 17.4.
"""

from .harness import EvaluationHarness
from .oracle import DeterministicOracle, exact_match

__all__ = [
    "DeterministicOracle",
    "EvaluationHarness",
    "exact_match",
]
