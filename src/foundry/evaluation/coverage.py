"""Event-coverage meter for the Stage-1 exit criterion (report 19.1:
"at least 95% required event coverage on fixtures").

Coverage is measured against a *declared* required vocabulary, because
"covered" is only meaningful relative to what a given run was supposed to
emit (report 15.2 defines the full families; a demo run legitimately
never cancels a mission). Two standard sets are provided:

* :data:`DEMO_REQUIRED_EVENTS` -- everything the nine-step demo story
  must ledger, from compilation through experiment, governance decision,
  canary, promotion and rollback.
* :data:`STAGE1_FIXTURE_REQUIRED_EVENTS` -- the demo set plus the
  interruption vocabulary (resume, duplicate suppression, node failure,
  cancellation) that the crash/replay fixtures exercise
  (STAGE1_PROTOCOL.md section 2).

The meter never mutates anything: it is a read-only audit over the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass

from foundry.contracts import EventTypes, LedgerLike

DEMO_REQUIRED_EVENTS: frozenset[str] = frozenset(
    {
        EventTypes.MISSION_COMPILED,
        EventTypes.MISSION_STARTED,
        EventTypes.NODE_STARTED,
        EventTypes.NODE_COMPLETED,
        EventTypes.MISSION_COMPLETED,
        EventTypes.PROPOSAL_SUBMITTED,
        EventTypes.EXPERIMENT_DESIGNED,
        EventTypes.EXPERIMENT_RANDOMIZED,
        EventTypes.ARM_STARTED,
        EventTypes.ARM_COMPLETED,
        EventTypes.METRIC_COMPUTED,
        EventTypes.EXPERIMENT_ANALYZED,
        EventTypes.APPROVAL_REQUESTED,
        EventTypes.GOVERNANCE_DECISION,
        EventTypes.CANARY_STARTED,
        EventTypes.PROMOTION,
        EventTypes.ROLLBACK,
    }
)

STAGE1_FIXTURE_REQUIRED_EVENTS: frozenset[str] = DEMO_REQUIRED_EVENTS | frozenset(
    {
        EventTypes.MISSION_RESUMED,
        EventTypes.DUPLICATE_SUPPRESSED,
        EventTypes.NODE_FAILED,
        EventTypes.MISSION_CANCELLED,
    }
)

EXIT_CRITERION_THRESHOLD = 0.95


@dataclass(frozen=True)
class CoverageReport:
    """Which required event types a ledger actually contains."""

    required: frozenset[str]
    observed: frozenset[str]
    missing: tuple[str, ...]

    @property
    def ratio(self) -> float:
        if not self.required:
            return 1.0
        return (len(self.required) - len(self.missing)) / len(self.required)

    def passed(self, threshold: float = EXIT_CRITERION_THRESHOLD) -> bool:
        return self.ratio >= threshold


def measure_coverage(
    ledger: LedgerLike, required: frozenset[str] = DEMO_REQUIRED_EVENTS
) -> CoverageReport:
    """Read-only coverage audit of *ledger* against *required*."""
    observed = frozenset(event.event_type for event in ledger.query())
    missing = tuple(sorted(required - observed))
    return CoverageReport(required=required, observed=observed, missing=missing)
