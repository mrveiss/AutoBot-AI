# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the research-quarantine filter fix at api/agent.py call sites (#13009).

Proves the two general-purpose KB reads in this module -- goal-context
enhancement and the "comprehensive research" multi-agent task (NOT the
#12622/#12623 ResearchOrchestrator quarantine pipeline) -- now pass the
shared exclusion filter into every ``knowledge_base.search()`` call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.agent import _enhance_context_with_kb, comprehensive_research_task
from api.schemas_agent import ResearchTaskRequest
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER


class _Payload:
    def __init__(self, goal: str, use_knowledge_base: bool = True, context: str | None = None):
        self.goal = goal
        self.use_knowledge_base = use_knowledge_base
        self.context = context


@pytest.mark.asyncio
async def test_enhance_context_with_kb_applies_quarantine_filter():
    mock_kb = AsyncMock()
    mock_kb.search.return_value = [{"content": "fact"}]

    await _enhance_context_with_kb(_Payload(goal="what is autobot"), mock_kb)

    mock_kb.search.assert_called_once_with(query="what is autobot", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_comprehensive_research_task_applies_quarantine_filter():
    """#13009: this endpoint is a general multi-agent task, not the #12622/#12623
    quarantine pipeline itself -- it must NOT see quarantined facts."""
    mock_kb = AsyncMock()
    mock_kb.search.return_value = []

    mock_ai_client = AsyncMock()
    mock_ai_client.multi_agent_query.return_value = {"result": "ok"}

    with patch("api.agent.get_ai_stack_client", AsyncMock(return_value=mock_ai_client)):
        await comprehensive_research_task(
            request_data=ResearchTaskRequest(research_query="what is autobot", include_web=False),
            knowledge_base=mock_kb,
            current_user={"user_id": "test-user"},
        )

    mock_kb.search.assert_called_once_with(query="what is autobot", top_k=3, filters=RESEARCH_QUARANTINE_FILTER)
