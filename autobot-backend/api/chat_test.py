# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the research-quarantine filter fix at api/chat.py call sites (#13009).

Two general-purpose chat surfaces in this module read the KB directly to
build response context/citations: ``process_chat_message`` (#10548 RAG
grounding, the primary ``/chat`` and ``/chat/message`` endpoints) and
``_enhance_with_knowledge_base`` (the AI-Stack chat pipeline). Both must
exclude quarantined research facts (#12622) the same way
``async_chat_workflow.py::_execute_kb_search`` already does.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.chat import _enhance_with_knowledge_base, process_chat_message
from api.schemas_chat import ChatMessage
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER


@pytest.mark.asyncio
async def test_enhance_with_knowledge_base_applies_quarantine_filter():
    mock_kb = AsyncMock()
    mock_kb.search.return_value = [{"content": "fact"}]
    message = ChatMessage(content="what is autobot", session_id="s1", use_knowledge_base=True)

    await _enhance_with_knowledge_base(message, mock_kb)

    mock_kb.search.assert_called_once_with(query="what is autobot", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_process_chat_message_citations_apply_quarantine_filter():
    """#10548: this is the live RAG-grounding path on every /chat turn."""
    mock_kb = AsyncMock()
    mock_kb.search.return_value = []

    message = ChatMessage(content="what is autobot", session_id="s1", use_knowledge_base=True)

    with (
        patch("api.chat._validate_session_id"),
        patch("api.chat._validate_and_pin_provider"),
        patch("api.chat._store_and_log_user_message", new=AsyncMock()),
        patch("api.chat._get_chat_context", new=AsyncMock(return_value=[])),
        patch("api.chat._build_llm_context", return_value=[]),
        patch("api.chat._resolve_chat_reasoning_effort", new=AsyncMock(return_value="auto")),
        patch(
            "api.chat._generate_ai_response",
            new=AsyncMock(return_value=({"content": "hi", "metadata": {}}, None)),
        ),
        patch("api.chat._store_and_log_ai_response", new=AsyncMock(return_value="msg-1")),
        patch(
            "api.chat.handle_message_completion",
            new=AsyncMock(return_value={"summary_created": False, "warning_triggered": False}),
        ),
    ):
        await process_chat_message(
            message=message,
            chat_history_manager=AsyncMock(),
            llm_service=AsyncMock(),
            memory_interface=AsyncMock(),
            knowledge_base=mock_kb,
            config={},
            request_id="req-1",
        )

    mock_kb.search.assert_called_once_with(query="what is autobot", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)
