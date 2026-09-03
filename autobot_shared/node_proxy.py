# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One client for every SLM -> node call (#14886).

``autobot-slm-backend/api/`` grew three near-identical proxies —
``voice_proxy``, ``personality_proxy``, ``memory_lifecycle_proxy`` — each
independently re-deriving the node URL, the internal API key, a TLS-verify
flag, a timeout, the ``X-Internal-API-Key`` header, and a mapping from
transport failure to response.

That is not a tidiness argument. Building the third one (#12632) by copying the
first inverted its TLS default: the new module read its own
``AUTOBOT_NODE_PROXY_VERIFY_TLS`` with a ``"false"`` default, shipping
verification **off** unless an operator opted in — on the channel that carries
the internal API key. Review caught it one commit before merge (#14653). A
hand-copied pattern is a pattern that can be copied wrong, and every copy is a
place where a security default can silently invert. A shared client makes that
class of mistake impossible instead of merely reviewable.

This module is the union of what the three could do, not the smallest of them:

===========================  ==========================================
Capability                   Came from
===========================  ==========================================
``AUTOBOT_BACKEND_URL``      all three
trailing-slash normalising   ``memory_lifecycle_proxy`` only
``AUTOBOT_INTERNAL_API_KEY`` all three
verify-by-default TLS        all three (the polarity from #14653)
env-backed timeout           ``memory_lifecycle_proxy`` only
``X-Internal-API-Key``       all three
``Content-Type`` passthrough ``voice_proxy`` / ``personality_proxy``
connect failure -> 503       ``voice_proxy`` / ``personality_proxy``
timeout -> 504               ``voice_proxy`` / ``personality_proxy``
catch-all ``HTTPError``      ``memory_lifecycle_proxy`` only
===========================  ==========================================

Egress policy (#14886, #13625): these calls are NOT routed through
``guard_egress``/``ssrf_guard``. Rule 8's origin audit scoped the guarded fetch
to connectors whose host comes from *customer* configuration; a control-plane
to node call's host comes from operator-set deployment config and never from a
request body. Decided once, here, rather than per proxy — the documented entry
is in ``docs/developer/ARCHITECTURE_EXCEPTIONS.md``.

``httpx`` is imported inside the functions that need it, not at module scope,
so the env-policy helpers above stay importable — and testable — anywhere in
the repo, including trees where ``httpx`` is not installed.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from autobot_shared.tls import tls_verify_enabled

#: Explicit node base URL. Overrides the caller's identity-authority default.
NODE_URL_ENV = "AUTOBOT_BACKEND_URL"

#: Shared secret the node trusts in place of a node-issued JWT.
INTERNAL_KEY_ENV = "AUTOBOT_INTERNAL_API_KEY"

#: Per-request timeout for node calls, in seconds.
TIMEOUT_ENV = "AUTOBOT_NODE_PROXY_TIMEOUT_SECONDS"

#: Used when TIMEOUT_ENV is unset or unparseable. Was a bare ``15.0`` literal in
#: two of the three proxies; only the third made it configurable, so the union
#: takes the configurable form.
DEFAULT_TIMEOUT_SECONDS = 15.0

#: Header the node's internal-auth dependency reads.
INTERNAL_KEY_HEADER = "X-Internal-API-Key"

REASON_KEY_NOT_CONFIGURED = "internal_api_key_not_configured"
REASON_URL_NOT_CONFIGURED = "node_url_not_configured"
REASON_TIMEOUT = "node_timeout"
REASON_UNREACHABLE = "node_unreachable"

#: Client-facing wording for each transport failure, so two proxies mapping the
#: same failure cannot describe it two different ways. Verbatim from
#: ``voice_proxy``/``personality_proxy``, which already shipped these strings.
FAILURE_DETAIL = {
    REASON_TIMEOUT: "Main backend timeout",
    REASON_UNREACHABLE: "Main backend unreachable",
}


class NodeTransportError(Exception):
    """A node call that never produced a response, carrying both mappings.

    A passthrough proxy needs an HTTP status to re-raise; an aggregator needs a
    machine-readable reason for its degraded payload. The two proxy families
    used to derive these separately from the same exception, which is how
    ``voice_proxy`` ended up mapping only ``ConnectError`` — a ``ReadError`` or
    a protocol failure escaped it as an unhandled 500.
    """

    def __init__(self, reason: str, status_code: int, detail: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code
        self.detail = detail


def resolve_node_url(fallback: str = "") -> str:
    """The node's base URL, without a trailing slash.

    Args:
        fallback: The caller's identity-authority base (#10197/#10263), used
            when ``AUTOBOT_BACKEND_URL`` is unset so a co-located install needs
            no extra config. Passed in rather than read here because it comes
            from each service's own ``config.settings``.

    Returns:
        The base URL, or ``""`` when neither source is configured — callers
        report that as :data:`REASON_URL_NOT_CONFIGURED` rather than building a
        request against an empty host.
    """
    return (os.getenv(NODE_URL_ENV, "") or fallback or "").rstrip("/")  # noqa: ssot-fallback


def internal_api_key() -> str:
    """The internal API key, or ``""`` when it is not configured."""
    return os.getenv(INTERNAL_KEY_ENV, "")


def node_timeout() -> float:
    """Per-request timeout in seconds; the default when the var is unusable."""
    try:
        return float(os.getenv(TIMEOUT_ENV, "") or DEFAULT_TIMEOUT_SECONDS)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def verify_tls() -> bool:
    """Whether to verify the node's certificate — on unless opted out (#14653)."""
    return tls_verify_enabled()


def internal_headers(content_type: Optional[str] = None) -> Dict[str, str]:
    """Headers for a node call: the internal key, plus a forwarded content type."""
    headers = {INTERNAL_KEY_HEADER: internal_api_key()}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def node_client(**overrides: Any) -> Any:
    """An ``httpx.AsyncClient`` configured by policy, not by each caller.

    TLS verification and the timeout come from this module, so adding a fourth
    node proxy requires no decision about either. ``overrides`` is for a caller
    with a genuinely different need (a long-poll, say) and is deliberately
    awkward enough to show up in review.
    """
    import httpx

    settings: Dict[str, Any] = {"verify": verify_tls(), "timeout": node_timeout()}
    settings.update(overrides)
    return httpx.AsyncClient(**settings)


def classify_transport_error(exc: BaseException) -> NodeTransportError:
    """Map an httpx transport failure onto a reason and an HTTP status.

    Total by construction: anything that is not a timeout is reported as
    unreachable rather than escaping as a 500, which is the ``HTTPError``
    catch-all only ``memory_lifecycle_proxy`` had.
    """
    import httpx

    if isinstance(exc, httpx.TimeoutException):
        return NodeTransportError(REASON_TIMEOUT, 504, FAILURE_DETAIL[REASON_TIMEOUT])
    return NodeTransportError(REASON_UNREACHABLE, 503, FAILURE_DETAIL[REASON_UNREACHABLE])
