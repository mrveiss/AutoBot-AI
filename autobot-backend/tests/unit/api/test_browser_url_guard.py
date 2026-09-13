# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""URL admission for the admin browser surface (#13236 step 5, #15228).

The regex allowlist this replaced was bypassable. Its patterns were anchored at
the start but **not** the end, so any attacker-controlled domain prefixed with
an allowlisted string passed — a lookalike host such as
``github.com.<attacker>`` or ``localhost.<attacker>`` matched.

Those cases come first here, because they are why this is a fix rather than a
tidy-up, and because everything #15228 adds must leave them refused.

#15228 changed two things and deliberately not a third:

* the **refusal message** names the real cause. One sentence used to answer for
  a non-HTTP scheme, an address resolving into private space, and a name that
  does not resolve — and it named a whitelist that #13236 step 5 had deleted;
* **fleet membership** comes from the SLM node registry, not a seven-name
  tuple, so a node the fleet gains is reachable without a code change;
* the **admission rule** is untouched: public by DNS, or an exact parsed-host
  match against loopback or a registry-listed fleet node. Nothing else.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.browser_url_guard import (
    INTERNAL_HOST_EXCEPTIONS,
    REASON_DNS_RESOLUTION_FAILED,
    REASON_PRIVATE_ADDRESS_NOT_IN_FLEET,
    REASON_UNSUPPORTED_SCHEME,
    classify_url,
    is_excepted_internal_host,
    is_url_allowed,
)
from services.fleet_registry import SOURCE_FALLBACK, SOURCE_REGISTRY, FleetSnapshot

_RESOLVER = "services.browser_url_guard.is_public_url_async"
_FLEET = "services.browser_url_guard.fleet_snapshot"
_RESOLVES = "services.browser_url_guard._resolves_at_all"


def _snapshot(*hosts: str, source: str = SOURCE_REGISTRY, reason: str | None = None) -> FleetSnapshot:
    return FleetSnapshot(
        hosts=frozenset(hosts),
        source=source,
        node_count=len(hosts),
        degraded_reason=reason,
    )


def _fleet(*hosts: str, source: str = SOURCE_REGISTRY, reason: str | None = None):
    """Patch the registry read with a fixed snapshot."""
    return patch(_FLEET, AsyncMock(return_value=_snapshot(*hosts, source=source, reason=reason)))


def _not_public():
    """The resolving guard says: not a public address."""
    return patch(_RESOLVER, AsyncMock(return_value=False))


def _public():
    return patch(_RESOLVER, AsyncMock(return_value=True))


def _resolves(value: bool):
    """Whether the *classifier* (not the guard) can resolve the host at all."""
    return patch(_RESOLVES, AsyncMock(return_value=value))


# ------------------------------------------------------------ the bypass


@pytest.mark.parametrize(
    "host",
    [
        "github.com.attacker.test",
        "localhost.attacker.test",
        "127.0.0.1.attacker.test",
        "evil.github.com.attacker.test",
    ],
)
@pytest.mark.asyncio
async def test_lookalike_domains_are_refused(host):
    """Every one of these passed the old prefix-matching allowlist."""
    with _not_public(), _fleet(), _resolves(True):
        assert await is_url_allowed(f"https://{host}/") is False


def test_lookalike_hostnames_are_not_internal_exceptions():
    """The host match is exact — a prefix must not qualify."""
    snapshot = _snapshot("10.99.0.7")
    for host in ("localhost.attacker.test", "127.0.0.1.attacker.test", "notlocalhost", "10.99.0.70"):
        assert is_excepted_internal_host(host, snapshot) is False


# ------------------------------------------------------------ what is allowed


@pytest.mark.asyncio
async def test_a_public_url_is_allowed_without_being_listed():
    """Public hosts no longer need an allowlist entry at all."""
    with _public(), _fleet():
        assert await is_url_allowed("https://example.org/some/page") is True


@pytest.mark.asyncio
async def test_loopback_stays_reachable_for_the_admin_surface():
    """Driving the browser at a local service is what this surface is for."""
    with _not_public(), _fleet():
        for url in ("http://localhost:3000/", "http://127.0.0.1:8000/health"):
            assert await is_url_allowed(url) is True


# ------------------------------------------------------------ #15228: fleet membership


@pytest.mark.asyncio
async def test_a_node_the_registry_reports_is_reachable_without_a_code_change():
    """The whole point of #15227/#15228: membership is data, not a tuple.

    The address below is in none of the seven SSOT attributes the old
    ``_FLEET_HOST_ATTRS`` named. It is reachable purely because the registry
    lists it, which is what "a node added to the fleet appears" means here.
    """
    with _not_public(), _fleet("10.77.4.21", "node-eight"):
        assert await is_url_allowed("http://10.77.4.21:9000/") is True
        assert await is_url_allowed("http://node-eight:9000/") is True


@pytest.mark.asyncio
async def test_a_node_the_registry_stops_reporting_is_refused():
    """...and a node removed disappears, in the same read."""
    with _not_public(), _fleet("10.77.4.21"), _resolves(True):
        assert await is_url_allowed("http://10.77.4.22:9000/") is False


