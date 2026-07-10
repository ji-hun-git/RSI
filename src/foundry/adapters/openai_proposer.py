"""OpenAI reflective proposer: the first model-backed ProposerLike
(report 12.4 "DSPy/GEPA optimizer" row, in its simplest defensible form:
reflective proposal generation from diagnosis evidence, no evolutionary
search yet).

Authority model, unchanged from the deterministic reference: the model
only ever produces *data*. Its inputs are diagnosis summaries (failure
signatures, rates and the frozen config -- never task contents, never
holdout anything) plus the allowed mutation surface; its output is
validated fail-closed before a single ImprovementProposal is built:

* a suggested ``field_path`` outside ``constraints.allowed_path_prefixes``
  is dropped, never widened;
* ``old_value`` is taken from the PARENT BUNDLE, not from the model, so a
  hallucinated current state cannot enter the typed diff;
* the rejected-diff rule (report 12.5) and the proposal budget apply
  exactly as they do to the template proposer;
* malformed or non-JSON model output yields zero proposals, not an error
  path into the loop.

Evidence discipline (report 12.3 "proposer identity, model/version,
prompt/version"): when a ledger is supplied, every API call is recorded
as MODEL_REQUEST/MODEL_RESPONSE canonical events carrying provider, model,
sampling settings, prompt and response digests and token usage -- and
those event ids join the proposal's ``evidence_refs``. The API key is
read from the environment at client construction and never appears in
code, events, artifacts or logs.

Requires the ``openai`` optional dependency group only when a real client
is used; any object with ``chat.completions.create`` can be injected
instead (that is how the offline tests run).
"""

from __future__ import annotations

import json
import os
from typing import Any

from foundry.contracts import (
    ChangeTarget,
    DeploymentScope,
    Event,
    EventTypes,
    FieldChange,
    ImprovementProposal,
    LedgerLike,
    ModelRef,
    ModuleRef,
    SystemBundle,
    Usage,
    content_digest,
)
from foundry.improvement import (
    Diagnosis,
    ProposalConstraints,
    diff_digest,
    path_within,
)

_RESPONSE_SCHEMA: dict[str, Any] = {
    "name": "improvement_proposals",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "proposals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field_path": {"type": "string"},
                        "new_value": {"type": "string"},
                        "hypothesis": {"type": "string"},
                        "expected_effect": {"type": "number"},
                        "risks": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "field_path",
                        "new_value",
                        "hypothesis",
                        "expected_effect",
                        "risks",
                    ],
                },
            }
        },
        "required": ["proposals"],
    },
}

_SYSTEM_PROMPT = (
    "You are a change proposer inside a governed agent-system experiment "
    "platform. You receive repeatable failure diagnoses for a frozen system "
    "configuration and the exact list of configuration paths you are allowed "
    "to modify. Propose at most the requested number of single-field changes "
    "that could remove the diagnosed failures. You have no authority: every "
    "proposal will be re-validated, tested in a paired experiment against a "
    "blind holdout, and gated by humans. Never propose paths outside the "
    "allowed list. Each hypothesis must be one falsifiable sentence."
)
PROMPT_VERSION = "1.0.0"


