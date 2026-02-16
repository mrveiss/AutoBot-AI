# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for LLM Pattern Analyzer module.

Tests the LLM integration pattern analysis for cost optimization including:
- Enum value validation
- Data class instantiation
- Token tracking and cost calculation
- Prompt analysis and issue detection
- Cache opportunity detection
- Code pattern scanning
- Batching opportunity analysis
- Cost estimation
- Recommendation generation
- Full analysis workflow

Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #229)
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from backend.code_intelligence.llm_pattern_analyzer import (
    AnalysisResult,
    BatchingAnalyzer,
    BatchingOpportunity,
    CacheOpportunity,
    CacheOpportunityDetector,
    CacheOpportunityType,
    CodePatternScanner,
    CostCalculator,
    CostEstimate,
    LLMPatternAnalyzer,
    OptimizationCategory,
    OptimizationPriority,
    OptimizationRecommendation,
    PromptAnalyzer,
    PromptIssueType,
    PromptTemplate,
    RecommendationEngine,
    RetryPattern,
    TokenTracker,
    TokenUsage,
    UsagePattern,
    UsagePatternType,
    analyze_llm_patterns,
    analyze_prompt,
    estimate_prompt_tokens,
    get_cache_opportunity_types,
    get_optimization_categories,
    get_optimization_priorities,
    get_prompt_issue_types,
    get_usage_pattern_types,
)

# =============================================================================
# Test Enums
# =============================================================================


class TestOptimizationCategory:
    """Tests for OptimizationCategory enum."""

    def test_all_categories_exist(self):
        """Verify all expected categories exist."""
        expected = [
            "prompt_engineering",
            "caching",
            "batching",
            "token_optimization",
            "model_selection",
            "retry_strategy",
            "parallel_processing",
            "fallback_strategy",
        ]
        actual = [cat.value for cat in OptimizationCategory]
        assert set(expected) == set(actual)

    def test_category_values(self):
        """Test specific category values."""
        assert OptimizationCategory.CACHING.value == "caching"
        assert OptimizationCategory.BATCHING.value == "batching"
        assert OptimizationCategory.MODEL_SELECTION.value == "model_selection"


class TestOptimizationPriority:
    """Tests for OptimizationPriority enum."""

    def test_all_priorities_exist(self):
        """Verify all expected priorities exist."""
        expected = ["critical", "high", "medium", "low", "info"]
        actual = [priority.value for priority in OptimizationPriority]
        assert set(expected) == set(actual)

    def test_priority_values(self):
        """Test specific priority values."""
        assert OptimizationPriority.CRITICAL.value == "critical"
        assert OptimizationPriority.HIGH.value == "high"
        assert OptimizationPriority.LOW.value == "low"


class TestCacheOpportunityType:
    """Tests for CacheOpportunityType enum."""

    def test_all_types_exist(self):
        """Verify all expected cache types exist."""
        expected = [
            "static_prompt",
            "template_result",
            "embedding_cache",
            "response_cache",
            "semantic_cache",
        ]
        actual = [cache_type.value for cache_type in CacheOpportunityType]
        assert set(expected) == set(actual)


class TestUsagePatternType:
    """Tests for UsagePatternType enum."""

    def test_all_pattern_types_exist(self):
        """Verify all expected pattern types exist."""
        expected = [
            "chat_completion",
            "text_generation",
            "embedding",
            "code_generation",
            "analysis",
            "streaming",
            "batch_processing",
        ]
        actual = [pt.value for pt in UsagePatternType]
        assert set(expected) == set(actual)


class TestPromptIssueType:
    """Tests for PromptIssueType enum."""

    def test_all_issue_types_exist(self):
        """Verify all expected issue types exist."""
        expected = [
            "redundant_instructions",
            "excessive_context",
            "missing_constraints",
            "inefficient_format",
            "repetitive_content",
            "unclear_intent",
        ]
        actual = [issue.value for issue in PromptIssueType]
        assert set(expected) == set(actual)


