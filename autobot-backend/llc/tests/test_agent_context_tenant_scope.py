# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cross-tenant isolation for agent_api context + peers reads (GH#12156).

The KB context collection is keyed by ``work_item_id`` alone, so an authenticated
agent for company A could read company B's handoff notes by UUID. These tests
prove the handler now verifies work-item ownership (cross-tenant -> 404, own ->
data) and that peer search only ever queries the caller's own company index.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from llc.api import agent_api

_COMPANY_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_COMPANY_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_ITEM_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

_DB = "user_management.database"
_WIS = "llc.services.work_item_service"


def _request(company_id: str) -> MagicMock:
    req = MagicMock()
    req.state.agent_id = "agent-1"
    req.state.company_id = company_id
    return req


def _patched_factory():
    """Stand-in for get_async_session_factory yielding a throwaway session."""

    @asynccontextmanager
    async def _cm():
        yield MagicMock()

    return lambda: _cm()


def _patch_work_item(item_company_id):  # noqa: ANN001, ANN202
    item = None if item_company_id is None else MagicMock(company_id=item_company_id)
    svc = MagicMock()
    svc.get = AsyncMock(return_value=item)
    return (
        patch(f"{_DB}.get_async_session_factory", new=_patched_factory),
        patch(f"{_WIS}.WorkItemService", return_value=svc),
    )


@pytest.mark.asyncio
class TestContextTenantScope:
    async def test_cross_tenant_context_404(self):
        fac_p, svc_p = _patch_work_item(_COMPANY_B)  # item owned by B
        with fac_p, svc_p:
            with pytest.raises(HTTPException) as exc:
                await agent_api.get_item_context(_ITEM_ID, _request(_COMPANY_A))
        assert exc.value.status_code == 404

    async def test_missing_item_404(self):
        fac_p, svc_p = _patch_work_item(None)  # no such item
        with fac_p, svc_p:
            with pytest.raises(HTTPException) as exc:
                await agent_api.get_item_context(_ITEM_ID, _request(_COMPANY_A))
        assert exc.value.status_code == 404

    async def test_same_tenant_context_ok(self):
        fac_p, svc_p = _patch_work_item(_COMPANY_A)  # item owned by caller
        kb = MagicMock()
        kb.get_context = AsyncMock(return_value=[{"id": "notes:1", "document": "hi", "metadata": {}}])
        with fac_p, svc_p, patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb):
            result = await agent_api.get_item_context(_ITEM_ID, _request(_COMPANY_A))
        assert result["has_human_handoff_context"] is True
        assert result["handoff_notes"][0]["document"] == "hi"
        kb.get_context.assert_awaited_once_with(_ITEM_ID)


@pytest.mark.asyncio
class TestPeersTenantScope:
    async def test_peers_query_scoped_to_caller_company(self):
        collection = MagicMock()
        collection.query = AsyncMock(return_value={"ids": [[]]})
        kb = MagicMock()
        kb._async_chroma_client.get_collection = AsyncMock(return_value=collection)
        with patch("knowledge.get_knowledge_base", new=AsyncMock(return_value=kb)):
            out = await agent_api.search_peer_agents(q="devops", request=_request(_COMPANY_A))
        assert out["count"] == 0
        called_name = kb._async_chroma_client.get_collection.await_args.args[0]
        assert called_name == f"company:{_COMPANY_A}:agents"
        assert _COMPANY_B not in called_name
