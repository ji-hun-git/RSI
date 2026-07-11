"""Outbound egress policy for the tool gateway (report section 14.3).

The report's SSRF control: "Apply outbound DNS, domain, method and path
restrictions where possible; block metadata and internal-network targets."
This checks a requested resource's host against a deny list of internal
address ranges and, when configured, an explicit domain allowlist.

Resolve-and-pin (report 14.3, defeating DNS rebinding): a literal-host
check alone is bypassable -- an attacker registers ``evil.test`` and points
its DNS at ``169.254.169.254``. When a ``resolver`` is supplied, the policy
resolves the hostname, refuses the request if *any* resolved address is
internal, and returns the resolved addresses so the caller can pin the
connection to exactly what was vetted (rather than re-resolving, where a
second answer could rebind to an internal host). The resolver is injected
so the check stays deterministic and offline in tests; :func:`system_resolver`
is the production DNS-backed resolver.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata", "metadata.google.internal"})

#: host -> list of resolved IP strings.
Resolver = Callable[[str], list[str]]


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    reason: str
    resolved_ips: tuple[str, ...] = ()  # the vetted addresses, for connection pinning


def _is_internal(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # 169.254/16 covers cloud metadata
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def system_resolver(host: str) -> list[str]:
    """Production DNS resolver (real ``getaddrinfo``). Not used in tests."""
    infos = socket.getaddrinfo(host, None)
    return sorted({info[4][0] for info in infos})


@dataclass(frozen=True)
class EgressPolicy:
    """Deny-by-default-for-internal outbound policy.

    ``allow_domains`` empty means any non-internal host is permitted; when
    set, the host must equal or be a subdomain of an allowed domain (an
    allowlist, report 14.3). ``resolver`` enables resolve-and-pin: without
    it the check vets the literal host only; with it, the hostname is
    resolved and refused if any resolved address is internal.
    """

    allow_domains: tuple[str, ...] = ()
    resolver: Resolver | None = field(default=None)

    def check(self, resource: str) -> EgressDecision:
        host = self._host(resource)
        if not host:
            return EgressDecision(False, f"no host in resource {resource!r}")
        if host.lower() in _BLOCKED_HOSTNAMES:
            return EgressDecision(False, f"blocked internal host {host!r}")

        literal = self._as_ip(host)
        if literal is not None:
            if _is_internal(literal):
                return EgressDecision(False, f"blocked internal address {host!r}")
        if self.allow_domains and not self._in_allowlist(host):
            return EgressDecision(False, f"host {host!r} not in egress allowlist")

        resolved: tuple[str, ...] = ()
        if literal is not None:
            resolved = (host,)
        elif self.resolver is not None:
            decision = self._resolve_and_check(host)
            if not decision.allowed:
                return decision
            resolved = decision.resolved_ips
        return EgressDecision(True, "ok", resolved_ips=resolved)

    def _resolve_and_check(self, host: str) -> EgressDecision:
        try:
            addresses = list(self.resolver(host)) if self.resolver else []
        except Exception as exc:  # fail-closed: an unresolvable host is refused
            return EgressDecision(False, f"could not resolve host {host!r}: {exc}")
        if not addresses:
            return EgressDecision(False, f"host {host!r} resolved to no address")
        for address in addresses:
            ip = self._as_ip(address)
            if ip is None:
                return EgressDecision(False, f"host {host!r} resolved to non-address {address!r}")
            if _is_internal(ip):
                return EgressDecision(
                    False, f"host {host!r} resolves to internal address {address}"
                )
        return EgressDecision(True, "ok", resolved_ips=tuple(addresses))

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
