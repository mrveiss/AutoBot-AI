# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LLCAgentAuthMiddleware (GH#9777 dedup — delegates to ApiKeyService)."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.middleware.agent_auth import LLCAgentAuthMiddleware

_HBS = "llc.middleware.agent_auth"


def _request(path: str, auth: str | None) -> MagicMock:
    req = MagicMock()
    req.url.path = path
    req.headers = {"Authorization": auth} if auth is not None else {}
    req.state = MagicMock()
    return req


def _patched_get_factory():
    """Stand-in for get_async_session_factory: returns a factory whose call
    yields a fresh async-context-manager session (middleware calls factory()
    once per DB op)."""

    @asynccontextmanager
    async def _cm():
        yield AsyncMock()

    def factory():
        return _cm()

    return factory


@pytest.mark.asyncio
class TestAgentAuthMiddleware:
    async def _dispatch(self, request):
        mw = LLCAgentAuthMiddleware(app=MagicMock())
        call_next = AsyncMock(return_value="OK")
        return await mw.dispatch(request, call_next), call_next

    async def test_passthrough_non_agent_path(self):
        resp, call_next = await self._dispatch(_request("/api/other", None))
        assert resp == "OK"
        call_next.assert_awaited_once()

    async def test_missing_bearer_401(self):
        resp, call_next = await self._dispatch(_request("/api/llc/agent/context/1", None))
        assert resp.status_code == 401
        call_next.assert_not_awaited()

    async def test_invalid_key_401_via_validate_key(self):
        with (
            patch(f"{_HBS}.get_async_session_factory", new=_patched_get_factory),
            patch(f"{_HBS}.ApiKeyService") as svc,
        ):
            svc.return_value.validate_key = AsyncMock(return_value=None)
            resp, call_next = await self._dispatch(_request("/api/llc/agent/context/1", "Bearer llc_bad"))
        assert resp.status_code == 401
        call_next.assert_not_awaited()
        svc.return_value.validate_key.assert_awaited_once()

    async def test_valid_key_sets_state_and_continues(self):
        record = MagicMock(id="k1", agent_id="agent-1", company_id="co-1")
        with (
            patch(f"{_HBS}.get_async_session_factory", new=_patched_get_factory),
            patch(f"{_HBS}.ApiKeyService") as svc,
        ):
            svc.return_value.validate_key = AsyncMock(return_value=record)
            req = _request("/api/llc/agent/context/1", "Bearer llc_good")
            resp, call_next = await self._dispatch(req)
        assert resp == "OK"
        call_next.assert_awaited_once()
        assert req.state.agent_id == "agent-1"
        assert req.state.company_id == "co-1"
