# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Outbound-address policy for the shared HTTP client (#13625).

Split out of :mod:`autobot_shared.http_client` by #15641. The policy is a
decision about *where* a request may go, not about how the session is pooled
or how the singleton is reached, and it is the only part of that module a
caller may want without an ``HTTPClientManager`` at all.

``EgressBlockedError`` and :func:`_assert_egress_allowed` moved here verbatim.
"""

import aiohttp


class EgressBlockedError(aiohttp.ClientError, ValueError):
    """Raised when a guarded request targets an address egress policy forbids.

    #13625: deliberately an ``aiohttp.ClientError`` as well as a ``ValueError``.
    Every connector already wraps its outbound call in
    ``except (RetryableError, aiohttp.ClientError)`` and returns a structured
    error; a bare ``ValueError`` escaped that and handed the operator a traceback
    instead. ``ValueError`` is kept so existing callers of the url-safety layer
    that catch it keep working.
    """


async def _assert_egress_allowed(url: str, *, allow_private: bool, private_network_hint: bool = True) -> None:
    """Refuse a URL that outbound connector traffic must not reach (#13625).

    Imported lazily so ``http_client`` keeps its stdlib+aiohttp dependency
    surface for callers that never opt in. *private_network_hint* names the
    ``AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS`` setting in the message; pass ``False`` where that setting
    has no effect (:data:`EGRESS_POLICY` and :func:`assert_public_egress` hard-code public-only).
    """
    from autobot_shared.url_safety import is_public_url_async

    if await is_public_url_async(url, allow_private=allow_private):
        return
    if private_network_hint:
        advice = (
            "If this is a self-hosted instance on a private network, set "
            "AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS=true."
        )
    else:
        advice = "The target is not public and not on the SSOT internal-origin allowlist."
    raise EgressBlockedError(f"Refusing outbound request to a disallowed address: {url!r}. {advice}")


class _EgressPolicy:
    """Type of :data:`EGRESS_POLICY` — a singleton sentinel, never constructed elsewhere."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "EGRESS_POLICY"


#: ``guard_egress=EGRESS_POLICY`` (#17576 AC4): an origin on the internal
#: allowlist (:mod:`autobot_shared.egress_allowlist`) bypasses the check;
#: anything else must be a public address (``allow_private=False``).
#:
#: **ONLY for server-chosen URLs** (from the SSOT or operator configuration). A URL a user, an LLM
#: or a document supplied must use ``guard_egress=False`` (public-only, no internal trust), or the
#: requester can aim the server at its own services.
EGRESS_POLICY = _EgressPolicy()


async def assert_egress_policy(url: str) -> None:
    """Apply :data:`EGRESS_POLICY` to *url*; raise :class:`EgressBlockedError` if refused.

    For raw clients (aiohttp, httpx, requests, urllib) that do not go through
    ``HTTPClientManager.request``: call it before the request. It does not
    police redirects — a raw caller must disable them itself.
    """
    from autobot_shared.egress_allowlist import is_internal_origin

    if await is_internal_origin(url):
        return
    await _assert_egress_allowed(url, allow_private=False, private_network_hint=False)


async def assert_public_egress(url: str) -> None:
    """Public-only check for a raw client sending to a user-, LLM- or document-supplied *url*.

    The raw-client counterpart of ``guard_egress=False``: no internal-origin trust, so an
    internal service URL the requester supplies is refused. Raises :class:`EgressBlockedError`.
    Like :func:`assert_egress_policy` it does not police redirects -- the caller disables them.
    """
    await _assert_egress_allowed(url, allow_private=False, private_network_hint=False)


async def apply_egress_guard(url: str, guard: "bool | None | _EgressPolicy") -> None:
    """Apply a ``guard_egress`` value: ``None`` (no guard), ``True``/``False`` or :data:`EGRESS_POLICY`.

    Anything else raises ``TypeError`` -- a truthy string or object must not silently pick
    ``allow_private``.
    """
    if guard is None:
        return
    if guard is EGRESS_POLICY:
        await assert_egress_policy(url)
    elif guard is True or guard is False:
        await _assert_egress_allowed(url, allow_private=guard)
    else:
        raise TypeError(f"guard_egress must be None, a bool or EGRESS_POLICY, not {guard!r}")
