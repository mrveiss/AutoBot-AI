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
"""

import logging

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


def resolve_ws_token(websocket) -> str | None:
    """The auth token: subprotocol header preferred, ``?token=`` a logged fallback.

    #16457 review: the query-param fallback is kept on purpose during
    migration, but its use was invisible. Logs one warning per handshake
    that actually took it -- naming the route only, the token never.
    """
    subprotocol_token = bearer_subprotocol_token(websocket)
    token = subprotocol_token or websocket.query_params.get("token")
    if token and not subprotocol_token:
        logger.warning("WS auth via ?token= fallback, not subprotocol | path=%s", websocket.url.path)
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
