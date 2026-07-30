# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for ToolRegistry's KB-search tools (#13027).

``get_tool_registry = lazy_singleton(ToolRegistry)`` is called with no args
by every production call site (``services/llm_service.py``,
``api/image_generation.py``), so the constructor-injected ``knowledge_base``
was permanently ``None`` -- ``search_knowledge_base()`` and ``get_fact()``
always hit their ``if not self.knowledge_base:`` guard and reported
"Knowledge base is not available", making the LLM tool-calling KB-search
tool permanently non-functional.

Fix: ``_resolve_knowledge_base()`` lazily resolves the KB via the shared
``knowledge_factory.get_knowledge_base_async()`` singleton on first use,
regardless of constructor args. Also discovered along the way (#13024-class
bug, same file): ``search_knowledge_base`` itself called
``self.knowledge_base.search(query, n_results=n_results)`` -- a kwarg the
canonical ``search()`` doesn't accept -- which would have just traded one
silent failure ("KB unavailable") for another (caught ``TypeError``) once
the KB was actually wired in. Fixed in the same change since #13027 isn't
fully delivered without it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, create_autospec, patch

import pytest

from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge_base import KnowledgeBase
from tools.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_search_knowledge_base_resolves_kb_and_returns_real_content():
    """No knowledge_base injected at construction -- matches every production caller."""
    registry = ToolRegistry()
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [{"content": "AutoBot uses Redis for caching.", "metadata": {}}]

    with patch("knowledge_factory.get_knowledge_base_async", AsyncMock(return_value=mock_kb)):
        result = await registry.search_knowledge_base("redis", n_results=5)

    assert result["status"] == "success"
    assert "AutoBot uses Redis" in result["result"]
    mock_kb.search.assert_called_once_with("redis", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_search_knowledge_base_no_kb_available_reports_unavailable():
    registry = ToolRegistry()

    with patch("knowledge_factory.get_knowledge_base_async", AsyncMock(return_value=None)):
        result = await registry.search_knowledge_base("redis")

    assert result["status"] == "error"
    assert result["result"] == "Knowledge base is not available"


@pytest.mark.asyncio
async def test_get_fact_by_query_resolves_kb_and_returns_real_content():
    registry = ToolRegistry()
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [{"id": "f1", "content": "Redis caches KB embeddings."}]

    with patch("knowledge_factory.get_knowledge_base_async", AsyncMock(return_value=mock_kb)):
        result = await registry.get_fact(query="redis")

    assert result["status"] == "success"
    assert "Redis caches KB embeddings." in result["result"]
    mock_kb.search.assert_called_once_with("redis", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_resolve_knowledge_base_caches_after_first_resolution():
    """The lazily-resolved KB is cached on the instance, not re-resolved every call."""
    registry = ToolRegistry()
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = []
    resolver = AsyncMock(return_value=mock_kb)

    with patch("knowledge_factory.get_knowledge_base_async", resolver):
        await registry.search_knowledge_base("q1")
        await registry.get_fact(query="q2")

    assert resolver.call_count == 1
    assert registry.knowledge_base is mock_kb


@pytest.mark.asyncio
async def test_search_knowledge_base_injected_at_construction_is_used_directly():
    """Constructor-injected knowledge_base (test/legacy callers) skips lazy resolution."""
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [{"content": "injected KB result", "metadata": {}}]
    registry = ToolRegistry(knowledge_base=mock_kb)

    result = await registry.search_knowledge_base("q")

    assert "injected KB result" in result["result"]
    mock_kb.search.assert_called_once_with("q", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)
