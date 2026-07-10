"""Paired statistical analysis for candidate-vs-control arms (report 13.4).

Pairing is mandatory: deltas are computed per task over identical task
sets ("use paired tasks ... so candidate-control differences have lower
variance"), and uncertainty is a paired percentile-bootstrap interval
("use paired bootstrap intervals ... do not rely only on a global mean")
driven by an explicit seed so every analysis is reproducible bit-for-bit.
The bootstrap resamples the delta vector in a canonical (value-sorted)
order, so the recorded interval is reproducible from the scores and the
seed alone, independent of dictionary key naming -- in particular of the
secret-keyed blind handles of the protected holdout (report 22.2).
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping

from foundry.contracts import PairedAnalysis, TaskSetRole


def paired_deltas(
    scores_a: Mapping[str, float], scores_b: Mapping[str, float]
) -> dict[str, float]:
    """Per-task ``b - a`` deltas over the shared task ids, sorted by task id.

    Raises ``ValueError`` when the task sets differ: unpaired scores are not
    admissible evidence (report 13.4).
    """
    if scores_a.keys() != scores_b.keys():
        only_a = sorted(scores_a.keys() - scores_b.keys())
        only_b = sorted(scores_b.keys() - scores_a.keys())
        raise ValueError(
            "paired analysis requires identical task sets; "
            f"only in a: {only_a}; only in b: {only_b}"
        )
    return {task_id: scores_b[task_id] - scores_a[task_id] for task_id in sorted(scores_a)}


def bootstrap_ci(
    deltas: list[float], n_boot: int = 2000, alpha: float = 0.05, *, seed: int
) -> tuple[float, float]:
    """Percentile-bootstrap CI for the mean delta, deterministic in *seed*.

    The delta vector is put in a canonical (sorted) order before
    resampling, so the interval is a pure function of the delta *values*
    and the seed -- never of how the score dictionaries happened to be
    keyed (e.g. by secret-dependent blind handles). Resampling indices
    are derived directly from ``random.Random.random()``, the only
    generator method with a cross-version stability guarantee.
    """
    if not deltas:
        raise ValueError("bootstrap_ci requires at least one delta")
    rng = random.Random(seed)
    ordered = sorted(deltas)
    n = len(ordered)
    means = sorted(
        statistics.fmean(ordered[int(rng.random() * n)] for _ in range(n))
        for _ in range(n_boot)
    )
    low_index = math.floor((alpha / 2.0) * n_boot)
    high_index = math.ceil((1.0 - alpha / 2.0) * n_boot) - 1
    return means[low_index], means[high_index]


def summarize(
    experiment_id: str,
    arm_id: str,
    role: TaskSetRole,
    control_scores: Mapping[str, float],
    candidate_scores: Mapping[str, float],
    seed: int,
    n_boot: int = 2000,
    alpha: float = 0.05,
) -> PairedAnalysis:
    """Paired candidate-vs-control summary on one task set (report 13.4)."""
    deltas = paired_deltas(control_scores, candidate_scores)
    values = list(deltas.values())
    ci_low, ci_high = bootstrap_ci(values, n_boot=n_boot, alpha=alpha, seed=seed)
    wins = sum(1 for d in values if d > 0)
    losses = sum(1 for d in values if d < 0)
    return PairedAnalysis(
        experiment_id=experiment_id,
        arm_id=arm_id,
        task_set_role=role,
        n_pairs=len(values),
        mean_delta=statistics.fmean(values),
        ci_low=ci_low,
        ci_high=ci_high,
        wins=wins,
        losses=losses,
        ties=len(values) - wins - losses,
        per_task_deltas=deltas,
        detail={"n_boot": n_boot, "alpha": alpha, "seed": seed},
    )
