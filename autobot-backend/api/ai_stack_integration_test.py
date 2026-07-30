# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the research-quarantine filter fix at api/ai_stack_integration.py (#13009).

Three admin-gated but still general-purpose KB reads in this module must
exclude quarantined research facts (#12622) the same way
``async_chat_workflow.py::_execute_kb_search`` already does: admin auth is a
different guarantee than the quarantine's "invisible until promoted".
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.ai_stack_integration import chat, knowledge_search, rag_query
from api.schemas_knowledge import ChatRequest, RAGQueryRequest
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER


def _fake_ai_client() -> AsyncMock:
    client = AsyncMock()
    client.rag_query.return_value = {"answer": "ok"}
    client.chat_message.return_value = {"content": "ok"}
    client.search_knowledge.return_value = {"results": []}
    return client


@pytest.mark.asyncio
async def test_rag_query_applies_quarantine_filter():
    mock_kb = AsyncMock()
    mock_kb.search.return_value = []

    with patch("api.ai_stack_integration.get_ai_stack_client", AsyncMock(return_value=_fake_ai_client())):
        await rag_query(
            request=RAGQueryRequest(query="what is autobot", max_results=10),
            admin_check=True,
            knowledge_base=mock_kb,
        )

    mock_kb.search.assert_called_once_with(query="what is autobot", top_k=10, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_chat_applies_quarantine_filter():
    mock_kb = AsyncMock()
    mock_kb.search.return_value = []

    with patch("api.ai_stack_integration.get_ai_stack_client", AsyncMock(return_value=_fake_ai_client())):
        await chat(
            request=ChatRequest(message="what is autobot", use_knowledge_base=True),
            admin_check=True,
            knowledge_base=mock_kb,
        )

    mock_kb.search.assert_called_once_with(query="what is autobot", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_knowledge_search_applies_quarantine_filter():
    mock_kb = AsyncMock()
    mock_kb.search.return_value = []

    with patch("api.ai_stack_integration.get_ai_stack_client", AsyncMock(return_value=_fake_ai_client())):
        await knowledge_search(
            query="what is autobot",
            max_results=10,
            admin_check=True,
            knowledge_base=mock_kb,
        )

    mock_kb.search.assert_called_once_with(query="what is autobot", top_k=10, filters=RESEARCH_QUARANTINE_FILTER)
