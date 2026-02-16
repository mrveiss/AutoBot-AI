# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Pattern Analyzer Data Models Module

Contains data classes for LLM pattern analysis results:
- TokenUsage, PromptAnalysisResult, PromptTemplate
- CacheOpportunity, UsagePattern, RetryPattern
- BatchingOpportunity, CostEstimate, OptimizationRecommendation
- AnalysisResult

Extracted from llm_pattern_analyzer.py as part of Issue #381 refactoring.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.code_intelligence.llm_pattern_analysis.types import (
    HIGH_PRIORITY_LEVELS,
    VALID_BACKOFF_STRATEGIES,
    CacheOpportunityType,
    OptimizationCategory,
    OptimizationPriority,
    PromptIssueType,
    UsagePatternType,
)

# =============================================================================
# Simple Data Classes
# =============================================================================


@dataclass
class TokenUsage:
    """Token usage statistics for an LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass
class PromptAnalysisResult:
    """
    Result of prompt analysis with integrated logic.

    Fixes Feature Envy: Encapsulates analysis data with its operations (Issue #312)
    """

    issues: List[PromptIssueType] = field(default_factory=list)
    estimated_tokens: int = 0
    variables: List[str] = field(default_factory=list)

    def get_suggestions(self, prompt_text: str) -> List[str]:
        """
        Generate improvement suggestions based on detected issues.

        Args:
            prompt_text: Original prompt text for context

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Get issue-specific suggestions
        for issue in self.issues:
            suggestions.append(issue.get_suggestion())

        # Add length-based suggestions
        if self.estimated_tokens > 2000:
            suggestions.append(
                f"Consider reducing prompt length (~{self.estimated_tokens} tokens)"
            )

        return suggestions

    def has_issue(self, issue_type: PromptIssueType) -> bool:
        """Check if a specific issue type is present."""
        return issue_type in self.issues

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "issues": [issue.value for issue in self.issues],
            "estimated_tokens": self.estimated_tokens,
            "variables": self.variables,
        }


@dataclass
class PromptTemplate:
    """Information about a detected prompt template."""

    template_id: str
    template_text: str
    variable_count: int
    usage_count: int = 0
    avg_token_count: int = 0
    file_path: Optional[str] = None
    line_number: int = 0
    issues: List[PromptIssueType] = field(default_factory=list)

    def analyze(self) -> PromptAnalysisResult:
        """
        Analyze this template for issues and optimization opportunities.

        Fixes Feature Envy: Template analyzes itself (Issue #312)
        """
        # Import here to avoid circular dependency
        from code_intelligence.llm_pattern_analysis.prompt_analyzer import (
            PromptAnalyzer,
        )

        issues = PromptAnalyzer.analyze_prompt(self.template_text)
        tokens = PromptAnalyzer.estimate_tokens(self.template_text)
        variables = PromptAnalyzer.extract_variables(self.template_text)

        return PromptAnalysisResult(
            issues=issues, estimated_tokens=tokens, variables=variables
        )

    def get_optimization_potential(self) -> float:
        """Calculate optimization potential based on issues."""
        if not self.issues:
            return 0.0

        # Weight different issue types
        weights = {
            PromptIssueType.REDUNDANT_INSTRUCTIONS: 0.3,
            PromptIssueType.EXCESSIVE_CONTEXT: 0.4,
            PromptIssueType.INEFFICIENT_FORMAT: 0.2,
            PromptIssueType.REPETITIVE_CONTENT: 0.3,
        }

        return min(sum(weights.get(issue, 0.1) for issue in self.issues), 1.0)


# =============================================================================
# Opportunity Data Classes
# =============================================================================


@dataclass
class CacheOpportunity:
    """A detected caching opportunity."""

    opportunity_id: str
    cache_type: CacheOpportunityType
    description: str
    estimated_hit_rate: float
    estimated_savings_percent: float
    affected_calls_per_hour: int = 0
    implementation_effort: str = "medium"
    priority: OptimizationPriority = OptimizationPriority.MEDIUM

    def should_implement(self) -> bool:
        """
        Determine if this caching opportunity should be implemented.

        Fixes Feature Envy: Opportunity decides for itself (Issue #312)
        """
        # High priority always worth implementing
        if self.priority in HIGH_PRIORITY_LEVELS:
            return True

        # Medium priority if savings are significant
        if self.estimated_savings_percent > 20.0:
            return True

        # Low effort with any savings is worth it
        if (
            self.implementation_effort == "low"
            and self.estimated_savings_percent > 10.0
        ):
            return True

        return False

    def get_implementation_steps(self) -> List[str]:
        """Get implementation steps based on cache type."""
        base_steps = [
            "Add Redis/in-memory cache layer",
            "Generate cache keys from prompt content hash",
            "Set appropriate TTL based on content freshness needs",
            "Add cache hit/miss metrics",
        ]

        type_specific = {
            CacheOpportunityType.EMBEDDING_CACHE: [
                "Hash input text for cache key",
                "Store embedding vectors in Redis",
                "Set long TTL (embeddings rarely change)",
            ],
            CacheOpportunityType.STATIC_PROMPT: [
                "Identify static prompt patterns",
                "Cache full responses with hash keys",
                "Monitor hit rates to adjust TTL",
            ],
            CacheOpportunityType.SEMANTIC_CACHE: [
                "Implement semantic similarity matching",
                "Use vector similarity for cache lookup",
                "Set threshold for similarity matches",
            ],
        }

        return base_steps + type_specific.get(self.cache_type, [])


