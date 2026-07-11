"""Capability-bound tool gateway (report sections 10.2, 14.3, 14.4).

The load-bearing invariants: deny-by-default (no capability, no call),
non-transferable capabilities, discovery is not authorization, egress/SSRF
blocking before the tool runs, per-call receipts to the ledger, untrusted
output, an excessive-output cap, and idempotent replay of side-effecting
calls.
"""

from __future__ import annotations

import pytest

from foundry.contracts import CapabilityToken, EventTypes
from foundry.ledger import EventLedger
from foundry.policy import CapabilityIssuer
from foundry.tools import (
    AppendLogTool,
    EchoTool,
    EgressPolicy,
    FetchTool,
    OversizeTool,
    ToolDenied,
    ToolExecutionError,
    ToolGateway,
    tool_manifest,
)

SUBJECT = "agent.builder"
MISSION = "mis_tools"


@pytest.fixture()
def ledger() -> EventLedger:
    return EventLedger(":memory:")


def cap(actions: list[str], scopes: list[str], subject: str = SUBJECT, ttl: int = 900) -> CapabilityToken:
    return CapabilityToken(
        subject=subject, actions=actions, resource_scopes=scopes, ttl_seconds=ttl, mission_id=MISSION
    )


def gateway_with(ledger: EventLedger, *tools, egress: EgressPolicy | None = None) -> ToolGateway:
    gw = ToolGateway(ledger, egress=egress)
    for tool in tools:
        gw.register(tool_manifest(tool.tool_id), tool)
    return gw


# -- deny-by-default ----------------------------------------------------------


def test_no_capability_is_denied(ledger: EventLedger) -> None:
    gw = gateway_with(ledger, EchoTool())
    with pytest.raises(ToolDenied, match="no capability"):
        gw.call("echo", {"x": 1}, None, subject=SUBJECT, action="tool.echo")
    denials = ledger.query(event_type=EventTypes.TOOL_DENIED)
    assert len(denials) == 1 and denials[0].payload["authorized"] is False


def test_capability_for_a_different_action_is_denied(ledger: EventLedger) -> None:
    gw = gateway_with(ledger, EchoTool())
    token = cap(actions=["tool.other"], scopes=[])
    with pytest.raises(ToolDenied, match="does not authorize"):
        gw.call("echo", {"x": 1}, token, subject=SUBJECT, action="tool.echo")


def test_authorized_call_succeeds_and_is_receipted(ledger: EventLedger) -> None:
    gw = gateway_with(ledger, EchoTool())
    token = cap(actions=["tool.echo"], scopes=[])
    result = gw.call("echo", {"x": 1}, token, subject=SUBJECT, action="tool.echo", mission_id=MISSION)
    assert result.output == {"echo": {"x": 1}}
    assert result.untrusted is True  # tool output is data, not instructions
    r = result.receipt
    assert r.authorized and r.tool_id == "echo" and r.capability_ref == token.capability_id
    assert r.args_digest.startswith("sha256:") and r.response_digest.startswith("sha256:")
    # the ledger holds the authorize/call/result trail
    assert ledger.query(event_type=EventTypes.TOOL_AUTHORIZED)
    assert ledger.query(event_type=EventTypes.TOOL_RESULT)


# -- non-transferable capabilities --------------------------------------------


def test_capability_is_non_transferable(ledger: EventLedger) -> None:
    gw = gateway_with(ledger, EchoTool())
    token = cap(actions=["tool.echo"], scopes=[], subject="agent.designer")
    # presented by a different subject than it was bound to
    with pytest.raises(ToolDenied):
        gw.call("echo", {"x": 1}, token, subject=SUBJECT, action="tool.echo")


def test_expired_capability_is_denied(ledger: EventLedger) -> None:
    gw = gateway_with(ledger, EchoTool())
    token = cap(actions=["tool.echo"], scopes=[], ttl=0)  # already expired
    with pytest.raises(ToolDenied):
        gw.call("echo", {"x": 1}, token, subject=SUBJECT, action="tool.echo")


# -- discovery is not authorization -------------------------------------------


def test_unregistered_tool_is_denied(ledger: EventLedger) -> None:
    gw = gateway_with(ledger, EchoTool())
    token = cap(actions=["tool.ghost"], scopes=[])
    with pytest.raises(ToolDenied, match="not registered"):
        gw.call("ghost", {}, token, subject=SUBJECT, action="tool.ghost")


def test_registration_records_discovery_but_grants_nothing(ledger: EventLedger) -> None:
    gw = gateway_with(ledger, EchoTool())
    assert gw.list_tools() == ["echo"]
    assert ledger.query(event_type=EventTypes.TOOL_DISCOVERED)
    # present in the catalog, still not callable without a capability
    with pytest.raises(ToolDenied):
        gw.call("echo", {}, None, subject=SUBJECT, action="tool.echo")


# -- egress / SSRF ------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://127.0.0.1:8080/admin",  # loopback
        "http://10.0.0.5/internal",  # private range
        "http://localhost/x",  # loopback host
        "http://192.168.1.1/",  # private range
    ],
)
def test_ssrf_targets_are_blocked_before_the_tool_runs(ledger: EventLedger, url: str) -> None:
    gw = gateway_with(ledger, FetchTool())
    token = cap(actions=["tool.net.fetch"], scopes=[url])
    with pytest.raises(ToolDenied, match="egress denied"):
        gw.call(
            "net.fetch", {"url": url}, token, subject=SUBJECT,
            action="tool.net.fetch", resource=url,
        )
    # denied before execution: no completed-result event
    assert not ledger.query(event_type=EventTypes.TOOL_RESULT)