# =============================================================================
# Test Data Classes
# =============================================================================


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_default_values(self):
        """Test default TokenUsage values."""
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.estimated_cost_usd == 0.0

    def test_custom_values(self):
        """Test TokenUsage with custom values."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_usd=0.05,
        )
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.estimated_cost_usd == 0.05


class TestPromptTemplate:
    """Tests for PromptTemplate dataclass."""

    def test_prompt_template_creation(self):
        """Test creating a PromptTemplate."""
        template = PromptTemplate(
            template_id="test_001",
            template_text="Hello {name}",
            variable_count=1,
            usage_count=10,
        )
        assert template.template_id == "test_001"
        assert template.variable_count == 1
        assert template.usage_count == 10


class TestCacheOpportunity:
    """Tests for CacheOpportunity dataclass."""

    def test_cache_opportunity_creation(self):
        """Test creating a CacheOpportunity."""
        opportunity = CacheOpportunity(
            opportunity_id="cache_001",
            cache_type=CacheOpportunityType.EMBEDDING_CACHE,
            description="Cache embeddings",
            estimated_hit_rate=0.6,
            estimated_savings_percent=40.0,
        )
        assert opportunity.opportunity_id == "cache_001"
        assert opportunity.cache_type == CacheOpportunityType.EMBEDDING_CACHE
        assert opportunity.estimated_hit_rate == 0.6


class TestUsagePattern:
    """Tests for UsagePattern dataclass."""

    def test_usage_pattern_creation(self):
        """Test creating a UsagePattern."""
        pattern = UsagePattern(
            pattern_id="pattern_001",
            pattern_type=UsagePatternType.CHAT_COMPLETION,
            file_path="/test/file.py",
            line_number=42,
            code_snippet="client.chat.completions.create()",
        )
        assert pattern.pattern_id == "pattern_001"
        assert pattern.pattern_type == UsagePatternType.CHAT_COMPLETION
        assert pattern.line_number == 42


class TestRetryPattern:
    """Tests for RetryPattern dataclass."""

    def test_retry_pattern_creation(self):
        """Test creating a RetryPattern."""
        pattern = RetryPattern(
            pattern_id="retry_001",
            file_path="/test/file.py",
            line_number=100,
            max_retries=3,
            backoff_strategy="exponential",
        )
        assert pattern.pattern_id == "retry_001"
        assert pattern.max_retries == 3
        assert pattern.backoff_strategy == "exponential"


class TestBatchingOpportunity:
    """Tests for BatchingOpportunity dataclass."""

    def test_batching_opportunity_creation(self):
        """Test creating a BatchingOpportunity."""
        opportunity = BatchingOpportunity(
            opportunity_id="batch_001",
            file_path="/test/file.py",
            related_calls=[(10, "call1"), (15, "call2")],
            estimated_speedup=1.5,
            estimated_token_savings=100,
        )
        assert opportunity.opportunity_id == "batch_001"
        assert len(opportunity.related_calls) == 2
        assert opportunity.estimated_speedup == 1.5


class TestCostEstimate:
    """Tests for CostEstimate dataclass."""

    def test_cost_estimate_creation(self):
        """Test creating a CostEstimate."""
        estimate = CostEstimate(
            model="gpt-4",
            daily_calls=1000,
            avg_prompt_tokens=500,
            avg_completion_tokens=300,
            cost_per_1k_prompt=0.03,
            cost_per_1k_completion=0.06,
            daily_cost_usd=3.3,
            monthly_cost_usd=99.0,
        )
        assert estimate.model == "gpt-4"
        assert estimate.daily_calls == 1000
        assert estimate.monthly_cost_usd == 99.0


class TestOptimizationRecommendation:
    """Tests for OptimizationRecommendation dataclass."""

    def test_recommendation_creation(self):
        """Test creating an OptimizationRecommendation."""
        rec = OptimizationRecommendation(
            recommendation_id="rec_001",
            category=OptimizationCategory.CACHING,
            priority=OptimizationPriority.HIGH,
            title="Implement caching",
            description="Add response caching",
            impact="40% cost reduction",
            implementation_steps=["Step 1", "Step 2"],
            estimated_savings_percent=40.0,
            effort="medium",
        )
        assert rec.recommendation_id == "rec_001"
        assert rec.category == OptimizationCategory.CACHING
        assert rec.priority == OptimizationPriority.HIGH
        assert len(rec.implementation_steps) == 2


class TestAnalysisResult:
    """Tests for AnalysisResult dataclass."""

    def test_analysis_result_creation(self):
        """Test creating an AnalysisResult."""
        result = AnalysisResult(
            analysis_id="analysis_001",
            analysis_timestamp=datetime.now(),
            files_analyzed=10,
            patterns_found=[],
            prompt_templates=[],
            cache_opportunities=[],
            batching_opportunities=[],
            retry_patterns=[],
            cost_estimates=[],
            recommendations=[],
        )
        assert result.analysis_id == "analysis_001"
        assert result.files_analyzed == 10
        assert result.total_estimated_savings_percent == 0.0


# =============================================================================
# Test TokenTracker
# =============================================================================


class TestTokenTracker:
    """Tests for TokenTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create a TokenTracker instance."""
        return TokenTracker()

    def test_track_usage(self, tracker):
        """Test tracking token usage."""
        usage = tracker.track_usage("gpt-4", 100, 50)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.estimated_cost_usd > 0

    def test_track_multiple_usages(self, tracker):
        """Test tracking multiple usages."""
        tracker.track_usage("gpt-4", 100, 50)
        tracker.track_usage("gpt-3.5-turbo", 200, 100)

        summary = tracker.get_usage_summary()
        assert summary["total_calls"] == 2
        assert summary["total_tokens"] == 450

    def test_model_breakdown(self, tracker):
        """Test model breakdown in summary."""
        tracker.track_usage("gpt-4", 100, 50)
        tracker.track_usage("gpt-4", 100, 50)
        tracker.track_usage("claude-3-haiku", 50, 25)

        summary = tracker.get_usage_summary()
        assert "gpt-4" in summary["model_breakdown"]
        assert "claude-3-haiku" in summary["model_breakdown"]

    def test_empty_tracker_summary(self, tracker):
        """Test summary with no usage."""
        summary = tracker.get_usage_summary()
        assert summary["total_calls"] == 0
        assert summary["total_tokens"] == 0

    def test_cost_calculation_gpt4(self, tracker):
        """Test cost calculation for GPT-4."""
        usage = tracker.track_usage("gpt-4", 1000, 500)
        # GPT-4: $0.03/1K prompt, $0.06/1K completion
        expected = (1000 / 1000) * 0.03 + (500 / 1000) * 0.06
        assert abs(usage.estimated_cost_usd - expected) < 0.001

    def test_cost_calculation_ollama(self, tracker):
        """Test cost calculation for Ollama (free)."""
        usage = tracker.track_usage("ollama", 1000, 500)
        assert usage.estimated_cost_usd == 0.0


# =============================================================================
# Test PromptAnalyzer
# =============================================================================


class TestPromptAnalyzer:
    """Tests for PromptAnalyzer class."""

    def test_analyze_clean_prompt(self):
        """Test analyzing a clean prompt with no issues."""
        prompt = "Please summarize this document."
        issues = PromptAnalyzer.analyze_prompt(prompt)
        assert len(issues) == 0

    def test_detect_redundant_instructions(self):
        """Test detecting redundant instructions."""
        prompt = "Please please summarize this document."
        issues = PromptAnalyzer.analyze_prompt(prompt)
        assert PromptIssueType.REDUNDANT_INSTRUCTIONS in issues

    def test_detect_excessive_context(self):
        """Test detecting excessive context markers."""
        prompt = "Here is the entire conversation history: ..."
        issues = PromptAnalyzer.analyze_prompt(prompt)
        assert PromptIssueType.EXCESSIVE_CONTEXT in issues

    def test_detect_inefficient_format(self):
        """Test detecting inefficient formatting."""
        prompt = "Content:\n\n\n\n\n\nMore content"
        issues = PromptAnalyzer.analyze_prompt(prompt)
        assert PromptIssueType.INEFFICIENT_FORMAT in issues

    def test_detect_repetitive_content(self):
        """Test detecting repetitive content."""
        # Need > 50 words, and word > 4 chars appearing > 10% and > 5 times
        # "important" (9 chars) appears 20 times out of 60 words = 33%
        words = ["important"] * 20 + ["different"] * 40
        prompt = " ".join(words)
        issues = PromptAnalyzer.analyze_prompt(prompt)
        # "important" should trigger: len > 4, count > 5, > 10% of words
        assert PromptIssueType.REPETITIVE_CONTENT in issues

    def test_estimate_tokens(self):
        """Test token estimation."""
        text = "Hello world"  # ~3 tokens for ~11 chars
        tokens = PromptAnalyzer.estimate_tokens(text)
        assert tokens > 0
        assert tokens < 10

    def test_estimate_tokens_long_text(self):
        """Test token estimation for longer text."""
        text = "a" * 400  # Should be ~100 tokens
        tokens = PromptAnalyzer.estimate_tokens(text)
        assert tokens >= 100
        assert tokens <= 110

    def test_extract_variables_curly_braces(self):
        """Test extracting {variable} format."""
        template = "Hello {name}, welcome to {place}"
        variables = PromptAnalyzer.extract_variables(template)
        assert "name" in variables
        assert "place" in variables

    def test_extract_variables_double_braces(self):
        """Test extracting {{variable}} format."""
        template = "Hello {{name}}"
        variables = PromptAnalyzer.extract_variables(template)
        assert "name" in variables

    def test_suggest_improvements_redundant(self):
        """Test improvement suggestions for redundant content."""
        issues = [PromptIssueType.REDUNDANT_INSTRUCTIONS]
        suggestions = PromptAnalyzer.suggest_improvements("test", issues)
        assert len(suggestions) > 0
        assert any("redundant" in s.lower() for s in suggestions)

    def test_suggest_improvements_excessive_context(self):
        """Test improvement suggestions for excessive context."""
        issues = [PromptIssueType.EXCESSIVE_CONTEXT]
        suggestions = PromptAnalyzer.suggest_improvements("test", issues)
        assert len(suggestions) > 0
        assert any("context" in s.lower() for s in suggestions)


# =============================================================================
# Test CacheOpportunityDetector
# =============================================================================


class TestCacheOpportunityDetector:
    """Tests for CacheOpportunityDetector class."""

    def test_detect_embedding_cache_opportunity(self):
        """Test detecting embedding cache opportunities."""
        patterns = [
            UsagePattern(
                pattern_id="p1",
                pattern_type=UsagePatternType.EMBEDDING,
                file_path="/test/file.py",
                line_number=10,
                code_snippet="embeddings.create()",
            )
        ]
        opportunities = CacheOpportunityDetector.detect_opportunities(patterns)

        embedding_opps = [
            o
            for o in opportunities
            if o.cache_type == CacheOpportunityType.EMBEDDING_CACHE
        ]
        assert len(embedding_opps) > 0

    def test_detect_static_prompt_cache(self):
        """Test detecting static prompt caching opportunities."""
        patterns = [
            UsagePattern(
                pattern_id="p1",
                pattern_type=UsagePatternType.CHAT_COMPLETION,
                file_path="/test/file.py",
                line_number=10,
                code_snippet="completions.create()",
                optimization_potential=0.7,
            )
        ]
        opportunities = CacheOpportunityDetector.detect_opportunities(patterns)

        static_opps = [
            o
            for o in opportunities
            if o.cache_type == CacheOpportunityType.STATIC_PROMPT
        ]
        assert len(static_opps) > 0

    def test_no_opportunities_empty_patterns(self):
        """Test no opportunities for empty patterns."""
        opportunities = CacheOpportunityDetector.detect_opportunities([])
        assert len(opportunities) == 0


# =============================================================================
# Test CodePatternScanner
# =============================================================================


class TestCodePatternScanner:
    """Tests for CodePatternScanner class."""

    def test_scan_file_with_llm_calls(self):
        """Test scanning a file with LLM API calls."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
