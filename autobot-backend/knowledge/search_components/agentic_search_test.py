# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for AgenticSearchTool (Issue #1718).

Covers:
- knowledge_search_tool() dispatches correctly when enabled / disabled
- rewrite_query() returns rewritten text on success and falls back on LLM error
- iterative_search() stops early when context is SUFFICIENT
- iterative_search() runs all iterations when context stays INSUFFICIENT
- AgenticSearchConfig fields are respected
- get_agentic_search_tool() singleton replacement when rag_service changes
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.search_components.agentic_search import (
    AgenticSearchConfig,
    AgenticSearchTool,
    get_agentic_search_tool,
    knowledge_search_tool,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(content: str, source: str = "test.md", score: float = 0.8):
    """Build a minimal SearchResult-like object."""
    r = MagicMock()
    r.content = content
    r.source_path = source
    r.metadata = {}
    r.hybrid_score = score
    return r


def _make_rag_service(results=None):
    """Build a mock RAGService whose advanced_search returns *results*."""
    svc = MagicMock()
    svc.advanced_search = AsyncMock(return_value=(results or [], MagicMock()))
    return svc


# ---------------------------------------------------------------------------
# AgenticSearchTool.rewrite_query
# ---------------------------------------------------------------------------


class TestRewriteQuery:
    @pytest.mark.asyncio
    async def test_returns_rewritten_query_on_success(self):
        svc = _make_rag_service()
        tool = AgenticSearchTool(svc, AgenticSearchConfig(rewrite_enabled=True))

        with patch.object(tool, "_call_llm", AsyncMock(return_value="rewritten query")):
            result = await tool.rewrite_query("original query", "some context")

        assert result == "rewritten query"

    @pytest.mark.asyncio
    async def test_falls_back_to_original_on_llm_error(self):
        svc = _make_rag_service()
        tool = AgenticSearchTool(svc, AgenticSearchConfig(rewrite_enabled=True))

        with patch.object(tool, "_call_llm", AsyncMock(side_effect=RuntimeError("timeout"))):
            result = await tool.rewrite_query("original query")

        assert result == "original query"

    @pytest.mark.asyncio
    async def test_falls_back_to_original_on_empty_llm_response(self):
        svc = _make_rag_service()
        tool = AgenticSearchTool(svc, AgenticSearchConfig())

        with patch.object(tool, "_call_llm", AsyncMock(return_value="   ")):
            result = await tool.rewrite_query("original")

        assert result == "original"

    @pytest.mark.asyncio
    async def test_returns_original_for_empty_input(self):
        svc = _make_rag_service()
        tool = AgenticSearchTool(svc, AgenticSearchConfig())
        result = await tool.rewrite_query("")
        assert result == ""


# ---------------------------------------------------------------------------
# AgenticSearchTool.iterative_search
# ---------------------------------------------------------------------------


class TestIterativeSearch:
    @pytest.mark.asyncio
    async def test_stops_early_when_sufficient(self):
        """Should return after first iteration when context is SUFFICIENT."""
        results = [_make_result("answer")]
        svc = _make_rag_service(results)
        tool = AgenticSearchTool(svc, AgenticSearchConfig(max_search_iterations=3))

        from services.context_sufficiency import SufficiencyVerdict

        mock_check = MagicMock()
        mock_check.verdict = SufficiencyVerdict.SUFFICIENT

        with patch("knowledge.search_components.agentic_search.get_context_sufficiency_evaluator") as mock_eval_factory:
            evaluator = MagicMock()
            evaluator.evaluate = AsyncMock(return_value=mock_check)
            mock_eval_factory.return_value = evaluator

            final_results, metrics = await tool.iterative_search("query")

        assert metrics["iterations_run"] == 1
        assert metrics["final_sufficient"] is True
        assert final_results == results
        svc.advanced_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_runs_all_iterations_when_always_insufficient(self):
        """Should exhaust all iterations when sufficiency never improves."""
        svc = _make_rag_service([_make_result("partial")])
        cfg = AgenticSearchConfig(max_search_iterations=2, rewrite_enabled=False)
        tool = AgenticSearchTool(svc, cfg)

        from services.context_sufficiency import SufficiencyVerdict

        mock_check = MagicMock()
        mock_check.verdict = SufficiencyVerdict.INSUFFICIENT

        with patch("knowledge.search_components.agentic_search.get_context_sufficiency_evaluator") as mock_eval_factory:
            evaluator = MagicMock()
            evaluator.evaluate = AsyncMock(return_value=mock_check)
            mock_eval_factory.return_value = evaluator

            with patch.object(tool, "_refine_query", AsyncMock(return_value="refined")):
                _, metrics = await tool.iterative_search("query")

        assert metrics["iterations_run"] == 2
        assert metrics["final_sufficient"] is False
        assert svc.advanced_search.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_empty_context_string_when_no_results(self):
        svc = _make_rag_service([])
        tool = AgenticSearchTool(svc, AgenticSearchConfig(max_search_iterations=1))

        from services.context_sufficiency import SufficiencyVerdict

        mock_check = MagicMock()
        mock_check.verdict = SufficiencyVerdict.INSUFFICIENT

        with patch("knowledge.search_components.agentic_search.get_context_sufficiency_evaluator") as mock_eval_factory:
            evaluator = MagicMock()
            evaluator.evaluate = AsyncMock(return_value=mock_check)
            mock_eval_factory.return_value = evaluator

            results, metrics = await tool.iterative_search("query")

        assert results == []


# ---------------------------------------------------------------------------
# AgenticSearchTool.knowledge_search (integration)
# ---------------------------------------------------------------------------


class TestKnowledgeSearch:
    @pytest.mark.asyncio
    async def test_disabled_agentic_search_skips_rewrite_and_iteration(self):
        """When enable_agentic_search=False the tool should call advanced_search once."""
        results = [_make_result("direct result")]
        svc = _make_rag_service(results)
        cfg = AgenticSearchConfig(enable_agentic_search=False)
        tool = AgenticSearchTool(svc, cfg)

        context = await tool.knowledge_search("query")

        svc.advanced_search.assert_called_once_with("query", max_results=5, categories=None)
        assert "direct result" in context

    @pytest.mark.asyncio
    async def test_enabled_path_calls_rewrite_then_iterative(self):
        """Full pipeline: rewrite then iterative_search."""
        results = [_make_result("rich content")]
        svc = _make_rag_service(results)
        cfg = AgenticSearchConfig(enable_agentic_search=True, rewrite_enabled=True)
        tool = AgenticSearchTool(svc, cfg)

        from services.context_sufficiency import SufficiencyVerdict

        mock_check = MagicMock()
        mock_check.verdict = SufficiencyVerdict.SUFFICIENT

        with patch.object(tool, "rewrite_query", AsyncMock(return_value="rewritten")):
            with patch("knowledge.search_components.agentic_search.get_context_sufficiency_evaluator") as mock_factory:
                evaluator = MagicMock()
                evaluator.evaluate = AsyncMock(return_value=mock_check)
                mock_factory.return_value = evaluator

                context = await tool.knowledge_search("original query")

        assert "rich content" in context

    @pytest.mark.asyncio
    async def test_format_results_includes_source(self):
        """_format_results should include source path in output."""
        svc = _make_rag_service()
        tool = AgenticSearchTool(svc)

        result = _make_result("body text", source="docs/guide.md")
        formatted = tool._format_results([result])

        assert "docs/guide.md" in formatted
        assert "body text" in formatted

    @pytest.mark.asyncio
    async def test_format_results_empty_list(self):
        """_format_results([]) should return empty string."""
        svc = _make_rag_service()
        tool = AgenticSearchTool(svc)
        assert tool._format_results([]) == ""


# ---------------------------------------------------------------------------
# knowledge_search_tool module-level function
# ---------------------------------------------------------------------------


class TestKnowledgeSearchTool:
    @pytest.mark.asyncio
    async def test_delegates_to_agentic_tool(self):
        results = [_make_result("module result")]
        svc = _make_rag_service(results)
        cfg = AgenticSearchConfig(enable_agentic_search=False)

        ctx = await knowledge_search_tool("test", svc, config=cfg)
        assert "module result" in ctx


# ---------------------------------------------------------------------------
# get_agentic_search_tool singleton
# ---------------------------------------------------------------------------


class TestGetAgenticSearchTool:
    def test_returns_same_instance_for_same_service(self):
        """Singleton should be reused when rag_service is unchanged."""
        import knowledge.search_components.agentic_search as mod

        # Reset singleton for isolation
        mod._agentic_tool = None

        svc = _make_rag_service()
        t1 = get_agentic_search_tool(svc)
        t2 = get_agentic_search_tool(svc)
        assert t1 is t2

    def test_replaces_instance_when_service_changes(self):
        """Singleton should be replaced when a different rag_service is given."""
        import knowledge.search_components.agentic_search as mod

        mod._agentic_tool = None

        svc_a = _make_rag_service()
        svc_b = _make_rag_service()

        t1 = get_agentic_search_tool(svc_a)
        t2 = get_agentic_search_tool(svc_b)
        assert t1 is not t2
        assert t2.rag_service is svc_b


# ---------------------------------------------------------------------------
# AgenticSearchConfig validation
# ---------------------------------------------------------------------------


class TestAgenticSearchConfig:
    def test_defaults(self):
        cfg = AgenticSearchConfig()
        assert cfg.enable_agentic_search is True
        assert cfg.rewrite_enabled is True
        assert cfg.max_search_iterations == 3
        assert cfg.timeout_ms == 8000

    def test_custom_values(self):
        cfg = AgenticSearchConfig(
            enable_agentic_search=False,
            max_search_iterations=5,
            model="mistral:latest",
        )
        assert cfg.enable_agentic_search is False
        assert cfg.max_search_iterations == 5
        assert cfg.model == "mistral:latest"
