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
from typing import TYPE_CHECKING

from fastapi import WebSocket

from autobot_shared.auth.device_capabilities import DeviceCapability
from autobot_shared.auth.permissions import is_admin_role

if TYPE_CHECKING:  # pragma: no cover - typing only
    from services.device_capabilities import DeviceCapabilityDecision

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


async def _resolve_ws_user(websocket: WebSocket) -> "dict | None":
    """Try every credential source a caller might legitimately present.

    A browser JS client can only put a JWT in the query string -- it cannot
    set custom headers on a WebSocket handshake -- so the query-param check
    (:func:`auth_middleware.authenticate_websocket`) goes first. A
    non-browser or service caller may instead send an ``Authorization``
    header, an ``X-Session-ID`` session header, a dev-mode header, or the
    internal-service key; ``get_user_from_request`` and
    ``verify_internal_api_key`` already resolve those for HTTP requests, and
    a WebSocket exposes the same ``headers``/``cookies`` interface
    (``authenticate_ws_admin`` relies on the same fact). Trying each in turn
    is a union of the accepted checks -- more ways to prove identity, not a
    looser standard for any one of them (#11016 documents the identical
    query-only lockout for the admin workspace shell).
    """
    from auth_middleware import (  # noqa: PLC0415
        authenticate_websocket,
        get_auth_middleware,
        verify_internal_api_key,
    )

    user = await authenticate_websocket(websocket)
    if user is not None:
        return user
    if verify_internal_api_key(websocket.headers.get("X-Internal-API-Key")):
        return {"username": "service:slm", "role": "admin", "service": True}
    return get_auth_middleware().get_user_from_request(websocket)  # type: ignore[arg-type]


async def enforce_ws_authentication(websocket: WebSocket) -> "dict | None":
    """Authenticate a WebSocket handshake and, on failure, close with ``1008``.

    Convenience wrapper mirroring :func:`enforce_ws_origin`: call before
    ``websocket.accept()`` and ``return`` when this yields ``None``. Closing
    before ``accept()`` rejects the handshake itself rather than the socket
    accepting then tearing down mid-stream (#14959, #14960, #14991).

    Returns the authenticated user dict, or ``None`` after having closed the
    socket for a missing or invalid credential.
    """
    user = await _resolve_ws_user(websocket)
    if user is None:
        logger.warning("Rejected unauthenticated WebSocket handshake")
        try:
            await websocket.close(code=1008, reason="Authentication required")
        except Exception:  # already closed / handshake not completed
            pass
        return None
    return user


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


async def _resolve_ws_device_credential(websocket: WebSocket) -> "dict | None":
    """Resolve a paired-device credential from the handshake, or ``None`` (#14964).

    A device JWT travels in the ``Authorization`` header, which a browser
    cannot set on a WebSocket handshake but a native paired app can. Validation
    is the canonical one (``auth_middleware._extract_user_from_device_jwt`` →
    ``services.device_jwt.validate_device_jwt``): signature, audience, expiry,
    device still paired and not revoked. This adds no new way to prove
    identity — it only lets the capability gate below see a credential that
    would otherwise have been refused as merely "unauthenticated".
    """
    from auth_middleware import get_auth_middleware  # noqa: PLC0415

    try:
        credential = await get_auth_middleware()._extract_user_from_device_jwt(websocket)  # type: ignore[arg-type]
    except Exception:
        # A resolution failure is a handshake with no device credential, never
        # an exception escaping into the endpoint's error boundary -- there it
        # would become a 500 and leave the socket hanging instead of refused.
        logger.warning("Device credential resolution failed — treating handshake as credential-less", exc_info=True)
        return None
    return credential if isinstance(credential, dict) else None


