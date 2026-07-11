"""Read-only projection from a foundry root to a :class:`DashboardModel`.

Every function here only *reads* the ledger and registry (report 15: the
dashboard is part of the scientific apparatus, not an actor). State is
reconstructed exclusively from canonical events, exactly as the deployment
controller, the coverage meter and ``foundry verify`` do, so the dashboard
can never diverge from the evidence it is supposed to explain.
"""

from __future__ import annotations

from typing import Any

from foundry.contracts import Event, EventTypes, LedgerLike
from foundry.deployment.controller import rebuild_state
from foundry.registry import BundleRegistry, IntegrityError

from .model import (
    ArmView,
    BundleNode,
    ChangeView,
    DashboardModel,
    DecisionView,
    DeploymentStep,
    EvidenceContext,
    ExperimentView,
    GateResultView,
    Incident,
    MissionView,
    NodeStep,
    ProposalView,
    ResourceTotals,
    RoleAnalysisView,
)

_CANDIDATE_ROLE_ORDER = ["development", "protected", "retention", "adversarial"]

#: Identity fields written by ``BundleRegistry.fork`` itself: lineage
#: bookkeeping, not proposed behavior. Excluded from the diff a decision
#: displays (mirrors ``cli.FORK_BOOKKEEPING_PATHS``).
_FORK_BOOKKEEPING_PATHS = frozenset({"/parent_bundle_id", "/semantic_version"})


def _sequence(event: Event) -> int:
    return event.integrity.sequence if event.integrity is not None else -1


def _parse_ci(ci: object) -> tuple[float | None, float | None]:
    """Read a confidence interval robustly. A missing or malformed interval
    yields (None, None) -- rendered as "unavailable", never as a fabricated
    zero-width [0.0, 0.0] that would read as perfect certainty, and never a
    crash on tampered evidence (the dashboard renders even on a broken chain)."""
    if not isinstance(ci, (list, tuple)) or len(ci) < 2:
        return (None, None)
    try:
        return (float(ci[0]), float(ci[1]))
    except (TypeError, ValueError):
        return (None, None)


def build_dashboard_model(
    ledger: LedgerLike,
    registry: BundleRegistry,
    *,
    root_name: str = "foundry",
    artifact_count: int = 0,
) -> DashboardModel:
    """Project the complete dashboard model from a ledger and registry."""
    events = ledger.all_events()
    chain_ok, chain_errors = ledger.verify_chain()
    tip_digest = None
    if events and events[-1].integrity is not None:
        tip_digest = events[-1].integrity.digest

    state = rebuild_state(events)
    active_bundle_id = state.active_bundle_id

    missions = _project_missions(events)
    proposals = _project_proposals(events)
    experiments = _project_experiments(events)
    decisions = _project_decisions(events, registry, proposals)
    bundle_roots, corrupt_bundle_ids = _project_bundle_tree(
        registry, state, decisions, active_bundle_id
    )
    deployment_timeline = _project_deployment_timeline(events)
    incidents = _project_incidents(events, chain_ok, chain_errors, decisions, corrupt_bundle_ids)
    resources = _project_resources(
        events, missions, experiments, decisions, registry, artifact_count
    )

    return DashboardModel(
        root_name=root_name,
        evidence=EvidenceContext(
            event_count=len(events),
            tip_digest=tip_digest,
            chain_ok=chain_ok,
            chain_errors=tuple(chain_errors),
        ),
        active_bundle_id=active_bundle_id,
        missions=missions,
        proposals=proposals,
        experiments=experiments,
        decisions=decisions,
        bundle_roots=bundle_roots,
        deployment_timeline=deployment_timeline,
        incidents=incidents,
        resources=resources,
    )


# -- missions -----------------------------------------------------------------


