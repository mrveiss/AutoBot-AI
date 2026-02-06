# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Recommendation Engine Module

Generates optimization recommendations based on LLM pattern analysis results.
Combines insights from all analyzers to produce actionable recommendations.

Extracted from llm_pattern_analyzer.py as part of Issue #381 refactoring.
"""

from typing import List

from code_intelligence.llm_pattern_analysis.data_models import (
    BatchingOpportunity,
    CacheOpportunity,
    CostEstimate,
    OptimizationRecommendation,
    RetryPattern,
    UsagePattern,
)
from code_intelligence.llm_pattern_analysis.types import (
    OptimizationCategory,
    OptimizationPriority,
)


class RecommendationEngine:
    """
    Generates optimization recommendations based on analysis results.

    Combines insights from all analyzers to produce actionable recommendations.

    Refactored to use data class methods (Issue #312)
    Issue #281: Extracted helper methods for each recommendation category.
    """

    @classmethod
    def _get_caching_recommendations(
        cls,
        cache_opportunities: List[CacheOpportunity],
    ) -> List[OptimizationRecommendation]:
        """Generate caching recommendations from cache opportunities."""
        recommendations = []
        for cache_opp in cache_opportunities:
            if cache_opp.should_implement():
                rec = OptimizationRecommendation(
                    recommendation_id=f"rec_{cache_opp.opportunity_id}",
                    category=OptimizationCategory.CACHING,
                    priority=cache_opp.priority,
                    title=f"Implement {cache_opp.cache_type.value} caching",
                    description=cache_opp.description,
                    impact=f"~{cache_opp.estimated_savings_percent:.0f}% cost reduction",
                    implementation_steps=cache_opp.get_implementation_steps(),
                    estimated_savings_percent=cache_opp.estimated_savings_percent,
                    effort=cache_opp.implementation_effort,
                )
                recommendations.append(rec)
        return recommendations

    @classmethod
    def _get_batching_recommendations(
        cls,
        batching_opportunities: List[BatchingOpportunity],
    ) -> List[OptimizationRecommendation]:
        """Generate batching recommendations from batching opportunities."""
        significant_batching = [b for b in batching_opportunities if b.is_significant()]
        if not significant_batching:
            return []

        files = list(set(b.file_path for b in significant_batching))
        return [
            OptimizationRecommendation(
                recommendation_id="rec_batching_001",
                category=OptimizationCategory.BATCHING,
                priority=OptimizationPriority.MEDIUM,
                title="Batch similar LLM calls",
                description=f"Found {len(significant_batching)} opportunities to batch LLM calls",
                impact="~1.5x throughput improvement, reduced latency",
                implementation_steps=[
                    "Collect similar requests into batches",
                    "Use async parallel processing",
                    "Implement request deduplication",
                    "Add batch size limits",
                ],
                estimated_savings_percent=20.0,
                effort="medium",
                affected_files=files[:5],
            )
        ]

    @classmethod
    def _get_retry_recommendations(
        cls,
        retry_patterns: List[RetryPattern],
    ) -> List[OptimizationRecommendation]:
        """Generate retry strategy recommendations from retry patterns."""
        suboptimal_retries = [r for r in retry_patterns if not r.is_optimal()]
        if not suboptimal_retries:
            return []

        # Aggregate recommendations from all patterns
        all_recs = []
        for retry_pat in suboptimal_retries:
            all_recs.extend(retry_pat.get_optimization_recommendations())

        return [
            OptimizationRecommendation(
                recommendation_id="rec_retry_001",
                category=OptimizationCategory.RETRY_STRATEGY,
                priority=OptimizationPriority.HIGH,
                title="Optimize retry strategies",
                description=f"Found {len(suboptimal_retries)} suboptimal retry patterns",
                impact="Reduced latency, better error handling",
                implementation_steps=list(set(all_recs)),  # Deduplicate
                estimated_savings_percent=10.0,
                effort="low",
                affected_files=list(set(r.file_path for r in suboptimal_retries))[:5],
            )
        ]

    @classmethod
    def _get_token_recommendations(
        cls,
        patterns: List[UsagePattern],
    ) -> List[OptimizationRecommendation]:
        """Generate token optimization recommendations from usage patterns."""
        high_token_patterns = [p for p in patterns if p.is_high_token_usage()]
        if not high_token_patterns:
            return []

        return [
            OptimizationRecommendation(
                recommendation_id="rec_tokens_001",
                category=OptimizationCategory.TOKEN_OPTIMIZATION,
                priority=OptimizationPriority.MEDIUM,
                title="Reduce token usage in prompts",
                description=f"Found {len(high_token_patterns)} high-token patterns",
                impact="15-30% cost reduction per call",
                implementation_steps=[
                    "Review and compress system prompts",
                    "Remove redundant instructions",
                    "Use structured output formats",
                    "Implement context window management",
                ],
                estimated_savings_percent=25.0,
                effort="medium",
            )
        ]

    @classmethod
    def _get_model_selection_recommendations(
        cls,
        patterns: List[UsagePattern],
        cost_estimates: List[CostEstimate],
    ) -> List[OptimizationRecommendation]:
        """Generate model selection recommendations from cost estimates."""
        expensive_models = [e for e in cost_estimates if e.is_expensive_model()]
        if not expensive_models or len(patterns) <= 5:
            return []

        return [
            OptimizationRecommendation(
                recommendation_id="rec_model_001",
                category=OptimizationCategory.MODEL_SELECTION,
                priority=OptimizationPriority.HIGH,
                title="Use appropriate models for task complexity",
                description="Consider cheaper models for simple tasks",
                impact="50-80% cost reduction for eligible tasks",
                implementation_steps=[
                    "Classify tasks by complexity",
                    "Route simple tasks to smaller models",
                    "Implement model fallback chain",
                    "A/B test quality vs cost tradeoffs",
                ],
                estimated_savings_percent=40.0,
                effort="high",
            )
        ]

    @classmethod
    def _sort_by_priority(
        cls,
        recommendations: List[OptimizationRecommendation],
    ) -> List[OptimizationRecommendation]:
        """Sort recommendations by priority order."""
        priority_order = {
            OptimizationPriority.CRITICAL: 0,
            OptimizationPriority.HIGH: 1,
            OptimizationPriority.MEDIUM: 2,
            OptimizationPriority.LOW: 3,
            OptimizationPriority.INFO: 4,
        }
        recommendations.sort(key=lambda r: priority_order[r.priority])
        return recommendations

    @classmethod
    def generate_recommendations(
        cls,
        patterns: List[UsagePattern],
        cache_opportunities: List[CacheOpportunity],
        batching_opportunities: List[BatchingOpportunity],
        retry_patterns: List[RetryPattern],
        cost_estimates: List[CostEstimate],
    ) -> List[OptimizationRecommendation]:
        """
        Generate optimization recommendations.

        Issue #281: Refactored from 137 lines to use extracted helper methods.

        Args:
            patterns: Usage patterns found
            cache_opportunities: Caching opportunities
            batching_opportunities: Batching opportunities
            retry_patterns: Retry patterns
            cost_estimates: Cost estimates

        Returns:
            List of optimization recommendations sorted by priority
        """
        recommendations = []
        recommendations.extend(cls._get_caching_recommendations(cache_opportunities))
        recommendations.extend(cls._get_batching_recommendations(batching_opportunities))
        recommendations.extend(cls._get_retry_recommendations(retry_patterns))
        recommendations.extend(cls._get_token_recommendations(patterns))
        recommendations.extend(
            cls._get_model_selection_recommendations(patterns, cost_estimates)
        )
        return cls._sort_by_priority(recommendations)
