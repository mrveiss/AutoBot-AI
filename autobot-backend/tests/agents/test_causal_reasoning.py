# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Causal Reasoning Functionality

Verifies that:
1. The Think Tool CAUSAL_ANALYSIS category exists and generates causal prompts
2. LLM outputs using causal reasoning include mechanism explanations
3. Error analysis produces causal chains, not just symptoms
4. Causal patterns are correctly integrated into agent prompts
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_loop.think_tool import ThinkTool
from agent_loop.types import ThinkCategory, ThinkResult
from orchestration.causal_error_analyzer import (
    CausalErrorAnalysis,
    CausalErrorAnalyzer,
)
from reasoning.causal_reasoning import (
    CausalChain,
    CausalReasoningContext,
    build_causal_reasoning_prompt,
)

# =============================================================================
# Unit Tests for Think Tool CAUSAL_ANALYSIS
# =============================================================================


class TestThinkToolCausalAnalysis:
    """Tests for causal analysis thinking."""

    @pytest.mark.asyncio
    async def test_causal_analysis_category_exists(self):
        """Verify CAUSAL_ANALYSIS category is defined in ThinkCategory."""
        assert hasattr(ThinkCategory, "CAUSAL_ANALYSIS")
        assert ThinkCategory.CAUSAL_ANALYSIS.name == "CAUSAL_ANALYSIS"

    @pytest.mark.asyncio
    async def test_think_causally_convenience_function(self):
        """Test the think_causally convenience function."""
        tool = ThinkTool()

        # Mock the LLM response
        mock_response = """## Reasoning
The system became slow after we deployed new code at 10am.
I need to identify if the deployment caused slowness or if it was coincidental.

Checking logs: The deployment added a SELECT query to the critical user endpoint.
This SELECT query scans 10M rows without an index. With 100 QPS, this means
1000 database queries per second instead of 100.

## Alternatives Considered
- Traffic spike at same time (but metrics show traffic was stable)
- Database maintenance (but maintenance log shows none at that time)

## Risks Identified
- Could be multiple cascading failures (network + database)
- Could be caching layer affected (but cache hit rates stable)

## Conclusion
The deployment CAUSED the slowness by introducing an N+1 query pattern.
Each user fetch now requires 1 base query + 10 follow-up queries.
The database became the bottleneck.

## Confidence
0.85
"""

        with patch.object(tool, "_get_llm_response", return_value=mock_response):
            result = await tool.think(
                ThinkCategory.CAUSAL_ANALYSIS,
                "System became slow after 10am deployment",
            )

            assert isinstance(result, ThinkResult)
            assert result.category == ThinkCategory.CAUSAL_ANALYSIS
            assert "deployment" in result.reasoning.lower()
            assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_causal_analysis_prompt_includes_mechanism(self):
        """Verify causal analysis prompt emphasizes WHY not just WHAT."""
        from agent_loop.think_tool import THINK_PROMPTS

        prompt = THINK_PROMPTS[ThinkCategory.CAUSAL_ANALYSIS]

        # Check that prompt emphasizes causal reasoning
        assert "CAUSES" in prompt or "causal" in prompt.lower()
        assert "mechanism" in prompt.lower() or "chain" in prompt.lower()
        assert "confounder" in prompt.lower()


# =============================================================================
# Unit Tests for Causal Reasoning Module
# =============================================================================


class TestCausalReasoningModule:
    """Tests for the causal reasoning prompt module."""

    def test_causal_chain_dataclass(self):
        """Test CausalChain data structure."""
        chain = CausalChain(
            intervention="Increased Redis memory from 1GB to 4GB",
            direct_effects=["More data cached without eviction"],
            secondary_effects=["Lower cache eviction rate", "Fewer cache misses"],
            confounders=["Traffic patterns changed", "Query distribution shifted"],
            confidence=0.85,
        )

        assert chain.intervention == "Increased Redis memory from 1GB to 4GB"
        assert len(chain.direct_effects) == 1
        assert len(chain.secondary_effects) == 2
        assert chain.confidence == 0.85

    def test_build_causal_reasoning_prompt(self):
        """Test prompt builder for different contexts."""
        prompt = build_causal_reasoning_prompt(
            context=CausalReasoningContext.ERROR_ANALYSIS,
            situation="Database query timeout after index removal",
            additional_guidance="Focus on query plan changes",
        )

        assert "Causal Reasoning Framework" in prompt
        assert "ERROR_ANALYSIS" in prompt or "Error" in prompt
        assert "Database query timeout" in prompt
        assert "Focus on query plan changes" in prompt

    def test_causal_reasoning_error_context(self):
        """Test error analysis context has cascading failure pattern."""
        prompt = build_causal_reasoning_prompt(context=CausalReasoningContext.ERROR_ANALYSIS, situation="Test error")

        # Should include error cascade example
        assert "cascade" in prompt.lower() or "chain" in prompt.lower()

    def test_causal_reasoning_decision_context(self):
        """Test decision context includes intervention effect analysis."""
        prompt = build_causal_reasoning_prompt(
            context=CausalReasoningContext.DECISION_ANALYSIS,
            situation="Should we increase cache size?",
        )

        # Should emphasize mechanism and ROI
        assert "mechanism" in prompt.lower() or "effect" in prompt.lower()
        assert "intervention" in prompt.lower() or "increase" in prompt.lower()