def _project_missions(events: list[Event]) -> tuple[MissionView, ...]:
    started = [e for e in events if e.event_type == EventTypes.MISSION_STARTED]
    by_run: dict[str, list[Event]] = {}
    for event in events:
        if event.run_id is not None:
            by_run.setdefault(event.run_id, []).append(event)

    missions: list[MissionView] = []
    for start in started:
        run_id = start.run_id
        run_events = by_run.get(run_id, []) if run_id is not None else []
        spec = start.payload.get("spec", {})
        inputs = spec.get("inputs", {}) if isinstance(spec, dict) else {}
        input_text = inputs.get("text") if isinstance(inputs, dict) else None

        timeline: list[NodeStep] = []
        final_output = None
        output_digest = None
        artifact_refs: list[str] = []
        status = "started"
        for event in run_events:
            if event.event_type == EventTypes.NODE_COMPLETED:
                timeline.append(
                    NodeStep(
                        node_id=event.node_id or "?",
                        status="completed",
                        output_digest=event.payload.get("output_digest"),
                    )
                )
            elif event.event_type == EventTypes.NODE_FAILED:
                timeline.append(
                    NodeStep(
                        node_id=event.node_id or "?",
                        status="failed",
                        detail=str(event.payload.get("error", "")),
                    )
                )
                status = "failed"
            elif event.event_type == EventTypes.DUPLICATE_SUPPRESSED:
                timeline.append(NodeStep(node_id=event.node_id or "?", status="suppressed"))
            elif event.event_type == EventTypes.MISSION_COMPLETED:
                status = "completed"
                out = event.payload.get("final_output")
                if isinstance(out, dict):
                    final_output = out.get("output")
                output_digest = event.payload.get("output_digest")
                artifact_refs.extend(event.output_refs)
            elif event.event_type == EventTypes.MISSION_CANCELLED:
                status = "cancelled"
            elif event.event_type == EventTypes.MISSION_FAILED:
                status = "failed"

        missions.append(
            MissionView(
                mission_id=start.mission_id or "?",
                run_id=run_id,
                status=status,
                bundle_id=start.system_bundle_id,
                input_text=input_text,
                final_output=final_output,
                output_digest=output_digest,
                timeline=tuple(timeline),
                artifact_refs=tuple(artifact_refs),
            )
        )
    return tuple(missions)


# -- proposals ----------------------------------------------------------------


def _project_proposals(events: list[Event]) -> tuple[ProposalView, ...]:
    proposals: list[ProposalView] = []
    for event in events:
        if event.event_type != EventTypes.PROPOSAL_SUBMITTED:
            continue
        p = event.payload.get("proposal", {})
        changes = tuple(
            ChangeView(
                field_path=c.get("field_path", "?"),
                old_value=c.get("old_value"),
                new_value=c.get("new_value"),
            )
            for c in p.get("changes", [])
        )
        proposer = p.get("proposer", {})
        proposer_id = proposer.get("id", "?") if isinstance(proposer, dict) else str(proposer)
        proposals.append(
            ProposalView(
                proposal_id=p.get("proposal_id", "?"),
                hypothesis=p.get("hypothesis", ""),
                current_behavior=p.get("current_behavior", ""),
                changes=changes,
                autonomy_level=int(p.get("autonomy_level", 0)),
                minimum_practical_effect=float(p.get("minimum_practical_effect", 0.0)),
                retention_floor=float(p.get("retention_floor", 0.0)),
                retention_set_ref=p.get("retention_set_ref", ""),
                rollback_condition=p.get("rollback_condition", ""),
                experiment_plan_ref=p.get("experiment_plan_ref"),
                proposer=proposer_id,
                evidence_refs=tuple(p.get("evidence_refs", [])),
                risks=tuple(p.get("risks", [])),
            )
        )
    return tuple(proposals)


# -- experiments --------------------------------------------------------------


