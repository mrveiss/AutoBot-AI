# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Callers of the synchronous ``KnowledgeBase.get_fact`` fetch an existing fact (#16670).

``FactsMixin.get_fact`` is a plain ``def``. Five callers awaited it, and awaiting a dict
raises ``TypeError``, so every one of those paths failed whether or not the fact existed.
Each mock here is a plain ``MagicMock`` for exactly that reason: an ``AsyncMock`` would
reproduce the wrong API and hide the bug again.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_FACT = {"content": "c", "metadata": {"owner_id": "u1"}, "timestamp": "t"}


def _kb():
    kb = MagicMock()
    kb.get_fact = MagicMock(return_value=_FACT)
    kb.ownership_manager = MagicMock()
    kb.ownership_manager.get_shared_facts = AsyncMock(return_value=["f1"])
    return kb


@pytest.mark.asyncio
async def test_the_owned_fact_detail_fetch_returns_the_fact():
    from api.knowledge_ownership import _fetch_fact_details

    facts = await _fetch_fact_details(_kb(), ["f1"], ["f1"], [], limit=10)

    assert [(f["fact_id"], f["content"], f["is_owned"]) for f in facts] == [("f1", "c", True)]


@pytest.mark.asyncio
async def test_the_shared_with_me_route_returns_the_fact():
    from api import knowledge_ownership as ownership_api

    request = MagicMock()
    request.state.user = {"user_id": "u2"}
    with patch.object(ownership_api, "get_or_create_knowledge_base", AsyncMock(return_value=_kb())):
        response = await ownership_api.get_shared_facts(request, limit=50, offset=0, _={})

    assert [(f["fact_id"], f["owner_id"]) for f in response["facts"]] == [("f1", "u1")]


def _preserving_kb(write_status: str):
    kb = _kb()
    kb.get_session_for_fact = AsyncMock(return_value="s1")  # genuinely async
    kb.update_fact = AsyncMock(return_value={"status": write_status})
    return kb


@pytest.mark.asyncio
async def test_preserving_a_session_fact_fetches_and_marks_it():
    import asyncio

    from api.chat_knowledge import _preserve_single_fact

    kb = _preserving_kb("success")
    result = await _preserve_single_fact(kb, "f1", "s1", True, "t", asyncio.Semaphore(1))

    assert result == {"status": "success", "fact_id": "f1"}
    assert kb.update_fact.await_args.kwargs["metadata"]["preserve"] is True


@pytest.mark.asyncio
async def test_a_failed_preserve_write_is_not_reported_as_success():
    """update_fact reports failure as a dict, which is truthy -- the old check passed it."""
    import asyncio

    from api.chat_knowledge import _preserve_single_fact

    result = await _preserve_single_fact(_preserving_kb("error"), "f1", "s1", True, "t", asyncio.Semaphore(1))

    assert result == {"status": "error", "fact_id": "f1", "error": "update_failed"}


@pytest.mark.asyncio
async def test_the_mcp_get_document_tool_returns_the_fact():
    from mcp.autobot_server import AutoBotMCPServer

    with patch("knowledge._composed.get_knowledge_base", AsyncMock(return_value=_kb())):
        doc = await AutoBotMCPServer()._kb_get_document("f1")

    assert doc == _FACT


@pytest.mark.asyncio
async def test_the_mcp_get_document_tool_reports_a_missing_fact():
    from mcp.autobot_server import AutoBotMCPServer

    kb = _kb()
    kb.get_fact.return_value = None
    with patch("knowledge._composed.get_knowledge_base", AsyncMock(return_value=kb)):
        doc = await AutoBotMCPServer()._kb_get_document("f1")

    assert doc == {"error": "Document not found", "doc_id": "f1"}
