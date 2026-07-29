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
import os

from fastapi import WebSocket
from autobot_shared.auth.permissions import is_admin_role

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


def authenticate_ws_admin(websocket: WebSocket) -> bool:
    """Fail-closed auth+authz for admin WS endpoints: a valid user (JWT/session/
    cookie) or the internal-service key, AND admin role — matching the REST
    endpoints' ``Depends(check_admin_permission)``.

    A WebSocket exposes the same ``headers``/``cookies`` interface as a Request,
    so the standard auth middleware resolves the caller. Any error → deny.

    Originally added inline to ``api/task_workspace_ws.py`` (#11051); extracted
    here so every admin WS endpoint reuses one audited implementation (#12178).
    """
    # Dev/test escape hatch: when WS auth is explicitly disabled, allow the
    # connection. Production defaults to "1", so full auth is required.
    if os.environ.get("AUTOBOT_REQUIRE_WS_AUTH", "1") != "1":
        return True
    try:
        from auth_middleware import (  # noqa: PLC0415
            get_auth_middleware,
            verify_internal_api_key,
        )

        if verify_internal_api_key(websocket.headers.get("X-Internal-API-Key")):
            return True
        user = get_auth_middleware().get_user_from_request(websocket)  # type: ignore[arg-type]
        if not user:
            return False
        return is_admin_role(user.get("role"))
    except Exception:
        logger.warning("WS admin auth error — denying", exc_info=True)
        return False


async def enforce_ws_admin(websocket: WebSocket) -> bool:
    """Enforce admin auth and, on rejection, accept then close with ``4001``.

    Call before the endpoint's own ``websocket.accept()`` and ``return`` when
    this yields ``False``. On rejection this accepts the handshake itself so
    the client receives a real WS close frame (code + reason) instead of an
    HTTP 403 that's indistinguishable from a missing route (#12366 — matches
    ``live_events.py``'s accept-then-close convention).

    Returns ``True`` when the caller is an authenticated admin (or WS auth is
    disabled for dev/test), ``False`` after having accepted then closed the
    socket ``4001``.
    """
    if authenticate_ws_admin(websocket):
        return True
    try:
        await websocket.accept()
        await websocket.close(code=4001, reason="Authentication required (admin)")
    except Exception:  # already closed / handshake not completed
        pass
    return False