def _project_experiments(events: list[Event]) -> tuple[ExperimentView, ...]:
    designed = {
        e.experiment_id: e for e in events if e.event_type == EventTypes.EXPERIMENT_DESIGNED
    }
    analyzed = {
        e.experiment_id: e for e in events if e.event_type == EventTypes.EXPERIMENT_ANALYZED
    }
    leakage: dict[str | None, int] = {}
    for e in events:
        if e.event_type == EventTypes.LEAKAGE_DETECTED:
            # One event can carry many leaked handles; count handles, not events.
            handles = e.payload.get("handles")
            hits = e.payload.get("n_hits", len(handles) if isinstance(handles, list) else 1)
            leakage[e.experiment_id] = leakage.get(e.experiment_id, 0) + int(hits)
    decisions_by_experiment: dict[str | None, list[str]] = {}
    for e in events:
        if e.event_type == EventTypes.GOVERNANCE_DECISION and e.experiment_id is not None:
            decision = e.payload.get("decision", {})
            decisions_by_experiment.setdefault(e.experiment_id, []).append(
                decision.get("decision_id", "?")
            )

    experiments: list[ExperimentView] = []
    for experiment_id, design in designed.items():
        arms = tuple(
            ArmView(
                arm_id=a.get("arm_id", "?"),
                bundle_id=a.get("bundle_id", "?"),
                is_control=bool(a.get("is_control", False)),
            )
            for a in design.payload.get("arms", [])
        )
        analyses: list[RoleAnalysisView] = []
        seed = None
        mpe = None
        analysis_event = analyzed.get(experiment_id)
        if analysis_event is not None:
            seed = analysis_event.payload.get("seed")
            mpe = analysis_event.payload.get("minimum_practical_effect")
            per_arm = analysis_event.payload.get("arms", {})
            # Every candidate arm is projected, not just the first: a losing
            # arm's evidence is a branch that must not be omitted (report 15.4).
            for arm in arms:
                if arm.is_control:
                    continue
                role_map = per_arm.get(arm.arm_id, {})
                for role in _CANDIDATE_ROLE_ORDER:
                    if role not in role_map:
                        continue
                    row = role_map[role]
                    ci_low, ci_high = _parse_ci(row.get("ci"))
                    analyses.append(
                        RoleAnalysisView(
                            arm_id=arm.arm_id,
                            role=role,
                            n_pairs=int(row.get("n_pairs", 0)),
                            mean_delta=float(row.get("mean_delta", 0.0)),
                            ci_low=ci_low,
                            ci_high=ci_high,
                            wins=int(row.get("wins", 0)),
                            losses=int(row.get("losses", 0)),
                            ties=int(row.get("ties", 0)),
                        )
                    )
        experiments.append(
            ExperimentView(
                experiment_id=experiment_id or "?",
                seed=seed,
                minimum_practical_effect=mpe,
                arms=arms,
                analyses=tuple(analyses),
                leakage_hits=leakage.get(experiment_id, 0),
                decision_ids=tuple(decisions_by_experiment.get(experiment_id, [])),
            )
        )
    return tuple(experiments)


# -- decisions ----------------------------------------------------------------


def _project_decisions(
    events: list[Event], registry: BundleRegistry, proposals: tuple[ProposalView, ...] = ()
) -> tuple[DecisionView, ...]:
    proposals_by_id = {p.proposal_id: p for p in proposals}
    decisions: list[DecisionView] = []
    for event in events:
        if event.event_type != EventTypes.GOVERNANCE_DECISION:
            continue
        d = event.payload.get("decision", {})
        gate_results = tuple(
            GateResultView(
                gate=g.get("gate", "?"),
                passed=bool(g.get("passed", False)),
                reason=g.get("reason", ""),
            )
            for g in d.get("gate_results", [])
        )
        parent_id = d.get("parent_bundle_id", "?")
        candidate_id = d.get("candidate_bundle_id", "?")
        changes, diff_source = _decision_diff(
            registry, parent_id, candidate_id, proposals_by_id.get(d.get("proposal_id"))
        )
        decisions.append(
            DecisionView(
                decision_id=d.get("decision_id", "?"),
                action=d.get("action", "?"),
                proposal_id=d.get("proposal_id"),
                experiment_id=d.get("experiment_id"),
                candidate_bundle_id=candidate_id,
                parent_bundle_id=parent_id,
                required_tier=d.get("required_approval_tier", "?"),
                reason=d.get("reason", ""),
                signed=bool(d.get("signature")),
                gate_results=gate_results,
                approvals=tuple(d.get("approvals", [])),
                rollback_target=d.get("rollback_target"),
                changes=changes,
                diff_source=diff_source,
            )
        )
    return tuple(decisions)


def _decision_diff(
    registry: BundleRegistry,
    parent_id: str,
    candidate_id: str,
    proposal: ProposalView | None,
) -> tuple[tuple[ChangeView, ...], str]:
    """Authoritative diff for a decision (report 15.4: never approve without it).

    Prefers the registry's parent-vs-candidate diff (independent of the
    proposal link); falls back to the linked proposal's declared changes,
    then to empty (rendered as "diff unavailable"). Fork bookkeeping paths
    are excluded, matching the diff the gate reviewed.
    """
    if registry.exists(parent_id) and registry.exists(candidate_id):
        try:
            raw = registry.diff(parent_id, candidate_id)
        except (IntegrityError, KeyError, ValueError):
            raw = None
        if raw is not None:
            changes = tuple(
                ChangeView(field_path=c.field_path, old_value=c.old_value, new_value=c.new_value)
                for c in raw.changes
                if c.field_path not in _FORK_BOOKKEEPING_PATHS
            )
            return changes, "registry"
    if proposal is not None and proposal.changes:
        return proposal.changes, "proposal"
    return (), "unavailable"


