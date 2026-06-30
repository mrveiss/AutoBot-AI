# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for AsyncChatWorkflow._execute_kb_search and _workflow_knowledge_search.

Issue #10715: Wire knowledge base search into async chat workflow.
Tests assert correct KnowledgeStatus mapping and kb_results shape across
three scenarios: populated KB, empty KB, and search raising an exception.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODULE = "async_chat_workflow"


def _make_kb_result(content: str = "fact text", score: float = 0.9) -> dict:
    """Return a minimal raw KB search result dict matching the facade output."""
    return {
        "content": content,
        "score": score,
        "metadata": {"fact_id": "abc123"},
        "node_id": "node-1",
        "doc_id": "node-1",
    }


# ---------------------------------------------------------------------------
# _execute_kb_search
# ---------------------------------------------------------------------------


class TestExecuteKbSearch:
    """Unit tests for AsyncChatWorkflow._execute_kb_search."""

    @pytest.fixture()
    def workflow(self):
        from async_chat_workflow import AsyncChatWorkflow

        return AsyncChatWorkflow()

    async def test_found_when_results_returned(self, workflow):
        """Populated KB returns FOUND status and non-empty kb_results."""
        from async_chat_workflow import KnowledgeStatus

        mock_kb = MagicMock()
        mock_kb.search = AsyncMock(return_value=[_make_kb_result("doc A", 0.95)])

        with patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            status, results = await workflow._execute_kb_search("what is autobot")

        assert status is KnowledgeStatus.FOUND
        assert len(results) == 1
        assert results[0]["content"] == "doc A"
        assert results[0]["score"] == 0.95
        assert results[0]["source"] == "node-1"

    async def test_missing_when_empty_results(self, workflow):
        """Empty KB search returns MISSING status and empty list."""
        from async_chat_workflow import KnowledgeStatus

        mock_kb = MagicMock()
        mock_kb.search = AsyncMock(return_value=[])

        with patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            status, results = await workflow._execute_kb_search("unknown query")

        assert status is KnowledgeStatus.MISSING
        assert results == []

    async def test_missing_when_search_raises(self, workflow):
        """Search raising an exception returns MISSING with no propagation."""
        from async_chat_workflow import KnowledgeStatus

        mock_kb = MagicMock()
        mock_kb.search = AsyncMock(side_effect=RuntimeError("chroma unreachable"))

        with patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            status, results = await workflow._execute_kb_search("any query")

        assert status is KnowledgeStatus.MISSING
        assert results == []

    async def test_missing_when_kb_unavailable(self, workflow):
        """get_knowledge_base returning None yields MISSING."""
        from async_chat_workflow import KnowledgeStatus

        with patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=None)):
            status, results = await workflow._execute_kb_search("any query")

        assert status is KnowledgeStatus.MISSING
        assert results == []

    async def test_multiple_results_mapped_correctly(self, workflow):
        """Multiple results are mapped with correct keys."""
        from async_chat_workflow import KnowledgeStatus

        raw = [_make_kb_result(f"doc {i}", 0.9 - i * 0.1) for i in range(3)]
        mock_kb = MagicMock()
        mock_kb.search = AsyncMock(return_value=raw)

        with patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            status, results = await workflow._execute_kb_search("query")

        assert status is KnowledgeStatus.FOUND
        assert len(results) == 3
        for r in results:
            assert "content" in r
            assert "source" in r
            assert "score" in r
            assert "metadata" in r


# ---------------------------------------------------------------------------
# _workflow_knowledge_search (integration of both helpers)
# ---------------------------------------------------------------------------


class TestWorkflowKnowledgeSearch:
    """Tests for _workflow_knowledge_search delegating to _execute_kb_search."""

    @pytest.fixture()
    def workflow(self):
        from async_chat_workflow import AsyncChatWorkflow

        return AsyncChatWorkflow()

    async def test_found_propagates_from_execute(self, workflow):
        """FOUND status and results propagate through _workflow_knowledge_search."""
        from async_chat_workflow import KnowledgeStatus

        mock_kb = MagicMock()
        mock_kb.search = AsyncMock(return_value=[_make_kb_result()])

        with patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            status, results = await workflow._workflow_knowledge_search("hello")

        assert status is KnowledgeStatus.FOUND
        assert len(results) == 1

    async def test_missing_propagates_on_empty(self, workflow):
        """MISSING status propagates through _workflow_knowledge_search."""
        from async_chat_workflow import KnowledgeStatus

        mock_kb = MagicMock()
        mock_kb.search = AsyncMock(return_value=[])

        with patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            status, results = await workflow._workflow_knowledge_search("unknown")

        assert status is KnowledgeStatus.MISSING
        assert results == []

    async def test_error_does_not_propagate(self, workflow):
        """Exception in search does not escape _workflow_knowledge_search."""
        from async_chat_workflow import KnowledgeStatus

        mock_kb = MagicMock()
        mock_kb.search = AsyncMock(side_effect=Exception("boom"))

        with patch(f"{_MODULE}.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            status, results = await workflow._workflow_knowledge_search("query")

        assert status is KnowledgeStatus.MISSING
        assert results == []
