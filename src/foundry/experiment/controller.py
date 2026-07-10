"""Experiment controller: matched, paired, budget-equalized experiments.

Implements the deterministic Experiment Controller of report section 10.4
("Matched run matrix and ExperimentRecord ... no production mutation;
blind holdout handles") following the BOUNDED_RSI design step of section
12.2: the control arm is always present, candidate lineage is validated
against the parent bundle, budgets are equalized, task order and per-task
seeds are identical across arms (section 13.4), and protected holdout
tasks are only reachable through blind vault handles (section 14.1).
"""

from __future__ import annotations

import hashlib
import platform
import statistics
import string
from collections.abc import Callable
from typing import Any

from foundry.contracts import (
    Event,
    EventTypes,
    ExperimentArm,
    ExperimentBudget,
    ExperimentRecord,
    ImprovementProposal,
    LedgerLike,
    PairedAnalysis,
    Randomization,
    SystemBundle,
    TaskSetRefs,
    TaskSetRole,
    Usage,
)

from .analysis import summarize
from .vault import VAULT_REF_PREFIX, HoldoutVault

RunArm = Callable[[SystemBundle, Any, int], str]
Score = Callable[[Any, str], float]

ArmScores = dict[TaskSetRole, dict[str, float]]


def derive_seed(base_seed: int, label: str) -> int:
    """Deterministic 64-bit seed derived from the experiment seed and a label.

    Wall-clock free and platform independent, so every arm replays a task
    with exactly the same seed (report 13.4 "repeated seeds").
    """
    material = f"{base_seed}:{label}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _arm_label(index: int) -> str:
    """Bijective base-26 arm label: 0 -> candidate_a, 26 -> candidate_aa."""
    letters = ""
    i = index
    while True:
        i, rem = divmod(i, 26)
        letters = string.ascii_lowercase[rem] + letters
        if i == 0:
            break
        i -= 1
    return f"candidate_{letters}"


