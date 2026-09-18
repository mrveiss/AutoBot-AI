# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one place that reads and echoes the WebSocket ``bearer`` subprotocol (#16457).

A browser cannot set headers on a WebSocket, so the token travels as
``Sec-WebSocket-Protocol: bearer, <jwt>`` instead of in a URL, where it would land
in proxy logs, history and referrers. RFC 6455 section 4.2.2 then requires the
server to echo back one subprotocol the client offered, or the browser fails the
handshake. So reading the token and echoing ``bearer`` are one contract.

They used to be kept separately in every endpoint, and had already drifted into
two different parsers: ``authenticate_websocket`` read a token only from exactly
``bearer, <jwt>``, while endpoints echoed whenever the raw header merely
``startswith("bearer")``. A header of ``bearerX, <jwt>`` therefore had
``bearer`` echoed back although the client never offered it -- which fails the
handshake -- and read no token. And four of the endpoints authenticating through
the same function echoed nothing at all, so the first frontend service pointed at
the header on any of them would have broken in browsers with CI green: a test
client does not enforce the echo.

Every endpoint now accepts through :func:`accept_websocket`, and
``repo_tests/websocket_subprotocol_echo_guard_test.py`` fails any module that
authenticates a WebSocket and calls ``.accept(`` itself.

:func:`resolve_ws_token` is the read-side counterpart (#16457 review):
both backends' token resolution fell back to ``?token=`` identically, and
that fallback's use was invisible -- neither logged when a handshake
actually took it. One function now owns both, so a straggler client still
using the query param shows up in the logs without a second copy of the
same fallback-and-log logic per backend.

The fallback warning is throttled per route through the existing
``autobot_shared.alert_cooldown`` (#16457 review, round 3): unthrottled, a
client stuck in a reconnect loop -- or a prober -- can flood the log with
one line per handshake attempt.
"""

import hashlib
import logging

from autobot_shared.alert_cooldown import AlertCooldownManager, AlertTier

# Plain stdlib logging, deliberately -- this module is imported at module
# scope by `autobot-slm-backend/api/websocket.py`, whose test harness
# (`tests/test_websocket_auth_smoke.py` et al.) loads that file with most of
# the config stack replaced by MagicMock.
# `autobot_shared.logging_manager.get_logger` builds a RotatingFileHandler
# from config at call time and raises under that harness (mirrors
# `autobot_shared/user_management/password_epoch.py`'s documented reason for
# the same choice; CLAUDE.md's pattern table prescribes it for exactly this
# situation).
logger = logging.getLogger(__name__)

# ROUTINE: this is a migration-visibility signal, not a paging alert -- 2/hr
# and a 60-minute per-route cooldown is plenty to notice a straggler client
# without a reconnect loop flooding the log with a line per attempt.
_fallback_cooldown = AlertCooldownManager()

BEARER = "bearer"


def _offered(websocket) -> list[str]:
    return [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]


def bearer_subprotocol_token(websocket) -> str | None:
    """The JWT from ``Sec-WebSocket-Protocol: bearer, <jwt>``, or None.

    Exactly the parse ``authenticate_websocket`` has always used, moved here so
    that the echo below can never disagree with it.
    """
    parts = _offered(websocket)
    return parts[1] if len(parts) == 2 and parts[0] == BEARER and parts[1] else None


def _route_cooldown_key(route: str) -> str:
    """An opaque per-route cooldown fingerprint, immune to ``alert_cooldown``'s
    own normalisation.

    ``AlertCooldownManager`` strips whole-token numeric runs from the alert
    text before hashing it (so e.g. "Disk at 95%" and "Disk at 96%" dedupe as
    the same alert) -- which silently collapsed ``/ws/deployments/dep-1`` and
    ``/ws/deployments/dep-2`` onto one cooldown key, verified by a failing
    test: only the first route's handshake ever logged. Prefixing the hash
    with a non-numeric run makes the whole token non-digit-only, so it can
    never match that strip.
    """
    return "route" + hashlib.sha256(str(route).encode("utf-8")).hexdigest()[:16]


def resolve_ws_token(websocket) -> str | None:
    """The auth token: subprotocol header preferred, ``?token=`` a logged fallback.

    #16457 review: the query-param fallback is kept on purpose during
    migration, but its use was invisible. Logs one warning per route, at
    most once per cooldown window, naming the route only, the token never.
    """
    subprotocol_token = bearer_subprotocol_token(websocket)
    token = subprotocol_token or websocket.query_params.get("token")
    if token and not subprotocol_token:
        route = websocket.url.path
        cooldown_key = _route_cooldown_key(route)
        if _fallback_cooldown.should_send(cooldown_key, AlertTier.ROUTINE):
            logger.warning("WS auth via ?token= fallback, not subprotocol | path=%s", route)
            _fallback_cooldown.record_sent(cooldown_key, AlertTier.ROUTINE)
    return token


def negotiated_subprotocol(websocket) -> str | None:
    """``"bearer"`` when the client offered that exact protocol, else None.

    Echoes only what was offered -- never ``bearer`` for ``bearerX`` -- and echoes
    it even when no usable token follows, so the handshake completes and the
    endpoint can reject with a clean 4001 close instead of a handshake failure.
    """
    return BEARER if BEARER in _offered(websocket) else None


async def accept_websocket(websocket) -> None:
    """``websocket.accept()``, echoing the ``bearer`` subprotocol when it was offered."""
    await websocket.accept(subprotocol=negotiated_subprotocol(websocket))
