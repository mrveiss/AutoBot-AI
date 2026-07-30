# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the research-quarantine filter fix at api/knowledge_ai_stack.py (#13009).

``POST /search/rag`` is a general-purpose, authenticated RAG search that
falls back to the local KB for documents -- it must exclude quarantined
research facts (#12622) the same way
``async_chat_workflow.py::_execute_kb_search`` already does.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.knowledge_ai_stack import rag_search
from api.schemas_knowledge import AIStackRAGQueryRequest
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER


@pytest.mark.asyncio
async def test_rag_search_applies_quarantine_filter():
    mock_kb = AsyncMock()
    mock_kb.search.return_value = []

    mock_ai_client = AsyncMock()
    mock_ai_client.rag_query.return_value = {"answer": "ok"}

    with patch("api.knowledge_ai_stack.get_ai_stack_client", AsyncMock(return_value=mock_ai_client)):
        await rag_search(
            request_data=AIStackRAGQueryRequest(query="what is autobot"),
            knowledge_base=mock_kb,
            current_user={"user_id": "test-user"},
        )

    mock_kb.search.assert_called_once_with(query="what is autobot", top_k=15, filters=RESEARCH_QUARANTINE_FILTER)