# -- bundle tree --------------------------------------------------------------


def _project_bundle_tree(
    registry: BundleRegistry,
    state: Any,
    decisions: tuple[DecisionView, ...],
    active_bundle_id: str | None,
) -> tuple[tuple[BundleNode, ...], tuple[str, ...]]:
    bundles = {}
    corrupt: list[str] = []
    for bundle_id in registry.list_ids():
        try:
            bundles[bundle_id] = registry.get(bundle_id)
        except IntegrityError:
            corrupt.append(bundle_id)  # surfaced as an incident, not silently dropped

    quarantined = {d.candidate_bundle_id for d in decisions if d.action == "quarantine"}
    rejected = {d.candidate_bundle_id for d in decisions if d.action == "reject"}
    ever_deployed = set(getattr(state, "parents", {}))

    def lifecycle(bundle_id: str) -> str:
        # Current standing, derived from the deployment projection -- not the
        # cumulative canary set (canary is mandatory before production, so a
        # cumulative check would label every deployed bundle "canaried" and
        # make "rolled_back"/"active" unreachable, report 15.4).
        if bundle_id == active_bundle_id:
            return "active"
        if bundle_id in ever_deployed:
            return "rolled_back"  # was active, since superseded or rolled back
        if bundle_id in rejected:
            return "rejected"  # a hard gate failure, distinct from an authority hold
        if bundle_id in quarantined:
            return "quarantined"  # evidence acceptable, authorization absent
        return "registered"

    children: dict[str | None, list[str]] = {}
    for bundle_id, bundle in bundles.items():
        children.setdefault(bundle.parent_bundle_id, []).append(bundle_id)
    for sibling_ids in children.values():
        sibling_ids.sort()

    def build(bundle_id: str) -> BundleNode:
        bundle = bundles[bundle_id]
        return BundleNode(
            bundle_id=bundle_id,
            semantic_version=bundle.semantic_version,
            registry_status=bundle.status.value,
            parent_bundle_id=bundle.parent_bundle_id,
            config=dict(bundle.config),
            is_active=bundle_id == active_bundle_id,
            lifecycle=lifecycle(bundle_id),
            children=tuple(build(child_id) for child_id in children.get(bundle_id, [])),
        )

    roots = sorted(
        bundle_id
        for bundle_id, bundle in bundles.items()
        if bundle.parent_bundle_id not in bundles
    )
    return tuple(build(root_id) for root_id in roots), tuple(sorted(corrupt))


# -- deployment timeline ------------------------------------------------------


def _project_deployment_timeline(events: list[Event]) -> tuple[DeploymentStep, ...]:
    steps: list[DeploymentStep] = []
    for event in sorted(events, key=_sequence):
        if event.event_type in (EventTypes.CANARY_STARTED, EventTypes.PROMOTION):
            record = event.payload.get("deployment", {})
            steps.append(
                DeploymentStep(
                    kind="canary" if event.event_type == EventTypes.CANARY_STARTED else "promotion",
                    bundle_id=record.get("bundle_id", "?"),
                    from_bundle_id=None,
                    to_bundle_id=None,
                    decision_id=record.get("decision_id"),
                    trigger=None,
                    sequence=_sequence(event),
                )
            )
        elif event.event_type == EventTypes.ROLLBACK:
            record = event.payload.get("rollback", {})
            steps.append(
                DeploymentStep(
                    kind="rollback",
                    bundle_id=record.get("to_bundle_id", "?"),
                    from_bundle_id=record.get("from_bundle_id"),
                    to_bundle_id=record.get("to_bundle_id"),
                    decision_id=None,
                    trigger=record.get("trigger"),
                    sequence=_sequence(event),
                )
            )
    return tuple(steps)


# -- incidents ----------------------------------------------------------------


_FAILURE_EVENT_KINDS = {
    EventTypes.INCIDENT: "incident",
    EventTypes.EXPERIMENT_STOPPED: "experiment_stopped",
    EventTypes.BUDGET_EXHAUSTED: "budget_exhausted",
    EventTypes.RESOURCE_QUOTA_VIOLATION: "quota_violation",
    EventTypes.MODEL_VALIDATION_FAILED: "model_validation_failed",
    EventTypes.MODEL_REFUSAL: "model_refusal",
}