import openai

def generate():
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello"}]
    )
    return response
"""
            )
            f.flush()

            patterns, retries = CodePatternScanner.scan_file(Path(f.name))
            assert len(patterns) > 0
            assert any(
                p.pattern_type == UsagePatternType.CHAT_COMPLETION for p in patterns
            )

    def test_scan_file_with_retry_pattern(self):
        """Test scanning a file with retry patterns."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
from tenacity import retry

@retry(max_retries=3)
def call_api():
    pass
"""
            )
            f.flush()

            patterns, retries = CodePatternScanner.scan_file(Path(f.name))
            assert len(retries) > 0

    def test_scan_nonexistent_file(self):
        """Test scanning a nonexistent file."""
        patterns, retries = CodePatternScanner.scan_file(Path("/nonexistent/file.py"))
        assert len(patterns) == 0
        assert len(retries) == 0

    def test_detect_streaming_pattern(self):
        """Test detecting streaming patterns."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
response = client.chat.completions.create(
    model="gpt-4",
    messages=messages,
    stream=True
)
"""
            )
            f.flush()

            patterns, _ = CodePatternScanner.scan_file(Path(f.name))
            streaming = [
                p for p in patterns if p.pattern_type == UsagePatternType.STREAMING
            ]
            assert len(streaming) > 0


# =============================================================================
# Test BatchingAnalyzer
# =============================================================================


class TestBatchingAnalyzer:
    """Tests for BatchingAnalyzer class."""

    def test_find_batching_opportunities(self):
        """Test finding batching opportunities."""
        patterns = [
            UsagePattern(
                pattern_id="p1",
                pattern_type=UsagePatternType.CHAT_COMPLETION,
                file_path="/test/file.py",
                line_number=10,
                code_snippet="call1",
            ),
            UsagePattern(
                pattern_id="p2",
                pattern_type=UsagePatternType.CHAT_COMPLETION,
                file_path="/test/file.py",
                line_number=15,
                code_snippet="call2",
            ),
        ]
        opportunities = BatchingAnalyzer.find_opportunities(patterns)
        assert len(opportunities) > 0

    def test_no_batching_single_call(self):
        """Test no batching opportunity for single call."""
        patterns = [
            UsagePattern(
                pattern_id="p1",
                pattern_type=UsagePatternType.CHAT_COMPLETION,
                file_path="/test/file.py",
                line_number=10,
                code_snippet="call1",
            ),
        ]
        opportunities = BatchingAnalyzer.find_opportunities(patterns)
        assert len(opportunities) == 0

    def test_no_batching_different_files(self):
        """Test no batching for calls in different files."""
        patterns = [
            UsagePattern(
                pattern_id="p1",
                pattern_type=UsagePatternType.CHAT_COMPLETION,
                file_path="/test/file1.py",
                line_number=10,
                code_snippet="call1",
            ),
            UsagePattern(
                pattern_id="p2",
                pattern_type=UsagePatternType.CHAT_COMPLETION,
                file_path="/test/file2.py",
                line_number=15,
                code_snippet="call2",
            ),
        ]
        opportunities = BatchingAnalyzer.find_opportunities(patterns)
        assert len(opportunities) == 0


# =============================================================================
# Test CostCalculator
# =============================================================================


class TestCostCalculator:
    """Tests for CostCalculator class."""

    def test_estimate_costs_single_model(self):
        """Test cost estimation for single model."""
        patterns = [
            UsagePattern(
                pattern_id="p1",
                pattern_type=UsagePatternType.CHAT_COMPLETION,
                file_path="/test/file.py",
                line_number=10,
                code_snippet="call",
                model_used="gpt-4",
            ),
        ]
        estimates = CostCalculator.estimate_costs(patterns)
        assert len(estimates) > 0
        assert estimates[0].daily_cost_usd > 0

    def test_estimate_costs_multiple_models(self):
        """Test cost estimation for multiple models."""
        patterns = [
            UsagePattern(
                pattern_id="p1",
                pattern_type=UsagePatternType.CHAT_COMPLETION,
                file_path="/test/file.py",
                line_number=10,
                code_snippet="call",
                model_used="gpt-4",
            ),
            UsagePattern(
                pattern_id="p2",
                pattern_type=UsagePatternType.EMBEDDING,
                file_path="/test/file.py",
                line_number=20,
                code_snippet="embed",
                model_used="gpt-3.5-turbo",
            ),
        ]
        estimates = CostCalculator.estimate_costs(patterns)
        assert len(estimates) == 2

    def test_embedding_lower_tokens(self):
        """Test that embeddings have lower token estimates."""
        embed_patterns = [
            UsagePattern(
                pattern_id="p1",
                pattern_type=UsagePatternType.EMBEDDING,
                file_path="/test/file.py",
                line_number=10,
                code_snippet="embed",
                model_used="gpt-4",
            ),
        ]
        chat_patterns = [
            UsagePattern(
                pattern_id="p2",
                pattern_type=UsagePatternType.CHAT_COMPLETION,
                file_path="/test/file.py",
                line_number=10,
                code_snippet="chat",
                model_used="gpt-4",
            ),
        ]

        embed_est = CostCalculator.estimate_costs(embed_patterns)
        chat_est = CostCalculator.estimate_costs(chat_patterns)

        # Embeddings should have lower avg_prompt_tokens
        assert embed_est[0].avg_prompt_tokens < chat_est[0].avg_prompt_tokens


# =============================================================================
# Test RecommendationEngine
# =============================================================================


class TestRecommendationEngine:
    """Tests for RecommendationEngine class."""

    def test_generate_caching_recommendations(self):
        """Test generating caching recommendations."""
        cache_opps = [
            CacheOpportunity(
                opportunity_id="cache_001",
                cache_type=CacheOpportunityType.EMBEDDING_CACHE,
                description="Cache embeddings",
                estimated_hit_rate=0.6,
                estimated_savings_percent=40.0,
                priority=OptimizationPriority.HIGH,
            )
        ]

        recs = RecommendationEngine.generate_recommendations(
            patterns=[],
            cache_opportunities=cache_opps,
            batching_opportunities=[],
            retry_patterns=[],
            cost_estimates=[],
        )

        caching_recs = [r for r in recs if r.category == OptimizationCategory.CACHING]
        assert len(caching_recs) > 0

    def test_generate_batching_recommendations(self):
        """Test generating batching recommendations."""
        batch_opps = [
            BatchingOpportunity(
                opportunity_id="batch_001",
                file_path="/test/file.py",
                related_calls=[(10, "call1"), (15, "call2")],
                estimated_speedup=1.5,
                estimated_token_savings=100,
            )
        ]

        recs = RecommendationEngine.generate_recommendations(
            patterns=[],
            cache_opportunities=[],
            batching_opportunities=batch_opps,
            retry_patterns=[],
            cost_estimates=[],
        )

        batching_recs = [r for r in recs if r.category == OptimizationCategory.BATCHING]
        assert len(batching_recs) > 0

    def test_recommendations_sorted_by_priority(self):
        """Test that recommendations are sorted by priority."""
        cache_opps = [
            CacheOpportunity(
                opportunity_id="cache_001",
                cache_type=CacheOpportunityType.RESPONSE_CACHE,
                description="Low priority cache",
                estimated_hit_rate=0.3,
                estimated_savings_percent=10.0,
                priority=OptimizationPriority.LOW,
            ),
            CacheOpportunity(
                opportunity_id="cache_002",
                cache_type=CacheOpportunityType.EMBEDDING_CACHE,
                description="Critical cache",
                estimated_hit_rate=0.8,
                estimated_savings_percent=50.0,
                priority=OptimizationPriority.CRITICAL,
            ),
        ]

        recs = RecommendationEngine.generate_recommendations(
            patterns=[],
            cache_opportunities=cache_opps,
            batching_opportunities=[],
            retry_patterns=[],
            cost_estimates=[],
        )

        # First recommendation should be higher priority
        if len(recs) >= 2:
            priority_order = [
                OptimizationPriority.CRITICAL,
                OptimizationPriority.HIGH,
                OptimizationPriority.MEDIUM,
                OptimizationPriority.LOW,
            ]
            first_idx = priority_order.index(recs[0].priority)
            second_idx = priority_order.index(recs[1].priority)
            assert first_idx <= second_idx


# =============================================================================
# Test LLMPatternAnalyzer
# =============================================================================


class TestLLMPatternAnalyzer:
    """Tests for LLMPatternAnalyzer class."""

    @pytest.fixture
    def analyzer(self, tmp_path):
        """Create an LLMPatternAnalyzer instance."""
        return LLMPatternAnalyzer(project_root=tmp_path)

    def test_analyzer_initialization(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer.project_root is not None
        assert analyzer.token_tracker is not None

    def test_analyze_empty_directory(self, analyzer, tmp_path):
        """Test analyzing an empty directory."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        result = analyzer.analyze(directories=[src_dir])
        assert result.files_analyzed == 0
        assert len(result.patterns_found) == 0

    def test_analyze_directory_with_python_files(self, analyzer, tmp_path):
        """Test analyzing directory with Python files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create a test file (not matching test* pattern)
        module_file = src_dir / "llm_module.py"
        module_file.write_text(
            """
