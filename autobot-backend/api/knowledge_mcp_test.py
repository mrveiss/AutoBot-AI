# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for the api/knowledge_mcp.py KB singleton fix (#13026).

``get_knowledge_base = lazy_singleton(lambda: KnowledgeBase(config_manager=get_config()))``
raised ``TypeError`` on first call: ``KnowledgeBase.__init__(self)`` takes no
parameters at all. Every handler in this file wraps the call in a broad
``except Exception`` returning a generic ``{"success": False, ...}`` payload,
so the breakage was silent (a 200 response, not a visible crash).

These tests call the route coroutines directly (no FastAPI TestClient needed
-- plain ``async def``s; ``Depends(...)`` defaults are simply overridden with
explicit kwargs), patching the module-level ``get_knowledge_base`` singleton
with a ``create_autospec(KnowledgeBase, instance=True)`` so an incompatible
call anywhere in the chain would raise the real production ``TypeError``.
"""

from __future__ import annotations

from unittest.mock import create_autospec, patch

import pytest

from api.knowledge_mcp import (
    KnowledgeSearchRequest,
    mcp_search_knowledge_base,
    mcp_summarize_knowledge_topic,
)
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge_base import KnowledgeBase


def test_get_knowledge_base_singleton_constructs_without_typeerror():
    """#13026: the bare constructor call must not raise TypeError."""
    import api.knowledge_mcp as knowledge_mcp

    knowledge_mcp.get_knowledge_base.reset()
    with patch("api.knowledge_mcp.KnowledgeBase", return_value=create_autospec(KnowledgeBase, instance=True)):
        kb = knowledge_mcp.get_knowledge_base()
    assert kb is not None
    knowledge_mcp.get_knowledge_base.reset()


@pytest.mark.asyncio
async def test_mcp_search_knowledge_base_returns_real_content_and_applies_quarantine():
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [{"content": "AutoBot uses Redis", "score": 0.9, "metadata": {}}]

    with patch("api.knowledge_mcp.get_knowledge_base", return_value=mock_kb):
        response = await mcp_search_knowledge_base(
            request=KnowledgeSearchRequest(query="redis", top_k=5),
            current_user={"user_id": "test-user"},
        )

    assert response["success"] is True
    assert response["results"][0]["content"] == "AutoBot uses Redis"
    mock_kb.search.assert_called_once_with(query="redis", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_mcp_summarize_knowledge_topic_returns_real_content():
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [{"content": "AutoBot uses Redis for caching."}]
    del mock_kb.llm  # KnowledgeBase has no `llm` attribute -- exercise the truncation fallback

    with patch("api.knowledge_mcp.get_knowledge_base", return_value=mock_kb):
        response = await mcp_summarize_knowledge_topic(
            request={"topic": "redis"},
            current_user={"user_id": "test-user"},
        )

    assert response["success"] is True
    assert "Redis" in response["summary"]
    assert response["source_count"] == 1
    mock_kb.search.assert_called_once_with(query="redis", top_k=10, filters=RESEARCH_QUARANTINE_FILTER)