def _project_incidents(
    events: list[Event],
    chain_ok: bool,
    chain_errors: list[str],
    decisions: tuple[DecisionView, ...],
    corrupt_bundle_ids: tuple[str, ...] = (),
) -> tuple[Incident, ...]:
    incidents: list[Incident] = []
    if not chain_ok:
        for error in chain_errors:
            incidents.append(
                Incident(kind="chain_error", summary=error, event_id=None, sequence=None)
            )
    for bundle_id in corrupt_bundle_ids:
        incidents.append(
            Incident(
                kind="corrupt_bundle",
                summary=f"registered bundle {bundle_id} failed its content-address check",
                event_id=None,
                sequence=None,
            )
        )
    for event in sorted(events, key=_sequence):
        if event.event_type in _FAILURE_EVENT_KINDS:
            incidents.append(
                Incident(
                    kind=_FAILURE_EVENT_KINDS[event.event_type],
                    summary=str(
                        event.payload.get("reason")
                        or event.payload.get("detail")
                        or event.event_type
                    ),
                    event_id=event.event_id,
                    sequence=_sequence(event),
                )
            )
        elif event.event_type == EventTypes.POLICY_DENIAL:
            incidents.append(
                Incident(
                    kind="policy_denial",
                    summary=str(event.payload.get("reason", "policy denied an action")),
                    event_id=event.event_id,
                    sequence=_sequence(event),
                )
            )
        elif event.event_type == EventTypes.TOOL_DENIED:
            incidents.append(
                Incident(
                    kind="policy_denial",
                    summary=str(event.payload.get("reason", "tool call denied")),
                    event_id=event.event_id,
                    sequence=_sequence(event),
                )
            )
        elif event.event_type == EventTypes.LEAKAGE_DETECTED:
            incidents.append(
                Incident(
                    kind="leakage",
                    summary=f"protected task content leaked into experiment {event.experiment_id}",
                    event_id=event.event_id,
                    sequence=_sequence(event),
                )
            )
        elif event.event_type == EventTypes.NODE_FAILED:
            incidents.append(
                Incident(
                    kind="node_failed",
                    summary=f"node {event.node_id} failed in run {event.run_id}",
                    event_id=event.event_id,
                    sequence=_sequence(event),
                )
            )
        elif event.event_type == EventTypes.ROLLBACK:
            record = event.payload.get("rollback", {})
            incidents.append(
                Incident(
                    kind="rollback",
                    summary=(
                        f"rolled back {record.get('from_bundle_id', '?')} to "
                        f"{record.get('to_bundle_id', '?')} (trigger: {record.get('trigger', '?')})"
                    ),
                    event_id=event.event_id,
                    sequence=_sequence(event),
                )
            )
    for decision in decisions:
        # A reject (hard gate failure) is a different outcome from a quarantine
        # (evidence acceptable, authorization absent); do not fold them together.
        if decision.action == "quarantine":
            incidents.append(
                Incident(
                    kind="quarantine",
                    summary=(
                        f"candidate {decision.candidate_bundle_id} quarantined "
                        f"(evidence acceptable, authorization absent): {decision.reason}"
                    ),
                    event_id=None,
                    sequence=None,
                )
            )
        elif decision.action == "reject":
            failed = ", ".join(g.gate for g in decision.gate_results if not g.passed)
            incidents.append(
                Incident(
                    kind="rejected",
                    summary=(
                        f"candidate {decision.candidate_bundle_id} rejected"
                        f"{f' (failed {failed})' if failed else ''}: {decision.reason}"
                    ),
                    event_id=None,
                    sequence=None,
                )
            )
    return tuple(incidents)


# -- resources ----------------------------------------------------------------


def _project_resources(
    events: list[Event],
    missions: tuple[MissionView, ...],
    experiments: tuple[ExperimentView, ...],
    decisions: tuple[DecisionView, ...],
    registry: BundleRegistry,
    artifact_count: int,
) -> ResourceTotals:
    input_tokens = 0
    output_tokens = 0
    cost_usd = 0.0
    wall_ms = 0
    model_calls = 0
    for event in events:
        usage = event.usage
        input_tokens += usage.input_tokens
        output_tokens += usage.output_tokens
        cost_usd += usage.cost_usd
        wall_ms += usage.wall_ms
        if event.event_type == EventTypes.MODEL_RESPONSE:
            model_calls += 1
    return ResourceTotals(
        events=len(events),
        missions=len(missions),
        experiments=len(experiments),
        decisions=len(decisions),
        bundles=len(registry.list_ids()),
        artifacts=artifact_count,
        model_calls=model_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost_usd, 6),
        wall_ms=wall_ms,
    )