def test_allowlisted_external_host_is_permitted(ledger: EventLedger) -> None:
    url = "https://api.example.com/v1/data"
    gw = gateway_with(ledger, FetchTool(), egress=EgressPolicy(allow_domains=("example.com",)))
    token = cap(actions=["tool.net.fetch"], scopes=[url])
    result = gw.call(
        "net.fetch", {"url": url}, token, subject=SUBJECT,
        action="tool.net.fetch", resource=url,
    )
    assert result.output["status"] == 200
    # an external side effect is receipted as such
    assert ledger.query(event_type=EventTypes.TOOL_SIDE_EFFECT)


def test_host_outside_allowlist_is_denied(ledger: EventLedger) -> None:
    url = "https://evil.test/x"
    gw = gateway_with(ledger, FetchTool(), egress=EgressPolicy(allow_domains=("example.com",)))
    token = cap(actions=["tool.net.fetch"], scopes=[url])
    with pytest.raises(ToolDenied, match="allowlist"):
        gw.call("net.fetch", {"url": url}, token, subject=SUBJECT,
                action="tool.net.fetch", resource=url)


# -- resource scoping ---------------------------------------------------------


def test_capability_resource_scope_is_enforced(ledger: EventLedger) -> None:
    gw = gateway_with(ledger, FetchTool(), egress=EgressPolicy(allow_domains=("example.com",)))
    # token scoped to one path; a different path is out of scope
    token = cap(actions=["tool.net.fetch"], scopes=["https://api.example.com/v1/"])
    with pytest.raises(ToolDenied):
        gw.call(
            "net.fetch", {"url": "https://api.example.com/v2/other"}, token,
            subject=SUBJECT, action="tool.net.fetch", resource="https://api.example.com/v2/other",
        )


# -- output governance --------------------------------------------------------


def test_excessive_output_is_refused(ledger: EventLedger) -> None:
    gw = ToolGateway(ledger, max_output_bytes=1024)
    gw.register(tool_manifest("oversize"), OversizeTool())
    token = cap(actions=["tool.oversize"], scopes=[])
    with pytest.raises(ToolExecutionError, match="exceeds"):
        gw.call("oversize", {}, token, subject=SUBJECT, action="tool.oversize")
    result_events = ledger.query(event_type=EventTypes.TOOL_RESULT)
    assert result_events and result_events[0].payload.get("error") == "excessive output"


def test_tool_crash_fails_closed(ledger: EventLedger) -> None:
    class Boom:
        tool_id = "boom"
        side_effect_class = "none"

        def invoke(self, args):
            raise RuntimeError("kaboom")

    gw = gateway_with(ledger, Boom())
    token = cap(actions=["tool.boom"], scopes=[])
    with pytest.raises(ToolExecutionError, match="kaboom"):
        gw.call("boom", {}, token, subject=SUBJECT, action="tool.boom")


# -- idempotent retry ---------------------------------------------------------


def test_idempotent_replay_does_not_run_a_side_effect_twice(ledger: EventLedger) -> None:
    tool = AppendLogTool()
    gw = gateway_with(ledger, tool)
    token = cap(actions=["tool.log.append"], scopes=[])
    first = gw.call("log.append", {"line": "a"}, token, subject=SUBJECT,
                    action="tool.log.append", idempotency_key="k1")
    second = gw.call("log.append", {"line": "a"}, token, subject=SUBJECT,
                     action="tool.log.append", idempotency_key="k1")
    assert first.output == second.output == {"appended": 1}
    assert tool.log == ["a"]  # the write ran exactly once
    assert second.receipt is first.receipt  # the recorded receipt is returned


def test_idempotent_replay_still_requires_authorization(ledger: EventLedger) -> None:
    """A cached side-effect result must not be handed to an unauthorized
    replay: authorization is checked before the idempotency cache."""
    tool = AppendLogTool()
    gw = gateway_with(ledger, tool)
    good = cap(actions=["tool.log.append"], scopes=[])
    gw.call("log.append", {"line": "a"}, good, subject=SUBJECT,
            action="tool.log.append", idempotency_key="k1")
    # a replay with a capability that does not authorize the action is denied,
    # even though a result for k1 is cached
    wrong = cap(actions=["tool.other"], scopes=[])
    with pytest.raises(ToolDenied):
        gw.call("log.append", {"line": "a"}, wrong, subject=SUBJECT,
                action="tool.log.append", idempotency_key="k1")


def test_distinct_idempotency_keys_run_the_effect(ledger: EventLedger) -> None:
    tool = AppendLogTool()
    gw = gateway_with(ledger, tool)
    token = cap(actions=["tool.log.append"], scopes=[])
    gw.call("log.append", {"line": "a"}, token, subject=SUBJECT, action="tool.log.append", idempotency_key="k1")
    gw.call("log.append", {"line": "b"}, token, subject=SUBJECT, action="tool.log.append", idempotency_key="k2")
    assert tool.log == ["a", "b"]


# -- revocation-aware authorizer ----------------------------------------------


def test_revoked_capability_is_denied_when_issuer_authorizes(ledger: EventLedger) -> None:
    issuer = CapabilityIssuer()
    token = issuer.issue(SUBJECT, actions=["tool.echo"], resource_scopes=[], ttl_seconds=900)

    def authorize(tok, subject, action, resource):
        return issuer.validate(tok, subject=subject, action=action, resource=resource)

    gw = ToolGateway(ledger, authorize=authorize)
    gw.register(tool_manifest("echo"), EchoTool())
    # works before revocation
    gw.call("echo", {"x": 1}, token, subject=SUBJECT, action="tool.echo")
    issuer.revoke(token.capability_id)
    with pytest.raises(ToolDenied):
        gw.call("echo", {"x": 1}, token, subject=SUBJECT, action="tool.echo")
