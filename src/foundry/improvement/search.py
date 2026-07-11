"""Governed improvement search with budget accounting (report 12.2, 12.5, 6).

The improvement loop run once (diagnose, propose, experiment, gate) is one
step; a *search* runs many steps under a fixed budget and stops on an
explicit rule. This is the report 12.2 BOUNDED_RSI control loop's
search-and-stop skeleton and the resource accounting report 6 asks for:
"the full cost of search, failed variants, human review and maintenance."

The controller owns only the budget, the stopping conditions and the
accounting. Candidate generation and evaluation are injected, so the search
is decoupled from any domain and testable in isolation:

    propose(parent, rejected_diffs)  -> list[ImprovementProposal]
    evaluate(parent, proposal)       -> CandidateOutcome

``propose`` is handed the diffs rejected so far, so a proposer that honors
the report 12.5 rejected-diff rule (like ``TemplateMutationProposer``)
stops emitting exhausted candidates and the search converges to "no
proposals" rather than looping forever.

Stopping conditions implemented (report 12.5):

* a candidate is accepted (reached canary) -- stop, success;
* the cost, candidate or iteration budget is exhausted;
* candidate generation converges (no new proposals, i.e. the proposer has
  only rejected diffs left);
* no candidate exceeds the minimum practical effect on the protected
  holdout after the budget is spent.

The controller never promotes and never approves: it drives generation and
evaluation and reports what it found. Every budget event is optionally
recorded to the ledger for the resource-economy view.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from foundry.contracts import (
    Event,
    EventTypes,
    ImprovementProposal,
    LedgerLike,
    SystemBundle,
)

from .proposer import RejectedDiff


@dataclass(frozen=True)
class SearchBudget:
    """The search's hard ceilings (report 12.5 "search budget exhausted")."""

    max_cost_usd: float = 100.0
    max_candidates: int = 10
    max_iterations: int = 5
    minimum_practical_effect: float = 0.05


@dataclass(frozen=True)
class CandidateOutcome:
    """The result of evaluating one candidate, with its search-cost share."""

    proposal_id: str
    candidate_bundle_id: str
    diff_digest: str
    action: str  # gate decision action: "canary" | "quarantine" | "reject" | "retest"
    holdout_lower_bound: float  # protected-holdout ci_low for this candidate
    cost_usd: float
    accepted: bool  # reached canary (an evidence-and-authority pass)
    evidence_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchReport:
    """Full accounting of a search (report 6 scientific resource accounting)."""

    iterations: int
    candidates_evaluated: int
    total_cost_usd: float
    accepted: CandidateOutcome | None
    outcomes: tuple[CandidateOutcome, ...]
    rejected_diffs: tuple[str, ...]
    best_holdout_lower_bound: float | None
    stop_reason: str


Propose = Callable[[SystemBundle, tuple[RejectedDiff, ...]], list[ImprovementProposal]]
Evaluate = Callable[[SystemBundle, ImprovementProposal], CandidateOutcome]


@dataclass
class SearchController:
    """Runs a budget-governed improvement search and accounts its full cost."""

    budget: SearchBudget = field(default_factory=SearchBudget)
    ledger: LedgerLike | None = None

    def run(self, parent: SystemBundle, propose: Propose, evaluate: Evaluate) -> SearchReport:
        outcomes: list[CandidateOutcome] = []
        rejected: dict[str, RejectedDiff] = {}
        cost = 0.0
        iterations = 0
        accepted: CandidateOutcome | None = None
        stop: str | None = None

        self._emit(EventTypes.BUDGET_RESERVED, {"budget": self._budget_payload()})

        while iterations < self.budget.max_iterations:
            iterations += 1
            proposals = propose(parent, tuple(rejected.values()))
            if not proposals:
                # The proposer has only rejected diffs left: convergence.
                stop = "candidate generation converged (no new proposals)"
                break

            made_progress = False
            for proposal in proposals:
                if len(outcomes) >= self.budget.max_candidates:
                    stop = "candidate budget exhausted"
                    break
                if cost >= self.budget.max_cost_usd:
                    stop = "cost budget exhausted"
                    break

                outcome = evaluate(parent, proposal)
                cost += outcome.cost_usd
                outcomes.append(outcome)
                made_progress = True

                if outcome.accepted:
                    accepted = outcome
                    stop = "accepted a candidate"
                    break
                # A non-accepted candidate's diff is retired; the proposer must
                # not re-emit it without new evidence (report 12.5).
                rejected[outcome.diff_digest] = RejectedDiff(
                    digest=outcome.diff_digest,
                    evidence_event_ids=frozenset(outcome.evidence_event_ids),
                )
                if cost >= self.budget.max_cost_usd:
                    stop = "cost budget exhausted"
                    break

            if accepted is not None or stop is not None:
                break
            if not made_progress:
                stop = "no progress within budget"
                break

        if stop is None:
            stop = "iteration budget exhausted"

        best = max((o.holdout_lower_bound for o in outcomes), default=None)
        if (
            accepted is None
            and best is not None
            and best < self.budget.minimum_practical_effect
            and stop in ("iteration budget exhausted", "candidate budget exhausted",
                         "cost budget exhausted", "candidate generation converged (no new proposals)")
        ):
            stop = (
                f"{stop}; no candidate exceeded the minimum practical effect "
                f"{self.budget.minimum_practical_effect:+.3f} on the holdout"
            )

        if "budget exhausted" in stop:
            self._emit(EventTypes.BUDGET_EXHAUSTED, {"total_cost_usd": round(cost, 6),
                                                     "candidates": len(outcomes)})

        return SearchReport(
            iterations=iterations,
            candidates_evaluated=len(outcomes),
            total_cost_usd=round(cost, 6),
            accepted=accepted,
            outcomes=tuple(outcomes),
            rejected_diffs=tuple(rejected),
            best_holdout_lower_bound=best,
            stop_reason=stop,
        )

    # -- internal --------------------------------------------------------------

    def _budget_payload(self) -> dict[str, float | int]:
        return {
            "max_cost_usd": self.budget.max_cost_usd,
            "max_candidates": self.budget.max_candidates,
            "max_iterations": self.budget.max_iterations,
            "minimum_practical_effect": self.budget.minimum_practical_effect,
        }

    def _emit(self, event_type: str, payload: dict) -> None:
        if self.ledger is not None:
            self.ledger.append(
                Event(event_type=event_type, actor="search-controller", payload=payload)
            )