class ExperimentController:
    """Designs, runs and analyzes paired control-vs-candidate experiments."""

    def __init__(self, ledger: LedgerLike, vault: HoldoutVault | None = None) -> None:
        self._ledger = ledger
        self._vault = vault

    def design(
        self,
        proposal: ImprovementProposal,
        control_bundle: SystemBundle,
        candidate_bundles: list[SystemBundle],
        task_set_refs: TaskSetRefs,
        budgets: ExperimentBudget,
        seed: int,
        minimum_practical_effect: float = 0.0,
    ) -> ExperimentRecord:
        """Design a matched experiment: control arm always included (12.2)."""
        if not candidate_bundles:
            raise ValueError("an experiment requires at least one candidate arm")
        if not budgets.equalized:
            raise ValueError("experiment budgets must be equalized across arms (report 13.4)")
        if proposal.parent_bundle_id != control_bundle.bundle_id:
            raise ValueError(
                f"proposal parent {proposal.parent_bundle_id!r} does not match "
                f"control bundle {control_bundle.bundle_id!r}"
            )
        for candidate in candidate_bundles:
            if candidate.parent_bundle_id != control_bundle.bundle_id:
                raise ValueError(
                    f"candidate {candidate.bundle_id!r} has parent "
                    f"{candidate.parent_bundle_id!r}, not the control bundle "
                    f"{control_bundle.bundle_id!r}; lineage must be matched"
                )
        arms = [ExperimentArm(arm_id="control", bundle_id=control_bundle.bundle_id, is_control=True)]
        arms += [
            ExperimentArm(arm_id=_arm_label(i), bundle_id=candidate.bundle_id)
            for i, candidate in enumerate(candidate_bundles)
        ]
        record = ExperimentRecord(
            proposal_id=proposal.proposal_id,
            arms=arms,
            task_sets=task_set_refs,
            randomization=Randomization(unit="task", paired=True, seed=seed),
            budgets=budgets,
            minimum_practical_effect=minimum_practical_effect,
        )
        self._ledger.append(
            Event(
                event_type=EventTypes.EXPERIMENT_DESIGNED,
                experiment_id=record.experiment_id,
                subject=proposal.proposal_id,
                payload={
                    "proposal_id": proposal.proposal_id,
                    "arms": [arm.model_dump(mode="json") for arm in arms],
                    "task_sets": task_set_refs.model_dump(mode="json"),
                    "budgets": budgets.model_dump(mode="json"),
                    "minimum_practical_effect": minimum_practical_effect,
                },
            )
        )
        self._ledger.append(
            Event(
                event_type=EventTypes.EXPERIMENT_RANDOMIZED,
                experiment_id=record.experiment_id,
                payload=record.randomization.model_dump(mode="json"),
            )
        )
        return record

    def run(
        self,
        record: ExperimentRecord,
        bundles: dict[str, SystemBundle],
        tasks_by_role: dict[TaskSetRole, list[Any]],
        run_arm: RunArm,
        score: Score,
    ) -> dict[str, ArmScores]:
        """Run every arm over the same tasks, order and per-task seeds (13.4).

        Protected holdout tasks are never accepted here in the clear: they
        are executed only through :meth:`HoldoutVault.run_blind` -- the arm
        sees a redacted view, scoring happens inside the vault with the
        scorer fixed at seal time -- and their scores are keyed by blind
        handle, not task id (report 14.1). The ``score`` callable applies
        to open roles only.
        """
        if TaskSetRole.PROTECTED_HOLDOUT in tasks_by_role:
            raise ValueError(
                "protected holdout tasks must stay in the vault; "
                "run() only accepts them via the record's blind vault ref (report 14.1)"
            )
        for arm in record.arms:
            if bundles[arm.arm_id].bundle_id != arm.bundle_id:
                raise ValueError(
                    f"bundle supplied for arm {arm.arm_id!r} does not match the "
                    f"designed bundle_id {arm.bundle_id!r}"
                )
        protected = self._protected_vault(record)
        base_seed = record.randomization.seed
        results: dict[str, ArmScores] = {}
        for arm in record.arms:
            bundle = bundles[arm.arm_id]
            self._ledger.append(
                Event(
                    event_type=EventTypes.ARM_STARTED,
                    experiment_id=record.experiment_id,
                    arm_id=arm.arm_id,
                    system_bundle_id=arm.bundle_id,
                    payload={"is_control": arm.is_control},
                )
            )
            arm_scores: ArmScores = {}
            for role in TaskSetRole:
                if role is TaskSetRole.PROTECTED_HOLDOUT:
                    if protected is None:
                        continue
                    name, vault = protected
                    scores = self._run_protected(vault, name, bundle, base_seed, run_arm)
                elif role in tasks_by_role:
                    scores = self._run_open(tasks_by_role[role], bundle, base_seed, run_arm, score)
                else:
                    continue
                arm_scores[role] = scores
                self._ledger.append(
                    Event(
                        event_type=EventTypes.METRIC_COMPUTED,
                        experiment_id=record.experiment_id,
                        arm_id=arm.arm_id,
                        system_bundle_id=arm.bundle_id,
                        payload={
                            "metric": "mean_score",
                            "role": role.value,
                            "value": statistics.fmean(scores.values()) if scores else 0.0,
                            "n_tasks": len(scores),
                        },
                    )
                )
            self._ledger.append(
                Event(
                    event_type=EventTypes.ARM_COMPLETED,
                    experiment_id=record.experiment_id,
                    arm_id=arm.arm_id,
                    system_bundle_id=arm.bundle_id,
                    usage=Usage(),
                    payload={
                        "runs": sum(len(s) for s in arm_scores.values()),
                        "tasks_per_role": {role.value: len(s) for role, s in arm_scores.items()},
                    },
                )
            )
            results[arm.arm_id] = arm_scores
        return results

    def analyze(
        self,
        record: ExperimentRecord,
        results: dict[str, ArmScores],
        seed: int,
    ) -> dict[str, dict[TaskSetRole, PairedAnalysis]]:
        """Paired candidate-vs-control analyses per (arm, role) (report 13.4)."""
        control_arm = next(arm for arm in record.arms if arm.is_control)
        control_scores = results[control_arm.arm_id]
        analyses: dict[str, dict[TaskSetRole, PairedAnalysis]] = {}
        summary: dict[str, Any] = {}
        for arm in record.arms:
            if arm.is_control:
                continue
            per_role: dict[TaskSetRole, PairedAnalysis] = {}
            for role, candidate_scores in results[arm.arm_id].items():
                if not candidate_scores:
                    continue
                per_role[role] = summarize(
                    record.experiment_id,
                    arm.arm_id,
                    role,
                    control_scores[role],
                    candidate_scores,
                    seed=derive_seed(seed, f"{arm.arm_id}:{role.value}"),
                )
            analyses[arm.arm_id] = per_role
            summary[arm.arm_id] = {
                role.value: {
                    "n_pairs": analysis.n_pairs,
                    "mean_delta": analysis.mean_delta,
                    "ci": [analysis.ci_low, analysis.ci_high],
                    "wins": analysis.wins,
                    "losses": analysis.losses,
                    "ties": analysis.ties,
                }
                for role, analysis in per_role.items()
            }
        self._ledger.append(
            Event(
                event_type=EventTypes.EXPERIMENT_ANALYZED,
                experiment_id=record.experiment_id,
                payload={
                    "seed": seed,
                    "minimum_practical_effect": record.minimum_practical_effect,
                    "python_version": platform.python_version(),
                    "arms": summary,
                },
            )
        )
        return analyses

    def check_leakage(
        self,
        record: ExperimentRecord,
        proposal: ImprovementProposal,
        extra_texts: list[str] | None = None,
    ) -> list[str]:
        """Check proposal text/evidence for verbatim protected task content.

        Returns the leaking blind handles and emits LEAKAGE_DETECTED when
        any exist (report 10.4 failure mode "leakage").
        """
        protected = self._protected_vault(record)
        if protected is None:
            return []
        name, vault = protected
        texts = [
            proposal.hypothesis,
            proposal.current_behavior,
            *proposal.secondary_hypotheses,
            *proposal.evidence_refs,
            *(extra_texts or []),
        ]
        hits = vault.leakage_check(name, [text for text in texts if text])
        if hits:
            self._ledger.append(
                Event(
                    event_type=EventTypes.LEAKAGE_DETECTED,
                    experiment_id=record.experiment_id,
                    subject=proposal.proposal_id,
                    payload={
                        "proposal_id": proposal.proposal_id,
                        "handles": hits,
                        "n_hits": len(hits),
                    },
                )
            )
        return hits

    def _protected_vault(self, record: ExperimentRecord) -> tuple[str, HoldoutVault] | None:
        ref = record.task_sets.protected
        if ref is None:
            return None
        if not ref.startswith(VAULT_REF_PREFIX):
            raise ValueError(f"protected task set ref {ref!r} is not a holdout vault ref")
        if self._vault is None:
            raise ValueError("experiment has a protected task set but the controller has no vault")
        return ref[len(VAULT_REF_PREFIX):], self._vault

    def _run_open(
        self,
        tasks: list[Any],
        bundle: SystemBundle,
        base_seed: int,
        run_arm: RunArm,
        score: Score,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for task in tasks:
            task_seed = derive_seed(base_seed, task.task_id)
            scores[task.task_id] = score(task, run_arm(bundle, task, task_seed))
        return scores

    def _run_protected(
        self,
        vault: HoldoutVault,
        name: str,
        bundle: SystemBundle,
        base_seed: int,
        run_arm: RunArm,
    ) -> dict[str, float]:
        """Execute one arm over the vault: redacted views in, floats out.

        The candidate callable only ever sees a ``BlindTaskView`` (the
        blind handle stands in for the task id, so the per-task seed is
        derived from it); scoring happens inside the vault against the
        sealed ground truth (report 14.1).
        """

        def run_view(view: Any) -> str:
            return run_arm(bundle, view, derive_seed(base_seed, view.task_id))

        return {
            handle: vault.run_blind(name, handle, run_view)
            for handle in vault.handles(name)
        }
