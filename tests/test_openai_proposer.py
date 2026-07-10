"""OpenAI reflective proposer: offline (injected fake client) and live tests.

The offline tests pin the authority boundary: model output is untrusted
data, so out-of-surface paths are dropped, old values come from the
parent bundle rather than the model, malformed output yields zero
proposals, the rejected-diff rule holds, and every API call is ledgered
as MODEL_REQUEST/MODEL_RESPONSE evidence with digests only (never the
key, never raw secrets).

The live test runs only when OPENAI_API_KEY is present (skipped in CI).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import pytest

from foundry.adapters.openai_proposer import OpenAIReflectiveProposer
from foundry.contracts import AutonomyLevel, EventTypes, SystemBundle
from foundry.improvement import (
    Diagnosis,
    ProposalConstraints,
    ProposerLike,
    RejectedDiff,
    diff_digest,
)
from foundry.ledger import EventLedger
from foundry.policy import ALLOWED_MUTATIONS
from foundry.runtime import FIXTURE_WORKFLOW_REF

L2_PREFIXES = tuple(ALLOWED_MUTATIONS[AutonomyLevel.PROMPT_SKILL_ROUTING])


def bundle() -> SystemBundle:
    return SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "naive"})


def diagnosis(parent: SystemBundle, evidence: tuple[str, ...] = ("evt_a", "evt_b", "evt_c")) -> Diagnosis:
    return Diagnosis(
        diagnosis_id="diag_1",
        failure_signature="task_success<1.0 on slugify/hard",
        metric="task_success",
        task_family="slugify",
        difficulty="hard",
        bundle_id=parent.bundle_id,
        config=dict(parent.config),
        n_failures=10,
        n_observations=10,
        evidence_event_ids=evidence,
    )


def constraints(**overrides) -> ProposalConstraints:
    defaults = dict(allowed_path_prefixes=L2_PREFIXES, retention_set_ref="corpus://fixture/7/retention")
    defaults.update(overrides)
    return ProposalConstraints(**defaults)


# -- fake OpenAI client -----------------------------------------------------------


@dataclass
class _FakeCompletion:
    content: str

    @property
    def choices(self):  # mimics openai types just enough
        message = type("M", (), {"content": self.content})
        return [type("C", (), {"message": message})]

    usage = type("U", (), {"prompt_tokens": 100, "completion_tokens": 50})


@dataclass
class FakeClient:
    reply: str
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def chat(self):
        outer = self

        class _Completions:
            @staticmethod
            def create(**kwargs):
                outer.calls.append(kwargs)
                return _FakeCompletion(outer.reply)

        class _Chat:
            completions = _Completions()

        return _Chat()


def reply(*suggestions: dict[str, Any]) -> str:
    return json.dumps({"proposals": list(suggestions)})


GOOD = {
    "field_path": "/config/strategy",
    "new_value": "robust",
    "hypothesis": "Robust normalization removes the hard-task failures.",
    "expected_effect": 0.5,
    "risks": ["may alter easy-task outputs"],
}


# -- offline: authority boundary ----------------------------------------------------


def test_satisfies_proposer_protocol() -> None:
    proposer = OpenAIReflectiveProposer(client=FakeClient(reply(GOOD)))
    assert isinstance(proposer, ProposerLike)


def test_builds_typed_proposal_with_ledgered_model_evidence() -> None:
    ledger = EventLedger(":memory:")
    parent = bundle()
    proposer = OpenAIReflectiveProposer(client=FakeClient(reply(GOOD)), ledger=ledger)

    proposals = proposer.propose([diagnosis(parent)], parent, constraints())

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.changes[0].field_path == "/config/strategy"
    assert proposal.changes[0].old_value == "naive"  # from the bundle, not the model
    assert proposal.changes[0].new_value == "robust"
    assert proposal.proposer.id == "optimizer.openai-reflective"
    assert proposal.hypothesis == GOOD["hypothesis"]

    request = ledger.query(event_type=EventTypes.MODEL_REQUEST)
    response = ledger.query(event_type=EventTypes.MODEL_RESPONSE)
    assert len(request) == 1 and len(response) == 1
    assert request[0].model_ref is not None and request[0].model_ref.provider == "openai"
    assert response[0].usage.input_tokens == 100
    # digests only: no prompt text, no key material in the evidence
    assert set(request[0].payload) == {"purpose", "prompt_digest", "prompt_version"}
    assert request[0].payload["prompt_digest"].startswith("sha256:")
    # the model-call events are part of the proposal's evidence chain
    assert request[0].event_id in proposal.evidence_refs
    assert response[0].event_id in proposal.evidence_refs
    for eid in diagnosis(parent).evidence_event_ids:
        assert eid in proposal.evidence_refs


def test_out_of_surface_suggestion_is_dropped_never_widened() -> None:
    rogue = {**GOOD, "field_path": "/evaluation_profile_ref", "new_value": "weaker"}
    parent = bundle()
    proposer = OpenAIReflectiveProposer(client=FakeClient(reply(rogue, GOOD)))
    proposals = proposer.propose([diagnosis(parent)], parent, constraints())
    assert [p.changes[0].field_path for p in proposals] == ["/config/strategy"]


def test_hallucinated_current_value_cannot_enter_the_diff() -> None:
    lying = {**GOOD}
    parent = bundle()
    proposer = OpenAIReflectiveProposer(client=FakeClient(reply(lying)))
    proposal = proposer.propose([diagnosis(parent)], parent, constraints())[0]
    # old_value is read from the frozen bundle regardless of model claims.
    assert proposal.changes[0].old_value == parent.config["strategy"]


def test_out_of_domain_value_is_dropped() -> None:
    """A hallucinated value for a closed-domain field never becomes a diff
    (found live: the model proposed strategy='advanced', which does not exist)."""
    hallucinated = {**GOOD, "new_value": "advanced"}
    parent = bundle()
    proposer = OpenAIReflectiveProposer(client=FakeClient(reply(hallucinated, GOOD)))
    proposals = proposer.propose(
        [diagnosis(parent)],
        parent,
        constraints(value_domains={"/config/strategy": ("naive", "robust")}),
    )
    assert [p.changes[0].new_value for p in proposals] == ["robust"]


def test_noop_suggestion_is_dropped() -> None:
    noop = {**GOOD, "new_value": "naive"}
    parent = bundle()
    proposer = OpenAIReflectiveProposer(client=FakeClient(reply(noop)))
    assert proposer.propose([diagnosis(parent)], parent, constraints()) == []


@pytest.mark.parametrize(
    "raw",
    ["not json", json.dumps({"nope": 1}), json.dumps({"proposals": "not-a-list"}), ""],
)
def test_malformed_model_output_yields_zero_proposals(raw: str) -> None:
    parent = bundle()
    proposer = OpenAIReflectiveProposer(client=FakeClient(raw))
    assert proposer.propose([diagnosis(parent)], parent, constraints()) == []


def test_rejected_diff_rule_applies_to_model_output() -> None:
    parent = bundle()
    d = diagnosis(parent)
    change_digest = diff_digest(
        [p.changes[0] for p in OpenAIReflectiveProposer(client=FakeClient(reply(GOOD))).propose(
            [d], parent, constraints()
        )]
    )
    rejected = RejectedDiff(digest=change_digest, evidence_event_ids=frozenset(d.evidence_event_ids))
    silenced = OpenAIReflectiveProposer(client=FakeClient(reply(GOOD))).propose(
        [d], parent, constraints(rejected_diffs=(rejected,))
    )
    assert silenced == []
    fresh = diagnosis(parent, evidence=("evt_new1", "evt_new2", "evt_new3"))
    revived = OpenAIReflectiveProposer(client=FakeClient(reply(GOOD))).propose(
        [fresh], parent, constraints(rejected_diffs=(rejected,))
    )
    assert len(revived) == 1


def test_budget_caps_model_enthusiasm() -> None:
    many = [
        {**GOOD, "new_value": f"variant_{i}", "hypothesis": f"variant {i} helps."}
        for i in range(6)
    ]
    parent = bundle()
    proposer = OpenAIReflectiveProposer(client=FakeClient(reply(*many)))
    proposals = proposer.propose([diagnosis(parent)], parent, constraints(max_proposals=2))
    assert len(proposals) == 2


def test_no_relevant_diagnosis_means_no_api_call() -> None:
    client = FakeClient(reply(GOOD))
    parent = bundle()
    other = SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "naive", "x": 1})
    proposer = OpenAIReflectiveProposer(client=client)
    assert proposer.propose([diagnosis(other)], parent, constraints()) == []
    assert client.calls == []  # stale evidence never reaches the model


def test_missing_key_fails_closed_without_client() -> None:
    key = os.environ.pop("OPENAI_API_KEY", None)
    try:
        proposer = OpenAIReflectiveProposer()
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            proposer.propose([diagnosis(bundle())], bundle(), constraints())
    finally:
        if key is not None:
            os.environ["OPENAI_API_KEY"] = key


# -- live (skipped without a key; never runs in CI) ---------------------------------


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set; live test skipped"
)
def test_live_openai_proposer_emits_valid_proposal() -> None:
    ledger = EventLedger(":memory:")
    parent = bundle()
    proposer = OpenAIReflectiveProposer(ledger=ledger)
    proposals = proposer.propose([diagnosis(parent)], parent, constraints())
    assert proposals, "live model returned no usable proposal"
    proposal = proposals[0]
    assert proposal.changes[0].field_path.startswith(tuple(L2_PREFIXES))
    assert proposal.changes[0].old_value == "naive"
    assert proposal.hypothesis
    assert ledger.query(event_type=EventTypes.MODEL_RESPONSE)