@pytest.mark.asyncio
async def test_an_address_outside_the_fleet_is_still_refused():
    """The security mutation: point the exception source at a non-fleet host.

    Widening the exception set to *fleet* nodes is #15228's job. Making the
    guard permissive is not. With the registry naming one host, every other
    private address must still be refused — including the metadata service and
    a neighbour on the same /24 as the exempt node.
    """
    with _not_public(), _fleet("10.77.4.21"), _resolves(True):
        for url in (
            "http://169.254.169.254/latest/meta-data/",
            "http://10.77.4.22/",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
        ):
            assert await is_url_allowed(url) is False


@pytest.mark.asyncio
async def test_an_empty_registry_exempts_nothing_but_loopback():
    """A fleet of no nodes must not read as a fleet of every node."""
    with _not_public(), _fleet(), _resolves(True):
        assert await is_url_allowed("http://10.77.4.21/") is False
        assert await is_url_allowed("http://localhost/") is True


# ------------------------------------------------------------ #15228: the reason


@pytest.mark.asyncio
async def test_no_refusal_mentions_a_whitelist():
    """The mechanism was deleted in #13236 step 5; the message outlived it.

    An operator reading any of these used to be sent to edit a list that does
    not exist. Whichever cause fires, the word must be gone.
    """
    cases = []
    with _not_public(), _fleet("10.77.4.21"), _resolves(True):
        cases.append(await classify_url("http://10.0.0.5/"))
        cases.append(await classify_url("ftp://example.org/x"))
    with _not_public(), _fleet(), _resolves(False):
        cases.append(await classify_url("http://nowhere.invalid/"))

    for decision in cases:
        assert decision.allowed is False
        assert "whitelist" not in decision.message.lower()
        assert "allowlist" not in decision.message.lower()


@pytest.mark.asyncio
async def test_the_three_causes_are_distinguishable():
    """A scheme problem, a private address and a DNS failure are not one fault.

    They used to produce identical text, so an operator could not tell which
    had happened. Reason code *and* message must differ.
    """
    with _not_public(), _fleet("10.77.4.21"), _resolves(True):
        scheme = await classify_url("ftp://example.org/x")
        private = await classify_url("http://10.0.0.5/")
    with _not_public(), _fleet(), _resolves(False):
        dns = await classify_url("http://nowhere.invalid/")

    assert scheme.reason == REASON_UNSUPPORTED_SCHEME
    assert private.reason == REASON_PRIVATE_ADDRESS_NOT_IN_FLEET
    assert dns.reason == REASON_DNS_RESOLUTION_FAILED
    assert len({scheme.message, private.message, dns.message}) == 3

    assert "ftp" in scheme.message
    assert "non-public" in private.message
    assert "resolved" in dns.message


@pytest.mark.asyncio
async def test_a_degraded_registry_says_so_in_the_refusal():
    """A node enrolled while the SLM was unreachable is refused for a *reason*.

    Silently answering "not a fleet node" from a stale set is the failure mode
    #15227's third criterion is about, one layer down.
    """
    with _not_public(), _fleet("10.1.1.1", source=SOURCE_FALLBACK, reason="registry unreadable"), _resolves(True):
        decision = await classify_url("http://10.77.4.21/")

    assert decision.allowed is False
    assert "degraded" in decision.message.lower()
    assert "registry unreadable" in decision.message


@pytest.mark.asyncio
async def test_a_healthy_registry_does_not_claim_degradation():
    """The vacuity check on the test above: the note is conditional, not always on."""
    with _not_public(), _fleet("10.1.1.1"), _resolves(True):
        decision = await classify_url("http://10.77.4.21/")

    assert "degraded" not in decision.message.lower()
    assert "SLM node registry" in decision.message


# ------------------------------------------------------------ scheme + shape


@pytest.mark.asyncio
async def test_non_http_schemes_are_refused_before_resolving():
    with patch(_RESOLVER, AsyncMock(return_value=True)) as resolver, _fleet():
        assert await is_url_allowed("ftp://example.org/x") is False
        assert await is_url_allowed("javascript:alert(1)") is False

    resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_malformed_url_is_refused_not_raised():
    with _not_public(), _fleet():
        assert await is_url_allowed("") is False
        assert await is_url_allowed("not a url") is False


@pytest.mark.asyncio
async def test_a_guard_that_cannot_answer_refuses():
    """Fail closed: an exception inside the resolving guard is not an approval."""
    with patch(_RESOLVER, AsyncMock(side_effect=RuntimeError("resolver down"))), _fleet("10.77.4.21"):
        decision = await classify_url("http://10.77.4.21/")

    assert decision.allowed is False
    assert decision.reason == REASON_DNS_RESOLUTION_FAILED


def test_the_exception_set_is_explicit_and_small():
    """It is a security control — it should be readable at a glance."""
    assert INTERNAL_HOST_EXCEPTIONS == frozenset({"localhost", "127.0.0.1", "::1"})