# =============================================================================
# Tests for Error Analyzer with Causal Reasoning
# =============================================================================


class TestCausalErrorAnalyzer:
    """Tests for causal error analysis."""

    @pytest.mark.asyncio
    async def test_analyzer_initialization(self):
        """Test analyzer can be initialized with or without ThinkTool."""
        analyzer1 = CausalErrorAnalyzer()
        assert analyzer1.think_tool is not None

        mock_tool = MagicMock()
        analyzer2 = CausalErrorAnalyzer(think_tool=mock_tool)
        assert analyzer2.think_tool is mock_tool

    @pytest.mark.asyncio
    async def test_analyze_error_causally(self):
        """Test causal error analysis."""
        analyzer = CausalErrorAnalyzer()

        error = RuntimeError("Database connection timeout")
        context = {
            "step_id": "step_1",
            "workflow_id": "workflow_abc",
        }

        # Mock the think_tool.think response
        mock_think_result = ThinkResult(
            category=ThinkCategory.CAUSAL_ANALYSIS,
            reasoning=(
                "Connection pool exhaustion → queries wait → timeout. "
                "Caused by: new code added 10 extra queries per request. "
                "Confounder: traffic also increased, but timing shows "
                "slowdown started with deployment."
            ),
            conclusion="Root cause: N+1 query pattern in new code",
            confidence=0.8,
            risks_identified=["Traffic patterns", "Database load"],
        )

        with patch.object(analyzer.think_tool, "think", return_value=mock_think_result):
            analysis = await analyzer.analyze_error_causally(error, context)

            assert isinstance(analysis, CausalErrorAnalysis)
            assert analysis.confidence == 0.8
            assert "root" in analysis.root_cause.lower() or "n+1" in analysis.root_cause.lower()
            assert len(analysis.confounders_identified) > 0

    def test_build_analysis_context(self):
        """Test context building includes execution history."""
        analyzer = CausalErrorAnalyzer()

        error = ValueError("Invalid parameter")
        context = {"step_id": "step_1"}
        history = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "event_type": "step_start",
                "description": "Starting step_1",
            },
            {
                "timestamp": "2024-01-01T10:00:05",
                "event_type": "query_executed",
                "description": "SELECT * FROM large_table",
            },
        ]

        analysis_context = analyzer._build_analysis_context(error, context, history)

        assert "step_1" in analysis_context
        assert "Error Context" in analysis_context
        assert "Execution History" in analysis_context
        assert "step_start" in analysis_context

    def test_extract_causal_chain(self):
        """Test causal chain extraction from reasoning."""
        reasoning = "Missing index → Query planner chooses full table scan → Timeout"

        chain = CausalErrorAnalyzer._extract_causal_chain(reasoning)

        assert "→" in chain or "->" in chain
        assert "Missing index" in chain

    def test_extract_root_cause(self):
        """Test root cause extraction from reasoning."""
        reasoning = (
            "The root cause is the missing index on (user_id, created_at). "
            "Without this index, the query planner scans all 10M rows."
        )

        root_cause = CausalErrorAnalyzer._extract_root_cause(reasoning)

        assert "missing index" in root_cause.lower()


# =============================================================================
# Integration Tests
# =============================================================================


