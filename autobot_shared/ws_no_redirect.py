# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A ``websockets`` client connect that never follows a handshake redirect (#17576, AC4).

``websockets.asyncio.client.connect`` (websockets 15.x) follows 3xx handshake responses that carry
a ``Location`` header, up to ``WEBSOCKETS_MAX_REDIRECTS`` hops, and its only cross-origin refusals
concern a preset ``sock``/``unix``/``host`` override -- an ordinary ``wss://`` redirect to another
host is followed. A caller that checked its first URL with :func:`assert_egress_policy` would then
be sent anywhere. The library has no per-connection switch, so the redirect decision is overridden
here: ``process_redirect`` returns the original exception, which ``connect`` re-raises
(``InvalidStatus``, a ``WebSocketException``).
"""

from __future__ import annotations

from websockets.asyncio.client import connect


class NoRedirectConnect(connect):
    """``websockets`` client ``connect`` whose handshake redirects are surfaced, not followed."""

    def process_redirect(self, exc: Exception) -> Exception | str:
        """Never a redirect target: hand the original exception back so it is raised."""
        return exc


connect_no_redirect = NoRedirectConnect
