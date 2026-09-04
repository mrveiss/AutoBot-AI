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


async def _assert_egress_allowed(url: str, *, allow_private: bool) -> None:
    """Refuse a URL that outbound connector traffic must not reach (#13625).

    Imported lazily so ``http_client`` keeps its stdlib+aiohttp dependency
    surface for callers that never opt in.
    """
    from autobot_shared.url_safety import is_public_url_async

    if not await is_public_url_async(url, allow_private=allow_private):
        raise EgressBlockedError(
            f"Refusing outbound request to a disallowed address: {url!r}. "
            "If this is a self-hosted instance on a private network, set "
            "AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS=true."
        )
