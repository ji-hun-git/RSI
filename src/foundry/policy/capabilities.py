"""Capability issuance, validation and revocation (report 10.1, 14.1).

The Capability Issuer is a deterministic governance component: it mints
short-lived, scoped, non-transferable ``CapabilityToken`` grants and is
the only party that can revoke them. Validation is fail-closed on every
axis the report names for token testing (scope, expiry, replay-by-other-
subject, revocation). Stage 1 keeps revocation state in-process; tokens
carry no signature field yet, so the optional signer only stamps issuer
identity (asymmetric attestation is Stage-2 work).
"""

from __future__ import annotations

from datetime import datetime

from foundry.contracts import CapabilityToken
from foundry.registry.signing import HMACSigner


class CapabilityIssuer:
    """Mints and validates bounded, auditable capability grants."""

    def __init__(self, signer: HMACSigner | None = None) -> None:
        self._signer = signer
        self._revoked: set[str] = set()

    @property
    def issuer_name(self) -> str:
        if self._signer is None:
            return "capability-issuer"
        return f"capability-issuer:{self._signer.key_id}"

    def issue(
        self,
        subject: str,
        actions: list[str],
        resource_scopes: list[str],
        ttl_seconds: int,
        mission_id: str | None = None,
    ) -> CapabilityToken:
        return CapabilityToken(
            subject=subject,
            mission_id=mission_id,
            actions=list(actions),
            resource_scopes=list(resource_scopes),
            ttl_seconds=ttl_seconds,
            issuer=self.issuer_name,
        )

    def validate(
        self,
        token: CapabilityToken,
        *,
        subject: str,
        action: str,
        resource: str | None = None,
        at: datetime | None = None,
    ) -> bool:
        """Fail-closed check: revocation, expiry, subject binding, action and scope."""
        if token.capability_id in self._revoked:
            return False
        if not token.is_valid(at=at, subject=subject):
            return False
        return token.allows(action, resource)

    def revoke(self, capability_id: str) -> None:
        self._revoked.add(capability_id)
