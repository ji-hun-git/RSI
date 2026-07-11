"""Capability-bound tool gateway (report sections 10.2, 14.3, 14.4).

The tool boundary is a primary security surface (report 14.3): "MCP
improves interoperability but introduces explicit authorization and
deployment responsibilities... terminate MCP at the Tool Gateway and
translate calls into its internal capability and receipt model." This
gateway is that termination point for any tool -- native or MCP -- behind
one internal interface.

Every call is:

* separated from discovery -- a tool present in the registry is not
  thereby callable (report 14.3: "presence in a catalog never implies
  permission to invoke");
* authorized by a short-lived, scoped, non-transferable capability token
  bound to the calling subject (deny-by-default: no capability, no call);
* egress-checked -- a resource the tool would reach must pass the SSRF
  policy before the tool runs;
* size-bounded -- an oversized output is refused, not passed on (the
  "excessive output" failure mode);
* receipted -- tool version, argument digest, capability, response digest,
  latency and side-effect class are recorded to the append-only ledger
  (report 14.3/14.4), and the returned output is flagged untrusted data;
* idempotent on request -- a repeated call carrying the same idempotency
  key returns the recorded receipt instead of re-executing a side effect
  (the "non-idempotent retry" failure mode).

The gateway authorizes with capabilities, not by routing through the
promotion-policy PDP: capabilities are the report's tool-authorization
model, and the PDP governs the mutation surface, a different decision.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol, runtime_checkable

from foundry.contracts import (
    CapabilityToken,
    Event,
    EventTypes,
    LedgerLike,
    ModuleManifest,
    canonical_json,
    content_digest,
    new_id,
)

from .egress import EgressPolicy

#: Side-effect classes whose re-execution must be guarded by idempotency
#: (a repeated call with the same key must not run the effect twice).
_SIDE_EFFECTING = frozenset({"write", "external", "monetary"})
_DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024


@runtime_checkable
class ToolProvider(Protocol):
    """A tool behind the gateway. ``side_effect_class`` is declared, not inferred."""

    tool_id: str
    side_effect_class: str  # "none" | "read" | "write" | "external" | "monetary"

    def invoke(self, args: dict[str, Any]) -> dict[str, Any]: ...


class ToolGatewayError(Exception):
    """Base class for gateway refusals and failures."""


class ToolDenied(ToolGatewayError):
    """A call was refused before execution (authorization or policy)."""


class ToolExecutionError(ToolGatewayError):
    """A call reached the tool but failed (crash or oversized output)."""


@dataclass(frozen=True)
class ToolReceipt:
    """Per-call audit record (report 14.3 "record ... for every call")."""

    receipt_id: str
    tool_id: str
    tool_version: str
    subject: str
    mission_id: str | None
    action: str
    resource: str | None
    capability_ref: str | None
    authorized: bool
    args_digest: str
    response_digest: str | None
    side_effect_class: str
    latency_ms: int
    idempotency_key: str | None
    idempotent_replay: bool
    denied_reason: str | None = None
    error: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "subject": self.subject,
            "action": self.action,
            "resource": self.resource,
            "capability_ref": self.capability_ref,
            "authorized": self.authorized,
            "args_digest": self.args_digest,
            "response_digest": self.response_digest,
            "side_effect_class": self.side_effect_class,
            "latency_ms": self.latency_ms,
            "idempotency_key": self.idempotency_key,
            "idempotent_replay": self.idempotent_replay,
            "denied_reason": self.denied_reason,
            "error": self.error,
        }


@dataclass(frozen=True)
class ToolResult:
    """A successful tool call. ``untrusted`` marks the output as data, never
    instructions (report 14.3: "mark all server text as untrusted data")."""

    output: dict[str, Any]
    receipt: ToolReceipt
    untrusted: bool = True


@dataclass
class _Registered:
    manifest: ModuleManifest
    provider: ToolProvider


#: How the gateway decides a capability authorizes a call. Defaults to the
#: token's own fail-closed checks; pass a ``CapabilityIssuer.validate``-shaped
#: callable to add revocation awareness.
Authorizer = Callable[[CapabilityToken, str, str, str | None], bool]


def _default_authorize(
    token: CapabilityToken, subject: str, action: str, resource: str | None
) -> bool:
    return token.is_valid(subject=subject) and token.allows(action, resource)


class ToolGateway:
    """Terminates every tool call in the internal capability + receipt model."""

    def __init__(
        self,
        ledger: LedgerLike,
        *,
        egress: EgressPolicy | None = None,
        authorize: Authorizer = _default_authorize,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self._ledger = ledger
        self._egress = egress or EgressPolicy()
        self._authorize = authorize
        self._max_output_bytes = max_output_bytes
        self._tools: dict[str, _Registered] = {}
        self._idempotency: dict[str, ToolResult] = {}

    # -- discovery (separate from authorization) ------------------------------

    def register(self, manifest: ModuleManifest, provider: ToolProvider) -> None:
        """Admit a tool to the catalog. Registration is discovery only: it
        confers no permission to call (report 14.3)."""
        self._tools[provider.tool_id] = _Registered(manifest, provider)
        self._ledger.append(
            Event(
                event_type=EventTypes.TOOL_DISCOVERED,
                actor="tool-gateway",
                payload={"tool_id": provider.tool_id, "version": manifest.version},
            )
        )

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    # -- the guarded call -----------------------------------------------------

    def call(
        self,
        tool_id: str,
        args: dict[str, Any],
        capability: CapabilityToken | None,
        *,
        subject: str,
        action: str | None = None,
        resource: str | None = None,
        mission_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        """Authorize, egress-check, execute and receipt one tool call."""
        registered = self._tools.get(tool_id)
        if registered is None:
            # An unknown tool is denied, not discovered by trying it.
            self._deny(tool_id, "?", subject, mission_id, action or tool_id, resource,
                       capability, args, "tool is not registered")
        assert registered is not None
        act = action or f"tool.{tool_id}"

        # Authorization: deny-by-default (report 14.3).
        if capability is None or not self._authorize(capability, subject, act, resource):
            reason = "no capability presented" if capability is None else (
                "capability does not authorize this action/resource"
            )
            self._deny(tool_id, registered.manifest.version, subject, mission_id, act,
                       resource, capability, args, reason)

        # Egress / SSRF (report 14.3): a named resource must pass before run.
        if resource is not None:
            decision = self._egress.check(resource)
            if not decision.allowed:
                self._deny(tool_id, registered.manifest.version, subject, mission_id, act,
                           resource, capability, args, f"egress denied: {decision.reason}")

        assert capability is not None
        self._emit(EventTypes.TOOL_AUTHORIZED, tool_id, subject, mission_id,
                   {"action": act, "resource": resource, "capability_ref": capability.capability_id})

        # Idempotent replay AFTER authorization: a repeat still must be
        # authorized, but it returns the recorded receipt without re-running
        # the side effect (report 10.2 "non-idempotent retry"). A replay
        # presenting an expired or revoked capability is denied above.
        if idempotency_key is not None and idempotency_key in self._idempotency:
            return self._idempotency[idempotency_key]

        args_digest = content_digest(args)
        started = time.monotonic()
        self._emit(EventTypes.TOOL_CALLED, tool_id, subject, mission_id,
                   {"action": act, "args_digest": args_digest})
        try:
            output = registered.provider.invoke(dict(args))
        except Exception as exc:
            latency = int((time.monotonic() - started) * 1000)
            self._emit(EventTypes.TOOL_RESULT, tool_id, subject, mission_id,
                       {"error": str(exc), "latency_ms": latency})
            raise ToolExecutionError(f"tool {tool_id} failed: {exc}") from exc
        latency = int((time.monotonic() - started) * 1000)

        if not isinstance(output, dict):
            self._emit(EventTypes.TOOL_RESULT, tool_id, subject, mission_id,
                       {"error": "non-dict output", "latency_ms": latency})
            raise ToolExecutionError(f"tool {tool_id} returned {type(output).__name__}, not dict")
        encoded = canonical_json(output)
        if len(encoded) > self._max_output_bytes:
            self._emit(EventTypes.TOOL_RESULT, tool_id, subject, mission_id,
                       {"error": "excessive output", "bytes": len(encoded), "latency_ms": latency})
            raise ToolExecutionError(
                f"tool {tool_id} output {len(encoded)} bytes exceeds the "
                f"{self._max_output_bytes}-byte cap"
            )

        response_digest = content_digest(output)
        receipt = ToolReceipt(
            receipt_id=new_id("rcpt"),
            tool_id=tool_id,
            tool_version=registered.manifest.version,
            subject=subject,
            mission_id=mission_id,
            action=act,
            resource=resource,
            capability_ref=capability.capability_id,
            authorized=True,
            args_digest=args_digest,
            response_digest=response_digest,
            side_effect_class=registered.provider.side_effect_class,
            latency_ms=latency,
            idempotency_key=idempotency_key,
            idempotent_replay=False,
        )
        self._emit(EventTypes.TOOL_RESULT, tool_id, subject, mission_id, receipt.payload())
        if registered.provider.side_effect_class in _SIDE_EFFECTING:
            self._emit(EventTypes.TOOL_SIDE_EFFECT, tool_id, subject, mission_id, receipt.payload())

        result = ToolResult(output=output, receipt=receipt, untrusted=True)
        if idempotency_key is not None:
            self._idempotency[idempotency_key] = result
        return result

    # -- internals ------------------------------------------------------------

    def _deny(
        self,
        tool_id: str,
        version: str,
        subject: str,
        mission_id: str | None,
        action: str,
        resource: str | None,
        capability: CapabilityToken | None,
        args: dict[str, Any],
        reason: str,
    ) -> NoReturn:
        receipt = ToolReceipt(
            receipt_id=new_id("rcpt"),
            tool_id=tool_id,
            tool_version=version,
            subject=subject,
            mission_id=mission_id,
            action=action,
            resource=resource,
            capability_ref=capability.capability_id if capability else None,
            authorized=False,
            args_digest=content_digest(args),
            response_digest=None,
            side_effect_class="none",
            latency_ms=0,
            idempotency_key=None,
            idempotent_replay=False,
            denied_reason=reason,
        )
        self._emit(EventTypes.TOOL_DENIED, tool_id, subject, mission_id, receipt.payload())
        raise ToolDenied(f"{tool_id}: {reason}")

    def _emit(
        self,
        event_type: str,
        tool_id: str,
        subject: str,
        mission_id: str | None,
        payload: dict[str, Any],
    ) -> Event:
        return self._ledger.append(
            Event(
                event_type=event_type,
                mission_id=mission_id,
                actor="tool-gateway",
                subject=subject,
                payload={"tool_id": tool_id, **payload},
            )
        )
