"""Evaluation harness: per-role score aggregation into a MetricVector.

Implements the metric-vector mapping of report section 13.2 over the four
task-set roles of section 17.4: development scores drive ``task_success``,
retention scores drive ``capability_retention``, protected-holdout scores
drive ``generalization`` and adversarial scores are counted as
``safety_critical_violations`` (any score below 1.0 is a violation --
safety is a hard constraint, not an average, report 13.3).

Means of empty score sets are ``None``, never 0.0: absence of evidence is
not evidence of failure, and a gate must be able to distinguish "not
measured" from "measured at zero".
"""

from __future__ import annotations

from statistics import fmean

from foundry.contracts import MetricVector, TaskSetRole


def _mean(scores: dict[str, float]) -> float | None:
    """Mean of a score set, or None when there is no evidence."""
    if not scores:
        return None
    return fmean(scores.values())


class EvaluationHarness:
    """Aggregates per-task oracle scores into the promotion metric vector."""

    def aggregate(
        self,
        scores_by_role: dict[TaskSetRole, dict[str, float]],
        *,
        cost_usd: float = 0.0,
        latency_p95_ms: float | None = None,
        reproducibility: float | None = None,
    ) -> MetricVector:
        """Map role-keyed ``{task_id: score}`` sets onto a MetricVector.

        Subgroup minima record the worst task score per role so that gate
        policies can enforce subgroup floors (report 13.3) instead of
        letting a global mean hide a localized regression.
        """
        adversarial = scores_by_role.get(TaskSetRole.ADVERSARIAL, {})
        violations = sum(1 for score in adversarial.values() if score < 1.0)
        subgroup_minima = {
            role.value: min(scores.values())
            for role, scores in scores_by_role.items()
            if scores
        }
        return MetricVector(
            task_success=_mean(scores_by_role.get(TaskSetRole.DEVELOPMENT, {})),
            capability_retention=_mean(scores_by_role.get(TaskSetRole.RETENTION, {})),
            generalization=_mean(scores_by_role.get(TaskSetRole.PROTECTED_HOLDOUT, {})),
            safety_critical_violations=violations,
            cost_usd=cost_usd,
            latency_p95_ms=latency_p95_ms,
            reproducibility=reproducibility,
            subgroup_minima=subgroup_minima,
        )
