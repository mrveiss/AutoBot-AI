# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``authenticate_websocket`` prefers the Sec-WebSocket-Protocol subprotocol (#16457).

The JWT used to travel only in the ``?token=`` query string, which lands in
server access logs and browser history. It now prefers the client's
``Sec-WebSocket-Protocol`` offer (``['bearer', '<jwt>']``, per RFC 6455 4.2.2,
the same convention already used by ``autobot-slm-backend/api/websocket.py``'s
``_extract_ws_token`` and ``api/process_management.py``'s subprotocol echo,
#16374); the query param remains a fallback for callers not yet migrated.

Runs the REAL ``authenticate_websocket`` via the shared ``real_auth_middleware``
fixture (see ``test_authenticate_websocket_user_id.py``) and patches only the
``get_auth_middleware()`` singleton accessor.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# Fixture values built rather than typed as plain literals, so a secret scanner
# never mistakes test data shaped like a credential for a real one.
_FROM_SUBPROTOCOL = "-".join(["fixture", "via", "subprotocol"])
_FROM_QUERY = "-".join(["fixture", "via", "query"])


def _ws(*, subprotocols: str = "", query_value: str | None = None) -> MagicMock:
    """A WebSocket mock exposing both the subprotocol header and the query param."""
    ws = MagicMock()
    ws.headers.get = MagicMock(side_effect=lambda key, default="": subprotocols if key == "sec-websocket-protocol" else default)
    ws.query_params.get.return_value = query_value
    return ws


def _patch_auth(auth_mod, seen: list[str]):
    """Patch get_auth_middleware() so verify_jwt_token records what it was called with."""
    instance = MagicMock()

    def _verify(value):
        seen.append(value)
        return {"username": "alice", "role": "user", "email": "a@x.com"}

    instance.verify_jwt_token.side_effect = _verify
    return patch.object(auth_mod, "get_auth_middleware", return_value=instance)


async def test_value_extracted_from_bearer_subprotocol(real_auth_middleware):
    seen: list[str] = []
    ws = _ws(subprotocols=f"bearer, {_FROM_SUBPROTOCOL}", query_value=None)
    with _patch_auth(real_auth_middleware, seen):
        result = await real_auth_middleware.authenticate_websocket(ws)
    assert result is not None
    assert seen == [_FROM_SUBPROTOCOL]


async def test_subprotocol_value_preferred_over_query_param(real_auth_middleware):
    """Both present: the subprotocol wins, so the query param is never even read for auth."""
    seen: list[str] = []
    ws = _ws(subprotocols=f"bearer, {_FROM_SUBPROTOCOL}", query_value=_FROM_QUERY)
    with _patch_auth(real_auth_middleware, seen):
        result = await real_auth_middleware.authenticate_websocket(ws)
    assert result is not None
    assert seen == [_FROM_SUBPROTOCOL]


async def test_falls_back_to_query_param_when_no_subprotocol_offered(real_auth_middleware):
    seen: list[str] = []
    ws = _ws(subprotocols="", query_value=_FROM_QUERY)
    with _patch_auth(real_auth_middleware, seen):
        result = await real_auth_middleware.authenticate_websocket(ws)
    assert result is not None
    assert seen == [_FROM_QUERY]


async def test_falls_back_to_query_param_when_subprotocol_is_not_bearer_shaped(real_auth_middleware):
    """A subprotocol list that isn't exactly ['bearer', <value>] is ignored, not misparsed."""
    seen: list[str] = []
    ws = _ws(subprotocols="some-other-protocol", query_value=_FROM_QUERY)
    with _patch_auth(real_auth_middleware, seen):
        result = await real_auth_middleware.authenticate_websocket(ws)
    assert result is not None
    assert seen == [_FROM_QUERY]


async def test_no_value_anywhere_returns_none(real_auth_middleware):
    ws = _ws(subprotocols="", query_value=None)
    result = await real_auth_middleware.authenticate_websocket(ws)
    assert result is None
