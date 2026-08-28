# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which URLs the admin browser surface may open, and why one was refused.

Extracted from ``api/browser_mcp.py`` (#15228). Two things changed with the
move; the admission rule itself did not.

**The rejection message names the real reason.** ``/browser/mcp/navigate``
answered every refusal with ``URL not in whitelist``. #13236 step 5 deleted the
whitelist — there is no list to be off — so the message sent operators to edit
a mechanism that no longer exists, and collapsed three unrelated causes into
one sentence: a non-HTTP scheme, an address resolving into private space with
no matching exception, and a name that does not resolve at all. Each now has
its own reason code and its own message.

**Fleet membership comes from the SLM node registry**, not a literal tuple of
seven SSOT attribute names, so a node the fleet gains is reachable from this
tool without a code change (#15227 is the same defect on the terminal's host
selector, answered from the same authority).

The admission rule, unchanged from #13236 step 5:

* non-HTTP schemes are refused before anything resolves;
* any URL resolving to a **public** address is permitted, via
  ``is_public_url_async`` — the DNS-resolving guard, so a hostname resolving
  into private space is rejected however it is spelled;
* a **non**-public address is permitted only when its parsed hostname is an
  explicit internal exception: loopback, or a host the SLM registry reports as
  a fleet node.

That replaced a prefix-matching regex allowlist which was bypassable: its
patterns had no end anchor, so a lookalike host such as ``github.com.<attacker>``
or ``localhost.<attacker>`` passed. Nothing here may reintroduce
a substring, prefix or suffix match against the URL or the hostname — the
comparison is equality against a parsed hostname, and that is the fix.

Classifying *why* a URL was refused deliberately runs only after the decision
to refuse has already been made, and cannot change it.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from autobot_shared.logging_manager import get_logger
from autobot_shared.url_safety import is_public_url_async
from services.fleet_registry import FleetSnapshot, fleet_snapshot

logger = get_logger(__name__)

#: Performance: O(1) lookup for allowed URL schemes (Issue #326).
ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

#: Internal hosts this ADMIN surface may reach regardless of the fleet.
#:
#: Kept because reaching internal services is what this surface is *for*:
#: pointing the browser at one and reading what the page requests is how wrong
#: API calls get found and callers mapped to the right routes. Matched against
#: the parsed hostname, never against the raw URL string.
INTERNAL_HOST_EXCEPTIONS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

#: Reason codes. Stable strings — logs, the 403 body and the tests all key off
#: these, so an operator reading a refusal and a test pinning it agree.
REASON_ALLOWED = "allowed"
REASON_MALFORMED_URL = "malformed_url"
REASON_UNSUPPORTED_SCHEME = "unsupported_scheme"
REASON_PRIVATE_ADDRESS_NOT_IN_FLEET = "private_address_not_in_fleet"
REASON_DNS_RESOLUTION_FAILED = "dns_resolution_failed"

#: Seconds allowed for the classification lookup. This resolves a name the
#: admission guard has *already* refused, purely to tell the operator whether
#: it failed to resolve or resolved somewhere private, so it must never
#: outlast the request it is explaining.
_CLASSIFY_DNS_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class UrlDecision:
    """Whether the URL may be opened, and the reason an operator gets."""

    allowed: bool
    reason: str
    message: str


def is_excepted_internal_host(hostname: str, snapshot: FleetSnapshot) -> bool:
    """True if *hostname* is an internal host this admin surface may reach.

    Matches the **parsed hostname**, exactly — never a substring of the URL.
    That is the difference from the regex allowlist this replaced, under which
    a lookalike such as ``localhost.<attacker>`` was allowed. The fleet half
    is passed in rather than fetched here, so the caller reports membership
    from the same snapshot it decided on.
    """
    host = (hostname or "").strip("[]").lower()
    if not host:
        return False
    if host in INTERNAL_HOST_EXCEPTIONS:
        return True
    return host in snapshot.hosts


async def _resolves_at_all(host: str) -> bool:
    """True if *host* resolves to anything; used only to explain a refusal.

    An IP literal always "resolves". Any lookup failure — NXDOMAIN, timeout,
    a broken resolver — reads as not resolving, because from the operator's
    seat those are the same problem: the name did not turn into an address.
    """
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, None, type=socket.SOCK_STREAM),
            timeout=_CLASSIFY_DNS_TIMEOUT_SECONDS,
        )
    except (socket.gaierror, OSError, asyncio.TimeoutError, ValueError):
        return False
    return bool(infos)


def _scheme_message(scheme: str) -> str:
    return f"Refused: '{scheme or 'none'}' is not a browsable scheme. " "This tool opens http and https URLs only."


def _private_message(host: str, snapshot: FleetSnapshot) -> str:
    """Say it resolved somewhere private, and say where membership came from."""
    provenance = (
        f"Fleet membership is currently degraded to configured hosts ({snapshot.degraded_reason}), "
        "so a recently enrolled node may not be recognised yet."
        if snapshot.is_degraded
        else f"Fleet membership came from the SLM node registry ({snapshot.node_count} nodes)."
    )
    return (
        f"Refused: '{host}' resolves to a non-public address and is neither a loopback host "
        f"nor a node the fleet registry knows. {provenance}"
    )


def _dns_message(host: str) -> str:
    return (
        f"Refused: '{host}' could not be resolved, so the address it points at is unknown. "
        "Check the name, or that this host's resolver can see it."
    )


async def classify_url(url: str) -> UrlDecision:
    """Decide whether *url* may be opened, and say why when it may not.

    The decision is exactly ``is_url_allowed``'s; the classification below it
    runs only on the refusal path and cannot turn a refusal into an approval.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        logger.warning("Blocked unparseable browser URL")
        return UrlDecision(False, REASON_MALFORMED_URL, "Refused: that is not a URL this tool can parse.")

    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        logger.warning("Blocked non-HTTP scheme: %s", parsed.scheme)
        return UrlDecision(False, REASON_UNSUPPORTED_SCHEME, _scheme_message(parsed.scheme))

    host = (parsed.hostname or "").strip("[]").lower()
    if not host:
        logger.warning("Blocked browser URL with no host")
        return UrlDecision(False, REASON_MALFORMED_URL, "Refused: that URL names no host to open.")

    try:
        if await is_public_url_async(url):
            return UrlDecision(True, REASON_ALLOWED, "")
    except Exception as exc:  # a guard that cannot answer refuses (#13236)
        logger.error("URL validation error: %s", exc)
        return UrlDecision(False, REASON_DNS_RESOLUTION_FAILED, _dns_message(host))

    snapshot = await fleet_snapshot()
    if is_excepted_internal_host(host, snapshot):
        logger.info("Allowing admin browser navigation to internal host: %s", host)
        return UrlDecision(True, REASON_ALLOWED, "")

    if not await _resolves_at_all(host):
        logger.warning("Blocked browser navigation: host does not resolve")
        return UrlDecision(False, REASON_DNS_RESOLUTION_FAILED, _dns_message(host))

    logger.warning("Blocked browser navigation to non-public host outside the fleet")
    return UrlDecision(False, REASON_PRIVATE_ADDRESS_NOT_IN_FLEET, _private_message(host, snapshot))


async def is_url_allowed(url: str) -> bool:
    """Boolean face of :func:`classify_url`, kept for existing call sites."""
    return (await classify_url(url)).allowed
