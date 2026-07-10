"""Change proposer seam and the template-mutation reference proposer
(report 8.3 improvement loop steps 2-3, 10.4 Change Proposer, 12.4).

The seam is :class:`ProposerLike`: diagnoses in, fully-formed typed
:class:`~foundry.contracts.ImprovementProposal` objects out, inside
explicit :class:`ProposalConstraints`. A proposer is pure candidate
generation -- it holds no registry write handle, no vault access and no
approval authority; everything it emits still has to survive fork policy,
the paired experiment, the G0-G9 gate and human approval. GEPA, DSPy or
TextGrad adapters implement the same protocol behind
``adapters/optimizers/gepa_dspy/``.

:class:`TemplateMutationProposer` is the deterministic reference
implementation, the report 12.4 "template mutation" strategy ("bounded
edits to known manifest fields -- safest first automation"): a mutation
table maps an observed config value to allowed replacement candidates,
and a diagnosis whose failing missions share that value yields one
proposal per replacement.

Two stopping conditions of report 12.5 are enforced here rather than
left to discipline: proposals whose diff was already rejected are not
re-emitted without new evidence, and the constraint budget caps the
number of proposals per call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from foundry.contracts import (
    AutonomyLevel,
    ChangeTarget,
    DeploymentScope,
    FieldChange,
    ImprovementProposal,
    ModuleRef,
    SystemBundle,
    content_digest,
)

from .diagnoser import Diagnosis


def diff_digest(changes: list[FieldChange]) -> str:
    """Content address of a candidate diff, used to recognize resubmissions."""
    payload = sorted(
        (c.field_path, repr(c.old_value), repr(c.new_value)) for c in changes
    )
    return content_digest(payload)


class ProposalPolicyViolation(Exception):
    """A proposer tried to leave its allowed mutation surface."""


@dataclass(frozen=True)
class RejectedDiff:
    """A previously rejected candidate diff and the evidence it was based on.

    Report 12.5: a proposal converging on a rejected diff is only
    admissible again when it carries NEW evidence.
    """

    digest: str
    evidence_event_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ProposalConstraints:
    """The box a proposer works inside; set by governance, not by the proposer.

    ``value_domains`` declares the legal values for closed-domain config
    fields (e.g. ``{"/config/strategy": ("naive", "robust")}``). A proposer
    must not emit a value outside a declared domain; fields without a
    declared domain are open (free-text prompts and similar).
    """

    allowed_path_prefixes: tuple[str, ...]
    max_autonomy_level: AutonomyLevel = AutonomyLevel.PROMPT_SKILL_ROUTING
    max_proposals: int = 3
    minimum_practical_effect: float = 0.05
    retention_floor: float = 0.0
    retention_set_ref: str = ""
    experiment_plan_ref: str = "artifact://plan/template-mutation-v1"
    rejected_diffs: tuple[RejectedDiff, ...] = ()
    min_failure_rate: float = 0.25
    value_domains: dict[str, tuple[Any, ...]] = field(default_factory=dict)


@runtime_checkable
class ProposerLike(Protocol):
    """The optimizer seam (report 12.4): any candidate generator plugs in here."""

    proposer_ref: ModuleRef

    def propose(
        self,
        diagnoses: list[Diagnosis],
        parent: SystemBundle,
        constraints: ProposalConstraints,
    ) -> list[ImprovementProposal]: ...


def path_within(field_path: str, prefixes: tuple[str, ...]) -> bool:
    """True when *field_path* sits inside one of the allowed prefixes (segment-aware)."""
    return any(
        field_path == prefix or field_path.startswith(prefix.rstrip("/") + "/")
        for prefix in prefixes
    )


@dataclass(frozen=True)
class TemplateMutationProposer:
    """Deterministic bounded-mutation proposer (report 12.4, first row of
    the strategy table after human-designed diffs).

    ``mutation_table`` maps a bundle config field path to
    ``{observed_value: [candidate_values...]}``. The table itself is part
    of governance configuration: the proposer cannot invent targets, only
    instantiate the table against diagnosed failures.
    """

    mutation_table: dict[str, dict[str, list[Any]]] = field(default_factory=dict)
    proposer_ref: ModuleRef = field(
        default_factory=lambda: ModuleRef(id="optimizer.template-mutation", version="1.0.0")
    )

    def propose(
        self,
        diagnoses: list[Diagnosis],
        parent: SystemBundle,
        constraints: ProposalConstraints,
    ) -> list[ImprovementProposal]:
        for path in self.mutation_table:
            if not path_within(path, constraints.allowed_path_prefixes):
                raise ProposalPolicyViolation(
                    f"mutation table targets {path!r}, outside the allowed "
                    f"surface {list(constraints.allowed_path_prefixes)}"
                )
        rejected = {r.digest: r for r in constraints.rejected_diffs}
        proposals: list[ImprovementProposal] = []
        for diagnosis in diagnoses:
            if diagnosis.bundle_id != parent.bundle_id:
                continue  # stale evidence from another lineage; not attributable
            if diagnosis.failure_rate < constraints.min_failure_rate:
                continue
            for field_path, replacements in sorted(self.mutation_table.items()):
                key = field_path.removeprefix("/config/")
                observed = diagnosis.config.get(key)
                for candidate_value in replacements.get(observed, []):
                    change = FieldChange(
                        field_path=field_path, old_value=observed, new_value=candidate_value
                    )
                    digest = diff_digest([change])
                    prior = rejected.get(digest)
                    if prior is not None and not (
                        set(diagnosis.evidence_event_ids) - prior.evidence_event_ids
                    ):
                        continue  # report 12.5: rejected diff, no new evidence
                    proposals.append(
                        self._build(diagnosis, parent, constraints, change, observed)
                    )
                    if len(proposals) >= constraints.max_proposals:
                        return proposals
        return proposals

    def _build(
        self,
        diagnosis: Diagnosis,
        parent: SystemBundle,
        constraints: ProposalConstraints,
        change: FieldChange,
        observed: Any,
    ) -> ImprovementProposal:
        return ImprovementProposal(
            parent_bundle_id=parent.bundle_id,
            target=ChangeTarget(field_path=change.field_path),
            current_behavior=(
                f"{diagnosis.n_failures}/{diagnosis.n_observations} missions fail "
                f"{diagnosis.failure_signature} under "
                f"{change.field_path}={observed!r}"
            ),
            hypothesis=(
                f"Setting {change.field_path} to {change.new_value!r} removes the "
                f"repeatable failure signature {diagnosis.failure_signature!r} "
                f"without regressing retained capabilities."
            ),
            evidence_refs=list(diagnosis.evidence_event_ids),
            changes=[change],
            expected_effects={diagnosis.metric: round(diagnosis.failure_rate, 4)},
            risks=[
                f"the {change.new_value!r} setting may alter behavior on task "
                "families the diagnosis did not cover"
            ],
            autonomy_level=constraints.max_autonomy_level,
            deployment_scope=DeploymentScope(task_types=[diagnosis.task_family]),
            experiment_plan_ref=constraints.experiment_plan_ref,
            retention_set_ref=constraints.retention_set_ref,
            minimum_practical_effect=constraints.minimum_practical_effect,
            retention_floor=constraints.retention_floor,
            rollback_condition=(
                "holdout ci_low below the minimum practical effect or any "
                "retention loss: roll back to the parent bundle"
            ),
            proposer=self.proposer_ref,
        )
