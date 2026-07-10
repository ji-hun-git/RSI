"""Improvement package: read-only diagnosis and authority-free proposal
generation (report 8.3 steps 1-3, 10.4, 12.4).

The rest of the improvement loop deliberately lives elsewhere: candidate
forking in the registry (policy-checked), matched experiments in the
experiment controller, promotion in the gate, deployment and rollback in
the deployment controller. A proposer only ever produces typed data.
"""

from .diagnoser import (
    DIAGNOSER_REF,
    Diagnosis,
    EvidenceDiagnoser,
    record_mission_evaluation,
)
from .proposer import (
    ProposalConstraints,
    ProposalPolicyViolation,
    ProposerLike,
    RejectedDiff,
    TemplateMutationProposer,
    diff_digest,
    path_within,
)

__all__ = [
    "DIAGNOSER_REF",
    "Diagnosis",
    "EvidenceDiagnoser",
    "ProposalConstraints",
    "ProposalPolicyViolation",
    "ProposerLike",
    "RejectedDiff",
    "TemplateMutationProposer",
    "diff_digest",
    "path_within",
    "record_mission_evaluation",
]
