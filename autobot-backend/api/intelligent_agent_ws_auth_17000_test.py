# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""WS /stream authenticates before processing a goal (#17000).

Before this fix, ``websocket_stream`` accepted any client -- ``enforce_ws_origin``
was the only check, and it passes a non-browser client that simply omits
``Origin`` -- then ran whatever goal it received through
``agent.process_natural_language_goal``. The HTTP twin, ``POST /process``,
already required ``Depends(get_current_user)``; the WebSocket was a direct
unauthenticated bypass of that authenticated route.

Same accept-then-close convention as ``api/voice_stream.py``'s ``voice_stream_ws``
and ``api/presence_ws_auth_16455_test.py`` (#12366, #15745): a rejected socket
gets a real WS close frame (4001 + reason), not a raw handshake rejection
indistinguishable from a missing route.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.intelligent_agent import router as intelligent_agent_router

_PATH = "/stream"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(intelligent_agent_router)
    return TestClient(app, raise_server_exceptions=False)


def _patch_auth(user_payload: dict | None):
    """``api.intelligent_agent`` imports ``authenticate_websocket`` at module
    scope (like ``api/presence_ws.py``) -- the patch target is the bound name
    in ``api.intelligent_agent``."""
    return patch("api.intelligent_agent.authenticate_websocket", new=AsyncMock(return_value=user_payload))


def _rejecting_agent() -> MagicMock:
    """A spy agent whose goal-processing method fails the test if reached.

    Used as the negative control: a refused handshake must never construct
    the agent's chunk generator at all, let alone iterate it.
    """
    agent = MagicMock()
    agent.process_natural_language_goal = MagicMock(
        side_effect=AssertionError("process_natural_language_goal must not be called for a refused handshake")
    )
    return agent


class TestIntelligentAgentStreamAuthentication:
    def test_no_token_is_refused(self):
        with (
            _patch_auth(None),
            patch("api.intelligent_agent.get_agent", new=AsyncMock(return_value=_rejecting_agent())) as mock_get_agent,
        ):
            client = _client()
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(_PATH) as ws:
                    ws.receive_text()
        assert exc_info.value.code == 4001
        mock_get_agent.assert_not_awaited()

    def test_invalid_token_is_refused(self):
        # authenticate_websocket itself returns None for an invalid/expired JWT --
        # indistinguishable, from this route's perspective, from no token at all.
        with (
            _patch_auth(None),
            patch("api.intelligent_agent.get_agent", new=AsyncMock(return_value=_rejecting_agent())) as mock_get_agent,
        ):
            client = _client()
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"{_PATH}?token=garbage") as ws:
                    ws.receive_text()
        assert exc_info.value.code == 4001
        mock_get_agent.assert_not_awaited()

    def test_a_refused_handshake_never_calls_process_natural_language_goal(self):
        """Negative control (#17000 AC): the goal-processing spy fails the
        test if reached, proving the reject path returns before any agent
        work starts."""
        with (
            _patch_auth(None),
            patch("api.intelligent_agent.get_agent", new=AsyncMock(return_value=_rejecting_agent())) as mock_get_agent,
        ):
            client = _client()
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(_PATH) as ws:
                    ws.receive_text()
        mock_get_agent.assert_not_awaited()

    def test_valid_token_is_accepted_and_reaches_the_agent(self):
        async def _empty_goal_stream(*_args, **_kwargs):
            return
            yield  # pragma: no cover - makes this an async generator

        fake_agent = MagicMock()
        fake_agent.process_natural_language_goal = MagicMock(side_effect=_empty_goal_stream)

        with (
            _patch_auth({"username": "alice", "role": "user"}),
            patch("api.intelligent_agent.get_agent", new=AsyncMock(return_value=fake_agent)) as mock_get_agent,
        ):
            client = _client()
            with client.websocket_connect(f"{_PATH}?token=real") as ws:
                ws.send_json({"goal": "list files"})
                msg = ws.receive_json()

        assert msg == {"type": "complete", "content": "Goal processing completed"}
        mock_get_agent.assert_awaited_once()
        fake_agent.process_natural_language_goal.assert_called_once_with("list files", context={})