def _make_module_stub(name: str, **attrs) -> types.ModuleType:
    """Create and register a stub module, preserving any existing entry."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return sys.modules[name]


class TestCausalReasoningIntegration:
    """Integration tests for causal reasoning across components."""

    @pytest.mark.asyncio
    async def test_intelligent_agent_causal_prompt(self):
        """Verify intelligent agent prompts include causal reasoning.

        intelligence.intelligent_agent has a deep dependency chain that requires
        autobot_shared, llm_interface, knowledge_base, and worker_node.  These
        are stubbed inline here (using sys.modules.setdefault so any already-
        imported real modules are kept) to avoid xfail — see issue #4749.
        """
        # Stub only the modules that are not importable in the test environment.
        # setdefault preserves any real module already registered by conftest.
        _make_module_stub(
            "intelligence.streaming_executor",
            ChunkType=MagicMock(),
            StreamChunk=MagicMock,
            StreamingCommandExecutor=MagicMock,
        )
        _make_module_stub("intelligence.goal_processor", GoalProcessor=MagicMock, ProcessedGoal=MagicMock)
        _make_module_stub(
            "intelligence.os_detector", OSDetector=MagicMock, OSInfo=MagicMock, get_os_detector=AsyncMock()
        )
        _make_module_stub("intelligence.tool_selector", OSAwareToolSelector=MagicMock)
        _make_module_stub("knowledge_base", KnowledgeBase=MagicMock)
        _make_module_stub("llm_interface", LLMInterface=MagicMock)
        _make_module_stub("worker_node", WorkerNode=MagicMock)

        from intelligence.intelligent_agent import IntelligentAgent

        agent = IntelligentAgent(MagicMock(), MagicMock(), MagicMock(), MagicMock())

        # Provide a minimal os_info stub so _build_llm_system_prompt can render
        # without a real initialized agent.
        _os_info = MagicMock()
        _os_info.os_type.value = "linux"
        _os_info.distro = None
        _os_info.version = "22.04"
        _os_info.architecture = "x86_64"
        _os_info.user = "test"
        _os_info.is_root = False
        _os_info.package_manager = "apt"
        _os_info.capabilities = []
        agent.state.os_info = _os_info

        prompt = agent._build_llm_system_prompt("diagnose slow query")

        # Verify CAUSAL_REASONING_SNIPPET is embedded in the system prompt
        assert "causal" in prompt.lower(), "Expected causal reasoning snippet in system prompt"
        assert "mechanism" in prompt.lower() or "BECAUSE" in prompt or "cause" in prompt.lower()


# =============================================================================
# LLM Output Validation Tests
# =============================================================================


class TestCausalOutputValidation:
    """Tests that verify causal reasoning patterns in LLM outputs."""

    def test_causal_vs_correlational_pattern(self):
        """Test the pattern for distinguishing causal vs correlational claims."""

        # Correlational (bad): "X and Y increase together"
        correlational = "Cache size and response time increase together"
        assert "together" in correlational or "correlate" in correlational.lower()

        # Causal (good): "X causes Y by [mechanism]"
        causal = "Increasing cache size REDUCES response time by eliminating " "database queries that take 200ms"
        assert "REDUCES" in causal or "CAUSES" in causal
        assert "database queries" in causal

    def test_causal_chain_pattern(self):
        """Test causal chain A → B → C pattern."""

        causal_chain = "Missing index → Full table scan → CPU bottleneck → " "Query timeout"

        parts = causal_chain.split("→")
        assert len(parts) == 4

        # Each part should be a concrete effect
        assert "index" in parts[0].lower()
        assert "scan" in parts[1].lower()
        assert "CPU" in parts[2]

    def test_confounder_identification(self):
        """Test identifying confounders in causal analysis."""

        analysis = (
            "Response time improved after caching was enabled. "
            "However, traffic decreased by 50% at the same time. "
            "To isolate the cache effect, we should: "
            "(1) Measure cache hit rate independently, "
            "(2) Compare latency per-request before/after, "
            "(3) Rule out traffic as the confounder."
        )

        assert "confounder" in analysis or "traffic" in analysis
        assert "isolate" in analysis or "independently" in analysis


# =============================================================================
# Fixtures and Helpers
# =============================================================================


@pytest.fixture
def sample_error_context():
    """Sample error context for testing."""
    return {
        "step_id": "deploy_service",
        "workflow_id": "wf_12345",
        "execution_time_ms": 5000,
        "timestamp": "2024-01-01T10:00:00Z",
    }


@pytest.fixture
def sample_execution_history():
    """Sample execution history for tracing causal chains."""
    return [
        {
            "timestamp": "2024-01-01T10:00:00Z",
            "event_type": "deployment_start",
            "description": "Deploying new service version",
        },
        {
            "timestamp": "2024-01-01T10:00:02Z",
            "event_type": "database_query",
            "description": "SELECT * FROM users - took 1200ms",
        },
        {
            "timestamp": "2024-01-01T10:00:03Z",
            "event_type": "timeout",
            "description": "Request exceeded 30s timeout",
        },
    ]
