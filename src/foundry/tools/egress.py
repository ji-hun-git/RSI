"""Outbound egress policy for the tool gateway (report section 14.3).

The report's SSRF control: "Apply outbound DNS, domain, method and path
restrictions where possible; block metadata and internal-network targets."
This checks a requested resource's host against a deny list of internal
address ranges and, when configured, an explicit domain allowlist.

Honest scoping: this vets the *literal* host in the resource. A production
egress proxy must additionally resolve DNS and pin the resolved address to
defeat DNS-rebinding; that belongs behind this same interface at a higher
assurance stage, not in a Stage-2 in-process check.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata", "metadata.google.internal"})


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class EgressPolicy:
    """Deny-by-default-for-internal outbound policy.

    ``allow_domains`` empty means any non-internal host is permitted;
    when set, the host must equal or be a subdomain of an allowed domain
    (an allowlist, report 14.3).
    """

    allow_domains: tuple[str, ...] = ()

    def check(self, resource: str) -> EgressDecision:
        host = self._host(resource)
        if not host:
            return EgressDecision(False, f"no host in resource {resource!r}")
        if host.lower() in _BLOCKED_HOSTNAMES:
            return EgressDecision(False, f"blocked internal host {host!r}")
        literal = self._as_ip(host)
        if literal is not None and (
            literal.is_private
            or literal.is_loopback
            or literal.is_link_local  # 169.254/16 covers cloud metadata
            or literal.is_reserved
            or literal.is_multicast
            or literal.is_unspecified
        ):
            return EgressDecision(False, f"blocked internal address {host!r}")
        if self.allow_domains and not self._in_allowlist(host):
            return EgressDecision(False, f"host {host!r} not in egress allowlist")
        return EgressDecision(True, "ok")

    def _in_allowlist(self, host: str) -> bool:
        host = host.lower()
        return any(host == d.lower() or host.endswith("." + d.lower()) for d in self.allow_domains)

    @staticmethod
    def _host(resource: str) -> str:
        parsed = urlparse(resource)
        if parsed.hostname:
            return parsed.hostname
        # bare host (no scheme): strip any path/port
        return resource.split("/")[0].split(":")[0]

    @staticmethod
    def _as_ip(host: str) -> ipaddress._BaseAddress | None:
        try:
            return ipaddress.ip_address(host)
        except ValueError:
            return None
