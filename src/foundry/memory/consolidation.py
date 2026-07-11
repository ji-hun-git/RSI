"""Deterministic memory consolidation (report section 11.5, "consolidation
without premature universal rules").

Consolidation is the *producer* the governed :class:`MemoryService` was
waiting for: it turns episodic evidence (recorded mission evaluations) into
candidate semantic claims and negative lessons. It is deliberately
model-free and disciplined by the report's own rules, and it holds no
authority beyond staging -- it never promotes.

The algorithm (report 11.5):

1. Cluster related episodes by task family, difficulty and the frozen
   configuration they ran under (only episodes whose configuration is
   recoverable from a MISSION_STARTED event are attributable, mirroring the
   diagnoser's rule).
2. Form a candidate pattern per cluster stating its preconditions, the
   observed effect, its support and its counterevidence.
3. Search for disconfirming episodes BEFORE creating a rule: a "reliably
   succeeds" pattern with failing episodes in the same cluster, or vice
   versa, is counterevidence. A candidate whose counterexample rate exceeds
   the allowed bound is rejected, not staged.
4. Require recurrence: a pattern below the support minimum is not a rule.
5. Promote narrowly: applicability is scoped to the single (family,
   difficulty) the evidence covers -- generalization is future work, not a
   default.
6. Survivors are STAGED (quarantine) through ``MemoryService.stage`` with
   full provenance (the supporting event ids) and any within-bound
   counterexamples attached as contradicting links. Success clusters become
   semantic claims; failure clusters become negative lessons carrying an
   explicit reconsideration condition.

Determinism and idempotency: a candidate's ``memory_id`` is a content
digest of its cluster signature (kind, family, difficulty, config), so
re-running the job over the same evidence stages nothing new (staging is
idempotent on ``memory_id``). No model, no wall-clock, no randomness
affects what is produced. Because the signature excludes the support
count, a pattern that later accrues more episodes keeps its id and is not
re-staged with the new evidence; refreshing a superseded candidate as a
new versioned record is deliberately left to a future consolidation pass.

The report 11.6 safety invariant holds by construction: nothing here
becomes production memory. A consolidated claim is a quarantined candidate
that still requires review evidence and a distinct non-author promoter
before it can be retrieved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from foundry.contracts import (
    Confidence,
    Event,
    EventTypes,
    LedgerLike,
    MemoryItem,
    MemoryLink,
    MemoryType,
    SourceRef,
    canonical_json,
    sha256_hex,
)

from .service import MemoryService

_CONSOLIDATOR = "consolidator.recurrence"


@dataclass(frozen=True)
class CandidatePattern:
    """A recurring outcome pattern with its confirming and disconfirming evidence."""

    signature: dict[str, Any]
    kind: str  # "success" | "failure"
    task_family: str
    difficulty: str
    config: dict[str, Any]
    support: int
    counterexamples: int
    supporting_refs: tuple[str, ...]
    contradicting_refs: tuple[str, ...]

    @property
    def total(self) -> int:
        return self.support + self.counterexamples

    @property
    def confidence(self) -> float:
        return self.support / self.total if self.total else 0.0


@dataclass(frozen=True)
class ConsolidationReport:
    staged: tuple[str, ...] = ()  # memory_ids staged this run
    rejected: tuple[CandidatePattern, ...] = ()  # below support or over counterexample bound
    considered: int = 0


@dataclass
class _Cluster:
    successes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class MemoryConsolidator:
    """Turns recurring mission-evaluation episodes into staged memory candidates."""

    def __init__(
        self,
        ledger: LedgerLike,
        memory: MemoryService,
        *,
        min_support: int = 3,
        max_counterexample_rate: float = 0.0,
        success_threshold: float = 1.0,
    ) -> None:
        self._ledger = ledger
        self._memory = memory
        self._min_support = min_support
        self._max_counterexample_rate = max_counterexample_rate
        self._success_threshold = success_threshold

    def consolidate(
        self, *, author: str = _CONSOLIDATOR, metric: str = "task_success"
    ) -> ConsolidationReport:
        """Cluster mission episodes and stage the patterns that survive the rules."""
        configs = self._bundle_configs()
        clusters = self._cluster(metric, configs)

        staged: list[str] = []
        rejected: list[CandidatePattern] = []
        for key, cluster in sorted(clusters.items(), key=lambda kv: kv[0]):
            bundle_id, family, difficulty = key
            for candidate in self._candidates(family, difficulty, configs[bundle_id], cluster):
                if self._admissible(candidate):
                    memory_id = self._stage(candidate, author)
                    staged.append(memory_id)
                else:
                    rejected.append(candidate)

        return ConsolidationReport(
            staged=tuple(staged),
            rejected=tuple(rejected),
            considered=len(clusters),
        )

    # -- clustering ------------------------------------------------------------

    def _bundle_configs(self) -> dict[str, dict[str, Any]]:
        configs: dict[str, dict[str, Any]] = {}
        for event in self._ledger.query(event_type=EventTypes.MISSION_STARTED):
            bundle = event.payload.get("bundle")
            if isinstance(bundle, dict) and event.system_bundle_id:
                configs[event.system_bundle_id] = dict(bundle.get("config", {}))
        return configs

    def _cluster(
        self, metric: str, configs: dict[str, dict[str, Any]]
    ) -> dict[tuple[str, str, str], _Cluster]:
        clusters: dict[tuple[str, str, str], _Cluster] = {}
        for event in self._ledger.query(event_type=EventTypes.METRIC_COMPUTED):
            payload = event.payload
            # Mission-level episodes only: the experiment controller also
            # emits METRIC_COMPUTED (mean_score, no mission_id) which is not
            # an episode and must not be consolidated.
            if (
                event.mission_id is None
                or payload.get("metric") != metric
                or "task_family" not in payload
            ):
                continue
            bundle_id = event.system_bundle_id
            if bundle_id is None or bundle_id not in configs:
                continue  # unattributable to a frozen configuration
            try:
                value = float(payload["value"])
            except (KeyError, TypeError, ValueError):
                continue  # a malformed episode is skipped, never a crash
            key = (bundle_id, str(payload["task_family"]), str(payload.get("difficulty", "")))
            cluster = clusters.setdefault(key, _Cluster())
            if value >= self._success_threshold:
                cluster.successes.append(event.event_id)
            else:
                cluster.failures.append(event.event_id)
        return clusters

    # -- candidate patterns ----------------------------------------------------

    def _candidates(
        self, family: str, difficulty: str, config: dict[str, Any], cluster: _Cluster
    ) -> list[CandidatePattern]:
        candidates: list[CandidatePattern] = []
        # A success pattern: episodes succeed; failures are counterevidence.
        if cluster.successes:
            candidates.append(
                CandidatePattern(
                    signature=self._signature("success", family, difficulty, config),
                    kind="success",
                    task_family=family,
                    difficulty=difficulty,
                    config=config,
                    support=len(cluster.successes),
                    counterexamples=len(cluster.failures),
                    supporting_refs=tuple(cluster.successes),
                    contradicting_refs=tuple(cluster.failures),
                )
            )
        # A failure pattern: episodes fail; successes are counterevidence.
        if cluster.failures:
            candidates.append(
                CandidatePattern(
                    signature=self._signature("failure", family, difficulty, config),
                    kind="failure",
                    task_family=family,
                    difficulty=difficulty,
                    config=config,
                    support=len(cluster.failures),
                    counterexamples=len(cluster.successes),
                    supporting_refs=tuple(cluster.failures),
                    contradicting_refs=tuple(cluster.successes),
                )
            )
        return candidates

    @staticmethod
    def _signature(
        kind: str, family: str, difficulty: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "task_family": family,
            "difficulty": difficulty,
            "config": config,
        }

    def _admissible(self, candidate: CandidatePattern) -> bool:
        if candidate.support < self._min_support:
            return False  # recurrence rule (report 11.5 step 4)
        rate = candidate.counterexamples / candidate.total if candidate.total else 1.0
        return rate <= self._max_counterexample_rate  # disconfirming-search rule (step 3)

    # -- staging ---------------------------------------------------------------

    def _stage(self, candidate: CandidatePattern, author: str) -> str:
        memory_id = "mem_" + sha256_hex(canonical_json(candidate.signature))[:32]
        if candidate.kind == "success":
            memory_type = MemoryType.SEMANTIC_CLAIM
            content = {
                "subject": candidate.config,
                "predicate": "reliably_succeeds_on",
                "object": f"{candidate.task_family}/{candidate.difficulty}",
                "preconditions": {
                    "task_family": candidate.task_family,
                    "difficulty": candidate.difficulty,
                    "config": candidate.config,
                },
                "expected_effect": "task_success == 1.0",
                "support": candidate.support,
                "counterexamples": candidate.counterexamples,
            }
            expiration_policy: dict[str, Any] = {}
        else:
            memory_type = MemoryType.NEGATIVE
            content = {
                "subject": candidate.config,
                "predicate": "reliably_fails_on",
                "object": f"{candidate.task_family}/{candidate.difficulty}",
                "preconditions": {
                    "task_family": candidate.task_family,
                    "difficulty": candidate.difficulty,
                    "config": candidate.config,
                },
                "expected_effect": "task_success < 1.0",
                "support": candidate.support,
                "counterexamples": candidate.counterexamples,
            }
            # A negative lesson is a warning, not an absolute prohibition
            # (report 11.3): it carries an explicit reconsideration condition
            # so the promotion gate can accept it.
            expiration_policy = {
                "reconsider_when": (
                    "the configuration, task distribution or worker changes; "
                    "re-evaluate on fresh episodes"
                )
            }

        item = MemoryItem(
            memory_id=memory_id,
            memory_type=memory_type,
            content=content,
            source_refs=[
                SourceRef(artifact_ref=ref, locator=f"{EventTypes.METRIC_COMPUTED}")
                for ref in candidate.supporting_refs
            ],
            contradicting_refs=[
                MemoryLink(target_ref=ref, method="recurrence-counterexample")
                for ref in candidate.contradicting_refs
            ],
            confidence=Confidence(value=candidate.confidence, method="recurrence-frequency"),
            applicability={
                "task_tags": [candidate.task_family],
                "difficulty": [candidate.difficulty],
            },
            lineage={
                "derived_by": _CONSOLIDATOR,
                "signature_digest": memory_id,
                "support": candidate.support,
                "counterexamples": candidate.counterexamples,
            },
            expiration_policy=expiration_policy,
        )
        record = self._memory.stage(item, author=author)
        return record.item.memory_id

    # -- convenience for callers/tests ----------------------------------------

    @staticmethod
    def episode_events(ledger: LedgerLike, metric: str = "task_success") -> list[Event]:
        return [
            e
            for e in ledger.query(event_type=EventTypes.METRIC_COMPUTED)
            if e.mission_id is not None and e.payload.get("metric") == metric
        ]