@dataclass
class UsagePattern:
    """A detected LLM usage pattern."""

    pattern_id: str
    pattern_type: UsagePatternType
    file_path: str
    line_number: int
    code_snippet: str
    model_used: Optional[str] = None
    frequency: str = "unknown"
    token_estimate: int = 0
    optimization_potential: float = 0.0

    def is_high_token_usage(self) -> bool:
        """Check if this pattern uses high token counts."""
        return self.token_estimate > 1000

    def is_cacheable(self) -> bool:
        """Determine if this pattern is cacheable."""
        cacheable_types = {
            UsagePatternType.EMBEDDING,
            UsagePatternType.ANALYSIS,
        }
        return self.pattern_type in cacheable_types or self.optimization_potential > 0.5


@dataclass
class RetryPattern:
    """Information about retry patterns in LLM calls."""

    pattern_id: str
    file_path: str
    line_number: int
    max_retries: int
    backoff_strategy: str  # exponential, linear, fixed, none
    retry_conditions: List[str] = field(default_factory=list)
    has_timeout: bool = False
    timeout_value: Optional[float] = None
    issues: List[str] = field(default_factory=list)

    def is_optimal(self) -> bool:
        """
        Check if this retry pattern follows best practices.

        Fixes Feature Envy: Pattern evaluates itself (Issue #312)
        """
        # Optimal patterns have exponential backoff, reasonable retries, and timeout
        return (
            self.backoff_strategy == "exponential"
            and self.max_retries <= 3
            and self.has_timeout
        )

    def get_optimization_recommendations(self) -> List[str]:
        """Get specific recommendations for this retry pattern."""
        recommendations = []

        if self.backoff_strategy == "unknown":
            recommendations.append("Implement exponential backoff with jitter")

        if self.max_retries > 5:
            recommendations.append("Reduce max retries to 3")

        if not self.has_timeout:
            recommendations.append("Add timeout to prevent infinite hangs")

        if self.backoff_strategy not in VALID_BACKOFF_STRATEGIES:
            recommendations.append("Use exponential or linear backoff")

        return recommendations


@dataclass
class BatchingOpportunity:
    """A detected batching opportunity."""

    opportunity_id: str
    file_path: str
    related_calls: List[Tuple[int, str]]  # (line_number, call_description)
    estimated_speedup: float
    estimated_token_savings: int
    priority: OptimizationPriority = OptimizationPriority.MEDIUM

    def get_batch_size(self) -> int:
        """Get recommended batch size."""
        return len(self.related_calls)

    def is_significant(self) -> bool:
        """Check if this batching opportunity is significant."""
        return len(self.related_calls) >= 2 and self.estimated_speedup > 1.2


# =============================================================================
# Cost and Recommendation Data Classes
# =============================================================================


@dataclass
class CostEstimate:
    """Cost estimation for LLM usage."""

    model: str
    daily_calls: int
    avg_prompt_tokens: int
    avg_completion_tokens: int
    cost_per_1k_prompt: float
    cost_per_1k_completion: float
    daily_cost_usd: float
    monthly_cost_usd: float
    optimization_potential_percent: float = 0.0
    optimized_monthly_cost_usd: float = 0.0

    def get_monthly_savings(self) -> float:
        """Calculate monthly savings from optimization."""
        return self.monthly_cost_usd - self.optimized_monthly_cost_usd

    def is_expensive_model(self) -> bool:
        """Check if this is an expensive model."""
        expensive_markers = ["gpt-4", "opus", "claude-3-opus"]
        return any(marker in self.model.lower() for marker in expensive_markers)


@dataclass
class OptimizationRecommendation:
    """A specific optimization recommendation."""

    recommendation_id: str
    category: OptimizationCategory
    priority: OptimizationPriority
    title: str
    description: str
    impact: str
    implementation_steps: List[str]
    estimated_savings_percent: float
    effort: str  # low, medium, high
    affected_files: List[str] = field(default_factory=list)
    code_examples: Dict[str, str] = field(default_factory=dict)

    def should_prioritize(self) -> bool:
        """Determine if this recommendation should be prioritized."""
        return (
            self.priority in HIGH_PRIORITY_LEVELS
            or self.estimated_savings_percent > 30.0
        )


# =============================================================================
# Analysis Result
# =============================================================================


@dataclass
class AnalysisResult:
    """Complete result of LLM pattern analysis."""

    analysis_id: str
    analysis_timestamp: datetime
    files_analyzed: int
    patterns_found: List[UsagePattern]
    prompt_templates: List[PromptTemplate]
    cache_opportunities: List[CacheOpportunity]
    batching_opportunities: List[BatchingOpportunity]
    retry_patterns: List[RetryPattern]
    cost_estimates: List[CostEstimate]
    recommendations: List[OptimizationRecommendation]
    total_estimated_savings_percent: float = 0.0
    summary: Dict[str, Any] = field(default_factory=dict)

    def get_high_priority_recommendations(self) -> List[OptimizationRecommendation]:
        """Get only high-priority recommendations."""
        return [rec for rec in self.recommendations if rec.should_prioritize()]

    def get_total_monthly_cost(self) -> float:
        """Calculate total monthly cost across all models."""
        return sum(est.monthly_cost_usd for est in self.cost_estimates)

    def get_total_monthly_savings(self) -> float:
        """Calculate total potential monthly savings."""
        return sum(est.get_monthly_savings() for est in self.cost_estimates)
