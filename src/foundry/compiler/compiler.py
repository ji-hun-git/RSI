"""Mission compiler: MissionRequest -> immutable MissionSpec (report 10.2, 17.4).

The compiler is the front door of mission execution: it turns a raw human
request into a frozen :class:`~foundry.contracts.MissionSpec` pinned to
exactly one signed :class:`~foundry.contracts.SystemBundle`. Stage 1
compiles fixture tasks fully deterministically -- objectives and acceptance
criteria are pure functions of the request inputs, and the acceptance
oracle is the deterministic exact-match check. The compiler reads registry
and policy state but executes no tools (report 10.2); its only side effect
is the ``mission.compiled`` evidence event.
"""

from __future__ import annotations

from foundry.contracts import (
    AcceptanceCriterion,
    Event,
    EventTypes,
    LedgerLike,
    MissionRequest,
    MissionSpec,
    Objective,
    PromotionStatus,
    SystemBundle,
    content_digest,
)

EXACT_MATCH_ORACLE_REF = "oracle://exact-match/v1"

_REFUSED_STATUSES = frozenset({PromotionStatus.DEPRECATED, PromotionStatus.REVOKED})


class MissionCompiler:
    """Compiles requests into frozen, bundle-pinned mission specs."""

    def __init__(self, ledger: LedgerLike) -> None:
        self._ledger = ledger

    def compile(self, request: MissionRequest, bundle: SystemBundle) -> MissionSpec:
        """Produce an immutable MissionSpec pinned to *bundle*.

        Raises ``ValueError`` if the bundle is no longer runnable
        (``deprecated`` or ``revoked``): a mission compiled against a
        retired genome would not be admissible evidence (report 9.1).
        """
        if bundle.status in _REFUSED_STATUSES:
            raise ValueError(
                f"bundle {bundle.bundle_id!r} has status {bundle.status.value!r}; "
                "missions cannot be compiled against deprecated or revoked bundles"
            )

        task_key = str(request.inputs.get("task_id", request.request_id))
        family = str(request.inputs.get("family", "slugify"))
        objective_text = request.description or (
            f"Apply the {family} transformation to the provided input text."
        )
        spec = MissionSpec(
            project_id=request.project_id,
            request_ref=request.request_id,
            task_type=request.task_type,
            objectives=[
                Objective(id=f"obj:{task_key}:primary", text=objective_text)
            ],
            acceptance_criteria=[
                AcceptanceCriterion(
                    id=f"ac:{task_key}:exact-match",
                    text=(
                        f"Worker output must exactly match the expected {family} "
                        "output for the task input."
                    ),
                    oracle=EXACT_MATCH_ORACLE_REF,
                )
            ],
            risk_class=request.risk_class,
            operating_profile=request.operating_profile,
            system_bundle_id=bundle.bundle_id,
            inputs=dict(request.inputs),
        )

        self._ledger.append(
            Event(
                event_type=EventTypes.MISSION_COMPILED,
                mission_id=spec.mission_id,
                system_bundle_id=bundle.bundle_id,
                actor="mission-compiler",
                subject=request.request_id,
                payload={
                    "spec_digest": content_digest(spec),
                    "request_id": request.request_id,
                    "task_type": spec.task_type,
                },
            )
        )
        return spec
