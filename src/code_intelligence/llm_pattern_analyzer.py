# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Integration Pattern Analyzer - Cost Optimization Engine

This module provides comprehensive analysis of LLM usage patterns in AutoBot
to optimize performance and reduce costs through:
- Prompt template analysis and optimization suggestions
- Token usage tracking and efficiency metrics
- Caching opportunity detection
- Batch processing pattern identification
- Cost estimation and savings calculation
- Retry pattern analysis
- Parallel call optimization

Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #229)
Refactored to fix Feature Envy code smells (Issue #312)

Note: This module has been refactored as part of Issue #381 god class refactoring.
All classes are now in the llm_pattern_analysis/ package. This module provides
backward compatibility by re-exporting all classes.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import all types, data models, and classes from the package (Issue #381 refactoring)
from src.code_intelligence.llm_pattern_analysis.types import (
    CacheOpportunityType,
    EXCESSIVE_CONTEXT_PATTERNS,
    FORMAT_INEFFICIENCY_PATTERNS,
    HIGH_PRIORITY_LEVELS,
    OptimizationCategory,
    OptimizationPriority,
    PromptIssueType,
    REDUNDANT_PATTERNS,
    RETRY_COUNT_PATTERNS,
    RETRY_LOGIC_PATTERNS,
    SIMPLE_LLM_MODELS,
    TEMPLATE_VAR_PATTERNS,
    UsagePatternType,
    VALID_BACKOFF_STRATEGIES,
)
from src.code_intelligence.llm_pattern_analysis.data_models import (
    AnalysisResult,
    BatchingOpportunity,
    CacheOpportunity,
    CostEstimate,
    OptimizationRecommendation,
    PromptAnalysisResult,
    PromptTemplate,
    RetryPattern,
    TokenUsage,
    UsagePattern,
)
from src.code_intelligence.llm_pattern_analysis.prompt_analyzer import PromptAnalyzer
from src.code_intelligence.llm_pattern_analysis.scanners import (
    BatchingAnalyzer,
    CacheOpportunityDetector,
    CodePatternScanner,
)
from src.code_intelligence.llm_pattern_analysis.calculators import (
    CostCalculator,
    TokenTracker,
)
from src.code_intelligence.llm_pattern_analysis.recommendation_engine import (
    RecommendationEngine,
)

logger = logging.getLogger(__name__)

# Backward compatibility aliases for module-level patterns
_REDUNDANT_PATTERNS = REDUNDANT_PATTERNS
_EXCESSIVE_CONTEXT_PATTERNS = EXCESSIVE_CONTEXT_PATTERNS
_FORMAT_INEFFICIENCY_PATTERNS = FORMAT_INEFFICIENCY_PATTERNS
_TEMPLATE_VAR_PATTERNS = TEMPLATE_VAR_PATTERNS
_RETRY_COUNT_PATTERNS = RETRY_COUNT_PATTERNS
_RETRY_LOGIC_PATTERNS = RETRY_LOGIC_PATTERNS
_VALID_BACKOFF_STRATEGIES = VALID_BACKOFF_STRATEGIES

# Re-export for backward compatibility
__all__ = [
    # Enums
    "OptimizationCategory",
    "OptimizationPriority",
    "CacheOpportunityType",
    "UsagePatternType",
    "PromptIssueType",
    # Constants
    "HIGH_PRIORITY_LEVELS",
    "SIMPLE_LLM_MODELS",
    # Data classes
    "TokenUsage",
    "PromptAnalysisResult",
    "PromptTemplate",
    "CacheOpportunity",
    "UsagePattern",
    "RetryPattern",
    "BatchingOpportunity",
    "CostEstimate",
    "OptimizationRecommendation",
    "AnalysisResult",
    # Classes
    "TokenTracker",
    "PromptAnalyzer",
    "CodePatternScanner",
    "CacheOpportunityDetector",
    "BatchingAnalyzer",
    "CostCalculator",
    "RecommendationEngine",
    "LLMPatternAnalyzer",
    # Convenience functions
    "analyze_llm_patterns",
    "get_optimization_categories",
    "get_optimization_priorities",
    "get_cache_opportunity_types",
    "get_usage_pattern_types",
    "get_prompt_issue_types",
    "estimate_prompt_tokens",
    "analyze_prompt",
]


# =============================================================================
# Main Analyzer Class
# =============================================================================


class LLMPatternAnalyzer:
    """
    Main LLM Pattern Analyzer for cost optimization.

    Coordinates all analysis components to provide comprehensive
    insights into LLM usage patterns and optimization opportunities.
    """

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize the analyzer.

        Args:
            project_root: Root directory of the project to analyze
        """
        self.project_root = project_root or Path.cwd()
        self.token_tracker = TokenTracker()
        self.analysis_history: List[AnalysisResult] = []

    def analyze(
        self,
        directories: Optional[List[Path]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> AnalysisResult:
        """
        Analyze the codebase for LLM patterns.

        Args:
            directories: Specific directories to analyze (default: src/)
            exclude_patterns: Glob patterns to exclude

        Returns:
            Complete analysis result
        """
        start_time = time.time()
        analysis_id = f"analysis_{int(start_time)}"

        # Default directories
        if directories is None:
            directories = [self.project_root / "src"]

        # Default exclusions
        if exclude_patterns is None:
            exclude_patterns = ["**/test*", "**/__pycache__", "**/venv"]

        # Collect all Python files
        python_files = self._collect_files(directories, exclude_patterns)

        # Scan all files
        all_patterns: List[UsagePattern] = []
        all_retry_patterns: List[RetryPattern] = []
        prompt_templates: List[PromptTemplate] = []

        for file_path in python_files:
            patterns, retries = CodePatternScanner.scan_file(file_path)
            all_patterns.extend(patterns)
            all_retry_patterns.extend(retries)

        # Detect opportunities
        cache_opportunities = CacheOpportunityDetector.detect_opportunities(all_patterns)
        batching_opportunities = BatchingAnalyzer.find_opportunities(all_patterns)

        # Calculate costs
        cost_estimates = CostCalculator.estimate_costs(all_patterns)

        # Generate recommendations
        recommendations = RecommendationEngine.generate_recommendations(
            patterns=all_patterns,
            cache_opportunities=cache_opportunities,
            batching_opportunities=batching_opportunities,
            retry_patterns=all_retry_patterns,
            cost_estimates=cost_estimates,
        )

        # Calculate total savings potential
        total_savings = sum(r.estimated_savings_percent for r in recommendations) / max(
            len(recommendations), 1
        )

        # Build result
        result = AnalysisResult(
            analysis_id=analysis_id,
            analysis_timestamp=datetime.now(),
            files_analyzed=len(python_files),
            patterns_found=all_patterns,
            prompt_templates=prompt_templates,
            cache_opportunities=cache_opportunities,
            batching_opportunities=batching_opportunities,
            retry_patterns=all_retry_patterns,
            cost_estimates=cost_estimates,
            recommendations=recommendations,
            total_estimated_savings_percent=total_savings,
            summary={
                "analysis_time_seconds": time.time() - start_time,
                "total_patterns": len(all_patterns),
                "total_opportunities": len(cache_opportunities)
                + len(batching_opportunities),
                "total_recommendations": len(recommendations),
                "estimated_monthly_cost": sum(c.monthly_cost_usd for c in cost_estimates),
                "estimated_optimized_cost": sum(
                    c.optimized_monthly_cost_usd for c in cost_estimates
                ),
            },
        )

        self.analysis_history.append(result)
        logger.info(
            f"Analysis complete: {len(all_patterns)} patterns, "
            f"{len(recommendations)} recommendations"
        )

        return result

    def _collect_files(
        self,
        directories: List[Path],
        exclude_patterns: List[str],
    ) -> List[Path]:
        """Collect Python files from directories."""
        files = []

        for directory in directories:
            if not directory.exists():
                continue

            for file_path in directory.rglob("*.py"):
                # Check exclusions
                excluded = False
                for pattern in exclude_patterns:
                    if file_path.match(pattern):
                        excluded = True
                        break

                if not excluded:
                    files.append(file_path)

        return files

    def get_summary_report(self, result: AnalysisResult) -> str:
        """
        Generate a human-readable summary report.

        Args:
            result: Analysis result to summarize

        Returns:
            Formatted summary string
        """
        lines = [
            "=" * 60,
            "LLM PATTERN ANALYSIS REPORT",
            "=" * 60,
            "",
            f"Analysis ID: {result.analysis_id}",
            f"Timestamp: {result.analysis_timestamp.isoformat()}",
            f"Files Analyzed: {result.files_analyzed}",
            "",
            "FINDINGS SUMMARY",
            "-" * 40,
            f"  Usage Patterns Found: {len(result.patterns_found)}",
            f"  Cache Opportunities: {len(result.cache_opportunities)}",
            f"  Batching Opportunities: {len(result.batching_opportunities)}",
            f"  Retry Patterns: {len(result.retry_patterns)}",
            "",
            "COST ANALYSIS",
            "-" * 40,
        ]

        for estimate in result.cost_estimates:
            lines.append(f"  Model: {estimate.model}")
            lines.append(f"    Daily Calls: {estimate.daily_calls}")
            lines.append(f"    Monthly Cost: ${estimate.monthly_cost_usd:.2f}")
            lines.append(f"    Optimized Cost: ${estimate.optimized_monthly_cost_usd:.2f}")
            lines.append("")

        lines.extend(
            [
                "TOP RECOMMENDATIONS",
                "-" * 40,
            ]
        )

        for rec in result.recommendations[:5]:
            lines.append(f"  [{rec.priority.value.upper()}] {rec.title}")
            lines.append(f"    Impact: {rec.impact}")
            lines.append(f"    Effort: {rec.effort}")
            lines.append("")

        lines.extend(
            [
                "ESTIMATED SAVINGS",
                "-" * 40,
                f"  Total Savings Potential: {result.total_estimated_savings_percent:.1f}%",
                "",
                "=" * 60,
            ]
        )

        return "\n".join(lines)


# =============================================================================
# Convenience Functions
# =============================================================================


def analyze_llm_patterns(
    project_root: Optional[Path] = None,
    directories: Optional[List[Path]] = None,
) -> AnalysisResult:
    """
    Convenience function to analyze LLM patterns.

    Args:
        project_root: Project root directory
        directories: Specific directories to analyze

    Returns:
        Analysis result
    """
    analyzer = LLMPatternAnalyzer(project_root)
    return analyzer.analyze(directories)


def get_optimization_categories() -> List[str]:
    """Get all optimization category values."""
    return [cat.value for cat in OptimizationCategory]


def get_optimization_priorities() -> List[str]:
    """Get all optimization priority values."""
    return [priority.value for priority in OptimizationPriority]


def get_cache_opportunity_types() -> List[str]:
    """Get all cache opportunity type values."""
    return [cache_type.value for cache_type in CacheOpportunityType]


def get_usage_pattern_types() -> List[str]:
    """Get all usage pattern type values."""
    return [pattern_type.value for pattern_type in UsagePatternType]


def get_prompt_issue_types() -> List[str]:
    """Get all prompt issue type values."""
    return [issue_type.value for issue_type in PromptIssueType]


def estimate_prompt_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    return PromptAnalyzer.estimate_tokens(text)


def analyze_prompt(prompt: str) -> Dict[str, Any]:
    """
    Analyze a prompt for issues.

    Args:
        prompt: Prompt text to analyze

    Returns:
        Analysis result with issues and suggestions
    """
    issues = PromptAnalyzer.analyze_prompt(prompt)
    result = PromptAnalysisResult(
        issues=issues,
        estimated_tokens=PromptAnalyzer.estimate_tokens(prompt),
        variables=PromptAnalyzer.extract_variables(prompt),
    )

    return {
        "issues": [issue.value for issue in result.issues],
        "suggestions": result.get_suggestions(prompt),
        "estimated_tokens": result.estimated_tokens,
        "variables": result.variables,
    }