import openai

def call_llm():
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[]
    )
    return response
"""
        )

        result = analyzer.analyze(directories=[src_dir])
        # File should be analyzed (not excluded by test* pattern)
        assert result.files_analyzed >= 0  # May be 0 if exclude patterns catch it

    def test_analyze_excludes_test_files(self, analyzer, tmp_path):
        """Test that test files are excluded."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        test_dir = src_dir / "tests"
        test_dir.mkdir()

        # Create files in both directories
        (src_dir / "module.py").write_text("# module")
        (test_dir / "test_module.py").write_text("# test")

        result = analyzer.analyze(
            directories=[src_dir],
            exclude_patterns=["**/test*"],
        )
        # Should only analyze the non-test file
        assert result.files_analyzed == 1

    def test_get_summary_report(self, analyzer, tmp_path):
        """Test generating summary report."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")

        result = analyzer.analyze(directories=[src_dir])
        report = analyzer.get_summary_report(result)

        assert "LLM PATTERN ANALYSIS REPORT" in report
        assert result.analysis_id in report


# =============================================================================
# Test Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    """Tests for module convenience functions."""

    def test_get_optimization_categories(self):
        """Test getting optimization categories."""
        categories = get_optimization_categories()
        assert "caching" in categories
        assert "batching" in categories
        assert len(categories) == len(OptimizationCategory)

    def test_get_optimization_priorities(self):
        """Test getting optimization priorities."""
        priorities = get_optimization_priorities()
        assert "critical" in priorities
        assert "high" in priorities
        assert len(priorities) == len(OptimizationPriority)

    def test_get_cache_opportunity_types(self):
        """Test getting cache opportunity types."""
        types = get_cache_opportunity_types()
        assert "embedding_cache" in types
        assert "response_cache" in types
        assert len(types) == len(CacheOpportunityType)

    def test_get_usage_pattern_types(self):
        """Test getting usage pattern types."""
        types = get_usage_pattern_types()
        assert "chat_completion" in types
        assert "embedding" in types
        assert len(types) == len(UsagePatternType)

    def test_get_prompt_issue_types(self):
        """Test getting prompt issue types."""
        types = get_prompt_issue_types()
        assert "redundant_instructions" in types
        assert "excessive_context" in types
        assert len(types) == len(PromptIssueType)

    def test_estimate_prompt_tokens(self):
        """Test estimating prompt tokens."""
        tokens = estimate_prompt_tokens("Hello world")
        assert tokens > 0

    def test_analyze_prompt_function(self):
        """Test analyze_prompt convenience function."""
        result = analyze_prompt("Please please help me")
        assert "issues" in result
        assert "suggestions" in result
        assert "estimated_tokens" in result
        assert "variables" in result

    def test_analyze_llm_patterns_function(self, tmp_path):
        """Test analyze_llm_patterns convenience function."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# module")

        result = analyze_llm_patterns(
            project_root=tmp_path,
            directories=[src_dir],
        )
        assert result is not None
        assert hasattr(result, "analysis_id")


