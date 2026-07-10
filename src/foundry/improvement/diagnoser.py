"""EvidenceDiagnoser: read-only failure diagnosis over the mission cohort
(report 8.3 improvement loop step 1, 10.4 Process Diagnoser).

The diagnoser is deterministic and strictly read-only: it consumes
canonical events, groups outcome failures into repeatable signatures and
emits typed :class:`Diagnosis` objects with the supporting evidence ids.
It cannot alter memory, policy, bundles or anything else -- a diagnosis
is an input to the proposer, never an action.

Evidence contract. A mission cohort is diagnosable when the ledger holds,
per mission: a MISSION_STARTED event (whose payload carries the frozen
bundle, giving the configuration under which the failure occurred) and
one or more METRIC_COMPUTED events with payload
``{"metric", "value", "task_family", "difficulty"}`` correlated by
``mission_id``. :func:`record_mission_evaluation` is the writer half of
that contract, used by whoever scores missions (report 15.2 evaluation
family).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from foundry.contracts import Event, EventTypes, LedgerLike, ModuleRef, new_id

DIAGNOSER_REF = ModuleRef(id="diagnoser.failure-signature", version="1.0.0")


def record_mission_evaluation(
    ledger: LedgerLike,
    *,
    mission_id: str,
    bundle_id: str,
    metric: str,
    value: float,
    task_family: str,
    difficulty: str = "",
    evaluator: ModuleRef | None = None,
) -> Event:
    """Ledger one mission-level evaluation observation (the evidence the
    diagnoser reads). Emitted by evaluators, never by the diagnoser itself."""
    return ledger.append(
        Event(
            event_type=EventTypes.METRIC_COMPUTED,
            mission_id=mission_id,
            system_bundle_id=bundle_id,
            module=evaluator,
            actor=(evaluator or DIAGNOSER_REF).id,
            payload={
                "metric": metric,
                "value": value,
                "task_family": task_family,
                "difficulty": difficulty,
            },
        )
    )


@dataclass(frozen=True)
class Diagnosis:
    """One repeatable failure signature with its supporting evidence.

    ``config`` is the (identical) bundle config observed across the
    failing missions; a signature that spans conflicting configurations
    is split, because a causal hypothesis needs a fixed antecedent.
    """

    diagnosis_id: str
    failure_signature: str  # e.g. "task_success<1.0 on slugify/hard"
    metric: str
    task_family: str
    difficulty: str
    bundle_id: str
    config: dict[str, Any]
    n_failures: int
    n_observations: int
    evidence_event_ids: tuple[str, ...] = ()

    @property
    def failure_rate(self) -> float:
        return self.n_failures / self.n_observations if self.n_observations else 0.0


class EvidenceDiagnoser:
    """Groups mission-level metric failures into typed diagnoses."""

    def __init__(self, ledger: LedgerLike, *, min_support: int = 3) -> None:
        self._ledger = ledger
        self._min_support = min_support

    def diagnose(self, *, metric: str = "task_success", threshold: float = 1.0) -> list[Diagnosis]:
        """Diagnoses for every (bundle, family, difficulty) group whose
        failure count (value < *threshold*) meets the support minimum.

        Read-only by construction: the only ledger interaction is query.
        """
        configs = self._bundle_configs()
        groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        for event in self._ledger.query(event_type=EventTypes.METRIC_COMPUTED):
            payload = event.payload
            if payload.get("metric") != metric or event.mission_id is None:
                continue
            bundle_id = event.system_bundle_id
            if bundle_id is None or bundle_id not in configs:
                continue  # inadmissible: no frozen configuration to attribute to
            key = (bundle_id, str(payload.get("task_family", "")), str(payload.get("difficulty", "")))
            group = groups.setdefault(
                key, {"failures": [], "n": 0}
            )
            group["n"] += 1
            if float(payload["value"]) < threshold:
                group["failures"].append(event.event_id)

        diagnoses = []
        for (bundle_id, family, difficulty), group in sorted(groups.items()):
            if len(group["failures"]) < self._min_support:
                continue
            diagnoses.append(
                Diagnosis(
                    diagnosis_id=new_id("diag"),
                    failure_signature=f"{metric}<{threshold} on {family}/{difficulty}",
                    metric=metric,
                    task_family=family,
                    difficulty=difficulty,
                    bundle_id=bundle_id,
                    config=configs[bundle_id],
                    n_failures=len(group["failures"]),
                    n_observations=group["n"],
                    evidence_event_ids=tuple(group["failures"]),
                )
            )
        return diagnoses

    def _bundle_configs(self) -> dict[str, dict[str, Any]]:
        configs: dict[str, dict[str, Any]] = {}
        for event in self._ledger.query(event_type=EventTypes.MISSION_STARTED):
            bundle = event.payload.get("bundle")
            if isinstance(bundle, dict) and event.system_bundle_id:
                configs[event.system_bundle_id] = dict(bundle.get("config", {}))
        return configs
