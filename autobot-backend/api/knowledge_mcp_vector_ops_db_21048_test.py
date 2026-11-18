# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Only the MCP vector ``flush`` operation needs the database; the read-only ones work without it (#21048).

Fakes only: no real Redis or database is touched.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import knowledge_mcp


def _unavailable():
    raise ConnectionError("database unavailable")


def test_the_route_does_not_depend_on_the_database_session():
    assert "session" not in inspect.signature(knowledge_mcp.mcp_redis_vector_operations).parameters


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["info", "reindex", "backup"])
async def test_a_read_only_operation_works_with_the_database_unavailable(operation):
    handler = AsyncMock(return_value={"success": True, "operation": operation})
    with (
        patch.object(knowledge_mcp, "get_async_session_factory", side_effect=_unavailable) as factory,
        patch.object(knowledge_mcp, "get_knowledge_base", return_value=MagicMock()),
        patch.object(knowledge_mcp, "get_vectors_redis_client", return_value=MagicMock()),
        patch.dict(knowledge_mcp._VECTOR_OPERATIONS, {operation: handler}),
    ):
        answer = await knowledge_mcp.mcp_redis_vector_operations({"operation": operation}, {"id": "u"})
    assert answer["success"] is True
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_flush_resolves_the_session_and_proposes_a_wipe():
    session = MagicMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    proposal = AsyncMock(return_value={"success": True, "operation": "flush"})
    with (
        patch.object(knowledge_mcp, "get_async_session_factory", return_value=lambda: context),
        patch.object(knowledge_mcp, "request_vector_flush", proposal),
    ):
        answer = await knowledge_mcp.mcp_redis_vector_operations({"operation": "flush"}, {"id": "u"})
    assert answer["success"] is True
    proposal.assert_awaited_once_with({"id": "u"}, session)