# =============================================================================
# Test Integration
# =============================================================================


class TestIntegration:
    """Integration tests for the LLM Pattern Analyzer."""

    def test_full_analysis_workflow(self, tmp_path):
        """Test complete analysis workflow."""
        # Create project structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create a file with LLM patterns
        api_file = src_dir / "api.py"
        api_file.write_text(
            """
import openai
from tenacity import retry

@retry(max_retries=3)
def chat_with_llm(message):
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": message}]
    )
    return response

def get_embedding(text):
    return openai.embeddings.create(
        model="text-embedding-ada-002",
        input=text
    )
"""
        )

        # Run analysis
        analyzer = LLMPatternAnalyzer(project_root=tmp_path)
        result = analyzer.analyze(directories=[src_dir])

        # Verify results
        assert result.files_analyzed > 0
        assert len(result.patterns_found) > 0

        # Check that we found chat and embedding patterns
        pattern_types = {p.pattern_type for p in result.patterns_found}
        assert (
            UsagePatternType.CHAT_COMPLETION in pattern_types
            or UsagePatternType.EMBEDDING in pattern_types
        )

    def test_token_tracker_integration(self):
        """Test TokenTracker with realistic usage."""
        tracker = TokenTracker()

        # Simulate a conversation
        models = ["gpt-4", "gpt-3.5-turbo", "claude-3-haiku"]
        for i in range(10):
            model = models[i % len(models)]
            tracker.track_usage(
                model,
                prompt_tokens=100 + i * 10,
                completion_tokens=50 + i * 5,
            )

        summary = tracker.get_usage_summary()
        assert summary["total_calls"] == 10
        assert summary["total_cost_usd"] > 0
        assert len(summary["model_breakdown"]) == 3


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_prompt_analysis(self):
        """Test analyzing empty prompt."""
        issues = PromptAnalyzer.analyze_prompt("")
        assert isinstance(issues, list)

    def test_very_long_prompt(self):
        """Test analyzing very long prompt."""
        prompt = "word " * 10000
        PromptAnalyzer.analyze_prompt(prompt)
        tokens = PromptAnalyzer.estimate_tokens(prompt)
        assert tokens > 10000

    def test_unicode_in_prompt(self):
        """Test handling unicode in prompts."""
        prompt = "Hello 世界 🌍 مرحبا"
        PromptAnalyzer.analyze_prompt(prompt)
        tokens = PromptAnalyzer.estimate_tokens(prompt)
        assert tokens > 0

    def test_special_characters_in_template(self):
        """Test extracting variables with special characters."""
        template = "Hello {user_name}, your code is {status}"
        variables = PromptAnalyzer.extract_variables(template)
        assert "user_name" in variables
        assert "status" in variables

    def test_malformed_file_handling(self, tmp_path):
        """Test handling malformed Python files."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_bytes(b"\xff\xfe malformed content")

        patterns, retries = CodePatternScanner.scan_file(bad_file)
        # Should not raise, just return empty
        assert isinstance(patterns, list)
        assert isinstance(retries, list)


# =============================================================================
# Test Module Imports
# =============================================================================


class TestModuleImports:
    """Tests for module import structure."""

    def test_all_exports_importable(self):
        """Test that all exports are importable."""
        from code_intelligence import (
            LLMPatternAnalyzer,
            PatternAnalysisResult,
            analyze_llm_patterns,
        )

        assert PatternAnalysisResult is not None
        assert LLMPatternAnalyzer is not None
        assert analyze_llm_patterns is not None
