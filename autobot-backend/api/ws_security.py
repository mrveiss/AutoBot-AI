# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared WebSocket security helpers.

WebSockets are exempt from the browser same-origin/CORS policy, so a malicious
page can open an authenticated socket using the victim's ambient cookies
(Cross-Site WebSocket Hijacking — CSWSH). :func:`validate_ws_origin` rejects a
cross-origin handshake by checking the ``Origin`` header against the same CORS
allowlist the HTTP layer uses.

Originally added inline to ``api/task_workspace_ws.py`` (#11051); extracted here
so every authenticated WS endpoint can reuse one audited implementation (#11088).
"""

from __future__ import annotations

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def validate_ws_origin(websocket: WebSocket) -> None:
    """Reject cross-origin (CSWSH) WebSocket handshakes — ``Origin`` check only.

    When an ``Origin`` header is present (browser client) it MUST be on the CORS
    allowlist; non-browser clients (native apps, server-to-server, CLI) omit
    ``Origin`` and are not subject to CSWSH, so they are allowed through here.
    Authentication/authorisation is decided separately by each endpoint's own
    auth logic — this only closes the cross-origin hijacking vector.

    Fail-closed: a disallowed or unresolvable ``Origin`` raises ``PermissionError``.
    Callers close the socket with policy-violation code ``1008``.
    """
    origin = websocket.headers.get("origin", "")
    if not origin:
        return  # non-browser client (no Origin) — not subject to CSWSH
    try:
        from config.manager import get_config_manager  # noqa: PLC0415

        allowed = set(get_config_manager().get_cors_origins() or [])
    except Exception:  # config unavailable → fail closed, allow nothing cross-origin
        allowed = set()
    if origin not in allowed:
        raise PermissionError(f"Cross-origin WebSocket handshake rejected: {origin}")


async def enforce_ws_origin(websocket: WebSocket) -> bool:
    """Validate the Origin and, on rejection, close the socket with ``1008``.

    Convenience wrapper for the common pattern: call before ``websocket.accept()``
    (or immediately after, per endpoint) and ``return`` when it yields ``False``.

    Returns ``True`` when the handshake origin is allowed (or absent), ``False``
    after having closed the socket for a cross-origin violation.
    """
    try:
        validate_ws_origin(websocket)
        return True
    except PermissionError as exc:
        logger.warning("Rejected WebSocket handshake: %s", exc)
        try:
            await websocket.close(code=1008)
        except Exception:  # already closed / handshake not completed
            pass
        return False
