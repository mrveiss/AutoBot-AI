# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Precedence of the one company-naming helper, and that a non-member ``?company_id=`` is refused (#21997)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.datastructures import State

from security import session_company
from security.named_company import named_company

HEADER, PATH, QUERY = (str(uuid.uuid4()) for _ in range(3))


def _conn(header=None, path=None, query=None):
    return SimpleNamespace(
        headers={"X-Organization-Id": header} if header else {},
        path_params={"company_id": path} if path else {},
        query_params={"company_id": query} if query else {},
    )


class TestPrecedence:
    def test_header_then_path_then_query(self):
        assert named_company(_conn(HEADER, PATH, QUERY), from_path=True) == uuid.UUID(HEADER)
        assert named_company(_conn(None, PATH, QUERY), from_path=True) == uuid.UUID(PATH)
        assert named_company(_conn(None, None, QUERY), from_path=True) == uuid.UUID(QUERY)

    def test_the_path_is_read_only_when_asked(self):
        assert named_company(_conn(None, PATH, QUERY)) == uuid.UUID(QUERY)

    def test_a_malformed_header_falls_through_to_the_query(self):
        assert named_company(_conn("not-a-uuid", None, QUERY)) == uuid.UUID(QUERY)

    def test_nothing_named_is_none(self):
        assert named_company(_conn()) is None

    def test_http_tenant_context_uses_the_same_helper(self):
        from api.user_management.dependencies import _extract_request_org_id

        assert _extract_request_org_id(_conn(None, PATH, QUERY)) == uuid.UUID(PATH)


class TestNonMemberQueryIsRefused:
    def _request(self):
        request = SimpleNamespace(headers={}, query_params={"company_id": QUERY}, state=State())
        return request

    @pytest.mark.asyncio
    async def test_http_403(self):
        with patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as refused:
                await session_company.resolve_company_scope(self._request(), {"username": "alice", "role": "user"})
        assert refused.value.status_code == 403

    @pytest.mark.asyncio
    async def test_websocket_closes_4403(self):
        socket = MagicMock(close=AsyncMock())
        socket.headers, socket.query_params, socket.state = {}, {"company_id": QUERY}, State()
        with (
            patch.object(session_company, "may_act_in_company", new=AsyncMock(return_value=False)),
            patch("autobot_shared.websocket_subprotocol.accept_websocket", new=AsyncMock()),
        ):
            result = await session_company.connection_company(socket, {"username": "alice", "role": "user"})
        assert result is None
        assert socket.close.await_args.kwargs["code"] == 4403