async def enforce_ws_remote_control_auth(
    websocket: WebSocket,
    *required: "DeviceCapability",
) -> "dict | None":
    """Authenticate a remote-control handshake, capability-scoping device credentials (#14964).

    A handshake carrying no device credential is delegated verbatim to
    :func:`enforce_ws_authentication` — nothing changes for a user, session or
    service caller. A *paired-device* credential must additionally hold every
    capability in ``required``, asserted positively against its own grant set.
    It is never granted by fall-through: an empty ``required``, an unreadable
    grant set, an unapproved or revoked credential, and a capability the
    platform does not define all refuse.

    The device credential is examined first on purpose. A caller presenting
    both a device JWT and a user credential is held to the stricter of the two
    standards, the same way ``services/feature_flags.combine_enforcement_modes``
    resolves a global mode against a per-endpoint override.

    Revocation and grant changes take effect on the **next** handshake: this
    runs once, before ``accept()``. A socket already open is not
    re-authenticated and stays up until it closes or the process ends.

    Returns the authenticated credential's user dict, or ``None`` after having
    closed the socket with ``1008``.
    """
    device_user = await _resolve_ws_device_credential(websocket)
    if device_user is None:
        # No device credential presented — the ordinary path, unchanged.
        return await enforce_ws_authentication(websocket)

    from services.device_capabilities import evaluate_device_capabilities  # noqa: PLC0415

    device_id = str(device_user.get("device_id", ""))
    decision = (
        await evaluate_device_capabilities(device_id, required)
        if required
        else _no_capability_requested(device_id)
    )
    if decision.granted:
        logger.info(
            "Device credential admitted to remote-control surface: device=%s capabilities=%s",
            device_id,
            ",".join(sorted(c.value for c in required)),
        )
        return device_user

    logger.warning(
        "Rejected device credential on remote-control surface: device=%s reason=%s",
        device_id,
        decision.describe(),
    )
    await _close_policy(websocket, f"Device capability denied ({decision.describe()})")
    return None


def _no_capability_requested(device_id: str) -> "DeviceCapabilityDecision":
    """An enforcement point that names no capability gets a refusal, not a pass.

    Calling the gate with an empty requirement set is a wiring mistake, and the
    only safe reading of "this credential must hold nothing in particular" on a
    full-control surface is that it holds nothing.
    """
    from services.device_capabilities import (  # noqa: PLC0415
        REASON_MISSING_CAPABILITY,
        DeviceCapabilityDecision,
    )

    logger.error("Remote-control capability gate invoked with no required capability (device=%s)", device_id)
    return DeviceCapabilityDecision(granted=False, reason=REASON_MISSING_CAPABILITY)


async def _close_policy(websocket: WebSocket, reason: str) -> None:
    """Close a handshake with policy-violation ``1008``, tolerating an already-closed socket."""
    try:
        await websocket.close(code=1008, reason=reason)
    except Exception:  # already closed / handshake not completed
        pass


async def enforce_ws_terminal_auth(websocket: WebSocket) -> "dict | None":
    """The terminal surface's guard: a device credential must hold ``terminal``."""
    return await enforce_ws_remote_control_auth(websocket, DeviceCapability.TERMINAL)


async def enforce_ws_desktop_auth(websocket: WebSocket) -> "dict | None":
    """The desktop surface's guard: a device credential must hold BOTH desktop capabilities.

    The RFB proxy carries framebuffer and input on one stream —
    ``api.vnc_proxy._forward_client_to_vnc`` forwards the client's KeyEvent and
    PointerEvent frames verbatim — so opening that socket grants input as
    inseparably as it grants view. Requiring view alone would be a view-only
    grant that is not view-only. Separating the two needs RFB message-level
    filtering on the client->server direction, which this does not attempt.

    Named per surface rather than per capability so the surface->capability
    mapping lives in one readable place: an endpoint asks for "the desktop
    guard" and cannot understate what its own socket hands out.
    """
    return await enforce_ws_remote_control_auth(
        websocket,
        DeviceCapability.DESKTOP_VIEW,
        DeviceCapability.DESKTOP_INPUT,
    )