class OpenAIReflectiveProposer:
    """ProposerLike backed by the OpenAI chat completions API."""

    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        *,
        client: Any = None,
        ledger: LedgerLike | None = None,
        temperature: float = 0.0,
        seed: int = 0,
        max_output_tokens: int = 1200,
    ) -> None:
        self._client = client
        self._model = model
        self._ledger = ledger
        self._temperature = temperature
        self._seed = seed
        self._max_output_tokens = max_output_tokens
        self.proposer_ref = ModuleRef(id="optimizer.openai-reflective", version=PROMPT_VERSION)

    # -- ProposerLike ----------------------------------------------------------

    def propose(
        self,
        diagnoses: list[Diagnosis],
        parent: SystemBundle,
        constraints: ProposalConstraints,
    ) -> list[ImprovementProposal]:
        relevant = [
            d
            for d in diagnoses
            if d.bundle_id == parent.bundle_id
            and d.failure_rate >= constraints.min_failure_rate
        ]
        if not relevant:
            return []
        prompt = self._render_prompt(relevant, parent, constraints)
        raw, call_event_ids = self._query(prompt)
        suggestions = self._parse(raw)
        if suggestions is None:
            return []  # fail-closed: unusable model output produces nothing

        rejected = {r.digest: r for r in constraints.rejected_diffs}
        evidence_pool = [eid for d in relevant for eid in d.evidence_event_ids]
        proposals: list[ImprovementProposal] = []
        for suggestion in suggestions:
            field_path = str(suggestion["field_path"])
            if not path_within(field_path, constraints.allowed_path_prefixes):
                continue  # dropped, never widened
            key = field_path.removeprefix("/config/")
            observed = parent.config.get(key)  # ground truth from the bundle
            new_value = suggestion["new_value"]
            if new_value == observed:
                continue  # a no-op is not a change proposal
            domain = constraints.value_domains.get(field_path)
            if domain is not None and new_value not in domain:
                continue  # hallucinated value for a closed-domain field: dropped
            change = FieldChange(field_path=field_path, old_value=observed, new_value=new_value)
            prior = rejected.get(diff_digest([change]))
            if prior is not None and not (set(evidence_pool) - prior.evidence_event_ids):
                continue  # report 12.5: rejected diff, no new evidence
            diagnosis = self._best_match(relevant)
            proposals.append(
                self._build(
                    diagnosis, parent, constraints, change, suggestion, call_event_ids
                )
            )
            if len(proposals) >= constraints.max_proposals:
                break
        return proposals

    # -- internals --------------------------------------------------------------

    def _render_prompt(
        self,
        diagnoses: list[Diagnosis],
        parent: SystemBundle,
        constraints: ProposalConstraints,
    ) -> str:
        lines = [
            f"Frozen configuration under test (bundle {parent.bundle_id[:19]}...):",
            json.dumps(parent.config, sort_keys=True),
            "",
            "Allowed mutation paths (proposals outside this list are discarded):",
            json.dumps(list(constraints.allowed_path_prefixes)),
        ]
        if constraints.value_domains:
            lines += [
                "",
                "Closed-domain fields: for these paths you MUST pick one of the "
                "listed legal values (anything else is discarded):",
                json.dumps(
                    {k: list(v) for k, v in sorted(constraints.value_domains.items())}
                ),
            ]
        lines += [
            "",
            f"Emit at most {constraints.max_proposals} proposals.",
            "",
            "Repeatable failure diagnoses:",
        ]
        for d in diagnoses:
            lines.append(
                f"- {d.failure_signature}: {d.n_failures}/{d.n_observations} missions "
                f"failed (rate {d.failure_rate:.2f}) on family {d.task_family!r} "
                f"difficulty {d.difficulty!r} under config {json.dumps(d.config, sort_keys=True)}"
            )
        return "\n".join(lines)

    def _query(self, prompt: str) -> tuple[str, list[str]]:
        client = self._client if self._client is not None else self._default_client()
        request_digest = content_digest({"system": _SYSTEM_PROMPT, "user": prompt})
        event_ids: list[str] = []
        if self._ledger is not None:
            event_ids.append(
                self._ledger.append(
                    Event(
                        event_type=EventTypes.MODEL_REQUEST,
                        actor=self.proposer_ref.id,
                        model_ref=self._model_ref(),
                        payload={
                            "purpose": "improvement-proposal",
                            "prompt_digest": request_digest,
                            "prompt_version": PROMPT_VERSION,
                        },
                    )
                ).event_id
            )
        completion = client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            seed=self._seed,
            max_tokens=self._max_output_tokens,
            response_format={"type": "json_schema", "json_schema": _RESPONSE_SCHEMA},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        raw = completion.choices[0].message.content or ""
        if self._ledger is not None:
            usage = getattr(completion, "usage", None)
            event_ids.append(
                self._ledger.append(
                    Event(
                        event_type=EventTypes.MODEL_RESPONSE,
                        actor=self.proposer_ref.id,
                        model_ref=self._model_ref(),
                        parent_event_ids=event_ids[:1],
                        usage=Usage(
                            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                        ),
                        payload={
                            "prompt_digest": request_digest,
                            "response_digest": content_digest(raw),
                        },
                    )
                ).event_id
            )
        return raw, event_ids

    def _default_client(self) -> Any:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set; the reflective proposer reads the key "
                "from the environment only (it is never stored in code or evidence)"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - exercised without the extra
            raise ImportError(
                "OpenAIReflectiveProposer needs the 'openai' optional dependency: "
                'pip install "agent-foundry[openai]"'
            ) from exc
        return OpenAI()

    def _model_ref(self) -> ModelRef:
        return ModelRef(
            provider="openai",
            model=self._model,
            sampling={"temperature": self._temperature, "seed": self._seed},
        )

    @staticmethod
    def _parse(raw: str) -> list[dict[str, Any]] | None:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        proposals = data.get("proposals") if isinstance(data, dict) else None
        if not isinstance(proposals, list):
            return None
        cleaned = []
        for entry in proposals:
            if not isinstance(entry, dict):
                continue
            if not all(k in entry for k in ("field_path", "new_value", "hypothesis")):
                continue
            cleaned.append(entry)
        return cleaned

    @staticmethod
    def _best_match(diagnoses: list[Diagnosis]) -> Diagnosis:
        return max(diagnoses, key=lambda d: (d.failure_rate, d.n_failures, d.diagnosis_id))

    def _build(
        self,
        diagnosis: Diagnosis,
        parent: SystemBundle,
        constraints: ProposalConstraints,
        change: FieldChange,
        suggestion: dict[str, Any],
        call_event_ids: list[str],
    ) -> ImprovementProposal:
        expected = suggestion.get("expected_effect", diagnosis.failure_rate)
        risks = [str(r) for r in suggestion.get("risks", [])] or [
            "the proposed setting may alter behavior on task families the "
            "diagnosis did not cover"
        ]
        return ImprovementProposal(
            parent_bundle_id=parent.bundle_id,
            target=ChangeTarget(field_path=change.field_path),
            current_behavior=(
                f"{diagnosis.n_failures}/{diagnosis.n_observations} missions fail "
                f"{diagnosis.failure_signature} under "
                f"{change.field_path}={change.old_value!r}"
            ),
            hypothesis=str(suggestion["hypothesis"]),
            evidence_refs=list(diagnosis.evidence_event_ids) + call_event_ids,
            changes=[change],
            expected_effects={diagnosis.metric: float(expected)},
            risks=risks,
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


__all__ = ["OpenAIReflectiveProposer", "PROMPT_VERSION"]
