"""Egress / SSRF policy with resolve-and-pin (report 14.3).

The load-bearing case is DNS-rebinding defense: a hostname that is not
literally an internal IP but *resolves* to one must be refused, and the
vetted addresses are returned so a caller can pin the connection.
"""

from __future__ import annotations

import pytest

from foundry.tools import EgressPolicy, system_resolver


def fake_resolver(mapping: dict[str, list[str]]):
    def resolve(host: str) -> list[str]:
        if host not in mapping:
            raise OSError(f"no such host {host}")
        return mapping[host]

    return resolve


# -- literal-host checks (unchanged without a resolver) -----------------------


@pytest.mark.parametrize(
    "resource",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1/x",
        "http://10.1.2.3/",
        "http://192.168.0.1/",
        "http://localhost/x",
    ],
)
def test_literal_internal_targets_are_blocked(resource: str) -> None:
    assert not EgressPolicy().check(resource).allowed


def test_public_literal_ip_is_allowed_and_pinned() -> None:
    decision = EgressPolicy().check("http://93.184.216.34/x")
    assert decision.allowed
    assert decision.resolved_ips == ("93.184.216.34",)


def test_no_resolver_vets_literal_host_only() -> None:
    # without a resolver, a hostname is allowed on its literal form (no DNS)
    decision = EgressPolicy().check("https://example.com/x")
    assert decision.allowed and decision.resolved_ips == ()


# -- resolve-and-pin ----------------------------------------------------------


def test_hostname_resolving_to_metadata_is_blocked() -> None:
    policy = EgressPolicy(resolver=fake_resolver({"evil.test": ["169.254.169.254"]}))
    decision = policy.check("http://evil.test/pwn")
    assert not decision.allowed
    assert "resolves to internal address" in decision.reason


def test_hostname_resolving_to_private_range_is_blocked() -> None:
    policy = EgressPolicy(resolver=fake_resolver({"rebind.test": ["10.0.0.5"]}))
    assert not policy.check("http://rebind.test/x").allowed


def test_any_internal_answer_blocks_a_rebinding_host() -> None:
    # one public + one metadata answer: the internal one blocks the request
    policy = EgressPolicy(resolver=fake_resolver({"multi.test": ["8.8.8.8", "169.254.169.254"]}))
    assert not policy.check("http://multi.test/x").allowed


def test_public_hostname_is_allowed_and_returns_pinned_ips() -> None:
    policy = EgressPolicy(resolver=fake_resolver({"api.example.com": ["93.184.216.34"]}))
    decision = policy.check("https://api.example.com/v1")
    assert decision.allowed
    assert decision.resolved_ips == ("93.184.216.34",)


def test_unresolvable_host_fails_closed() -> None:
    policy = EgressPolicy(resolver=fake_resolver({}))
    decision = policy.check("https://nonexistent.test/x")
    assert not decision.allowed and "could not resolve" in decision.reason


def test_resolver_and_allowlist_compose() -> None:
    policy = EgressPolicy(
        allow_domains=("example.com",),
        resolver=fake_resolver({"api.example.com": ["93.184.216.34"], "evil.test": ["8.8.8.8"]}),
    )
    assert policy.check("https://api.example.com/x").allowed
    # allowlist rejects the off-domain host before resolution even matters
    assert not policy.check("https://evil.test/x").allowed


def test_hostname_resolving_to_a_non_address_is_refused() -> None:
    policy = EgressPolicy(resolver=fake_resolver({"weird.test": ["not-an-ip"]}))
    assert not policy.check("http://weird.test/x").allowed


# -- production resolver ------------------------------------------------------


def test_system_resolver_resolves_localhost_to_loopback() -> None:
    ips = system_resolver("localhost")
    assert ips  # resolves to at least one address
    assert any(ip in ("127.0.0.1", "::1") for ip in ips)
    # a policy using the real resolver would therefore block localhost by name
    policy = EgressPolicy(resolver=system_resolver)
    # "localhost" is caught by the hostname blocklist first, but a resolved
    # loopback proves the resolve-and-pin path would also catch it
    assert not policy.check("http://127.0.0.1/x").allowed
