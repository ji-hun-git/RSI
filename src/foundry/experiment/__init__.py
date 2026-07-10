"""Experiment package: matched paired experiments over blind holdouts.

Implements the deterministic Experiment Controller (report section 10.4),
the protected holdout vault (14.1) and paired bootstrap statistical
analysis (13.4) over the frozen ExperimentRecord contracts (17.4).
"""

from .analysis import bootstrap_ci, paired_deltas, summarize
from .controller import ExperimentController, RunArm, Score, derive_seed
from .vault import (
    HANDLE_PREFIX,
    VAULT_REF_PREFIX,
    BlindRunner,
    BlindTaskView,
    HoldoutVault,
    Scorer,
    TaskLike,
)

__all__ = [
    "HANDLE_PREFIX",
    "VAULT_REF_PREFIX",
    "BlindRunner",
    "BlindTaskView",
    "ExperimentController",
    "HoldoutVault",
    "RunArm",
    "Score",
    "Scorer",
    "TaskLike",
    "bootstrap_ci",
    "derive_seed",
    "paired_deltas",
    "summarize",
]
