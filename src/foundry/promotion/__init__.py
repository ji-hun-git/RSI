"""Promotion package: the G0-G9 gates and the fail-closed gate runner.

Report sections 13.1, 13.3, 14.5; no-self-approval invariant from 8.1.
"""

from .gate_runner import (
    DecisionSignerLike,
    DecisionVerifierLike,
    PromotionGate,
    sign_decision,
    verify_decision_signature,
)
from .gates import (
    g0_integrity,
    g1_static,
    g2_dev_replay,
    g3_holdout,
    g4_retention,
    g5_adversarial,
    g6_resource,
    g7_reproducibility,
    g8_human,
    g9_canary,
    required_approval_tier,
    tier_meets,
)

__all__ = [
    "DecisionSignerLike",
    "DecisionVerifierLike",
    "PromotionGate",
    "g0_integrity",
    "g1_static",
    "g2_dev_replay",
    "g3_holdout",
    "g4_retention",
    "g5_adversarial",
    "g6_resource",
    "g7_reproducibility",
    "g8_human",
    "g9_canary",
    "required_approval_tier",
    "sign_decision",
    "tier_meets",
    "verify_decision_signature",
]
