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

from code_intelligence.llm_pattern_analysis.calculators import (
    CostCalculator,
    TokenTracker,
)
from code_intelligence.llm_pattern_analysis.data_models import (
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
from code_intelligence.llm_pattern_analysis.prompt_analyzer import PromptAnalyzer
from code_intelligence.llm_pattern_analysis.recommendation_engine import (
    RecommendationEngine,
)
from code_intelligence.llm_pattern_analysis.scanners import (
    BatchingAnalyzer,
    CacheOpportunityDetector,
    CodePatternScanner,
)

# Import all types, data models, and classes from the package (Issue #381 refactoring)
from code_intelligence.llm_pattern_analysis.types import (
    EXCESSIVE_CONTEXT_PATTERNS,
    FORMAT_INEFFICIENCY_PATTERNS,
    HIGH_PRIORITY_LEVELS,
    REDUNDANT_PATTERNS,
    RETRY_COUNT_PATTERNS,
    RETRY_LOGIC_PATTERNS,
    SIMPLE_LLM_MODELS,
    TEMPLATE_VAR_PATTERNS,
    VALID_BACKOFF_STRATEGIES,
    CacheOpportunityType,
    OptimizationCategory,
    OptimizationPriority,
    PromptIssueType,
    UsagePatternType,
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

    def _scan_files_for_patterns(
        self, python_files: List[Path]
    ) -> tuple[List[UsagePattern], List[RetryPattern]]:
        """Scan files and collect patterns (Issue #665: extracted helper)."""
        all_patterns: List[UsagePattern] = []
        all_retry_patterns: List[RetryPattern] = []

        for file_path in python_files:
            patterns, retries = CodePatternScanner.scan_file(file_path)
            all_patterns.extend(patterns)
            all_retry_patterns.extend(retries)

        return all_patterns, all_retry_patterns

    def _detect_opportunities_and_costs(
        self, all_patterns: List[UsagePattern]
    ) -> tuple[List[CacheOpportunity], List[BatchingOpportunity], List[CostEstimate]]:
        """Detect optimization opportunities and calculate costs (Issue #665: extracted helper)."""
        cache_opportunities = CacheOpportunityDetector.detect_opportunities(
            all_patterns
        )
        batching_opportunities = BatchingAnalyzer.find_opportunities(all_patterns)
        cost_estimates = CostCalculator.estimate_costs(all_patterns)
        return cache_opportunities, batching_opportunities, cost_estimates

    def _build_analysis_summary(
        self,
        start_time: float,
        all_patterns: List[UsagePattern],
        cache_opportunities: List[CacheOpportunity],
        batching_opportunities: List[BatchingOpportunity],
        recommendations: List[OptimizationRecommendation],
        cost_estimates: List[CostEstimate],
    ) -> Dict[str, Any]:
        """Build analysis summary dict (Issue #665: extracted helper)."""
        return {
            "analysis_time_seconds": time.time() - start_time,
            "total_patterns": len(all_patterns),
            "total_opportunities": len(cache_opportunities)
            + len(batching_opportunities),
            "total_recommendations": len(recommendations),
            "estimated_monthly_cost": sum(c.monthly_cost_usd for c in cost_estimates),
            "estimated_optimized_cost": sum(
                c.optimized_monthly_cost_usd for c in cost_estimates
            ),
        }

    def _get_default_directories_and_exclusions(
        self,
        directories: Optional[List[Path]],
        exclude_patterns: Optional[List[str]],
    ) -> tuple[List[Path], List[str]]:
        """
        Get default directories and exclusion patterns.

        Issue #620.
        """
        if directories is None:
            directories = [self.project_root / "src"]
        if exclude_patterns is None:
            exclude_patterns = ["**/test*", "**/__pycache__", "**/venv"]
        return directories, exclude_patterns

    def _generate_recommendations(
        self,
        all_patterns: List[UsagePattern],
        cache_opportunities: List[CacheOpportunity],
        batching_opportunities: List[BatchingOpportunity],
        all_retry_patterns: List[RetryPattern],
        cost_estimates: List[CostEstimate],
    ) -> List[OptimizationRecommendation]:
        """Generate optimization recommendations from analysis data. Issue #620."""
        return RecommendationEngine.generate_recommendations(
            patterns=all_patterns,
            cache_opportunities=cache_opportunities,
            batching_opportunities=batching_opportunities,
            retry_patterns=all_retry_patterns,
            cost_estimates=cost_estimates,
        )

    def _build_analysis_result(
        self,
        analysis_id: str,
        start_time: float,
        python_files: List[Path],
        all_patterns: List[UsagePattern],
        all_retry_patterns: List[RetryPattern],
        cache_opportunities: List[CacheOpportunity],
        batching_opportunities: List[BatchingOpportunity],
        cost_estimates: List[CostEstimate],
        recommendations: List[OptimizationRecommendation],
    ) -> AnalysisResult:
        """Build the final AnalysisResult object from collected data. Issue #620."""
        total_savings = sum(r.estimated_savings_percent for r in recommendations) / max(
            len(recommendations), 1
        )
        return AnalysisResult(
            analysis_id=analysis_id,
            analysis_timestamp=datetime.now(),
            files_analyzed=len(python_files),
            patterns_found=all_patterns,
            prompt_templates=[],
            cache_opportunities=cache_opportunities,
            batching_opportunities=batching_opportunities,
            retry_patterns=all_retry_patterns,
            cost_estimates=cost_estimates,
            recommendations=recommendations,
            total_estimated_savings_percent=total_savings,
            summary=self._build_analysis_summary(
                start_time,
                all_patterns,
                cache_opportunities,
                batching_opportunities,
                recommendations,
                cost_estimates,
            ),
        )

    def analyze(
        self,
        directories: Optional[List[Path]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> AnalysisResult:
        """Analyze the codebase for LLM patterns. Issue #620."""
        start_time = time.time()
        analysis_id = f"analysis_{int(start_time)}"

        directories, exclude_patterns = self._get_default_directories_and_exclusions(
            directories, exclude_patterns
        )
        python_files = self._collect_files(directories, exclude_patterns)
        all_patterns, all_retry_patterns = self._scan_files_for_patterns(python_files)
        cache_opps, batch_opps, costs = self._detect_opportunities_and_costs(
            all_patterns
        )
        recommendations = self._generate_recommendations(
            all_patterns, cache_opps, batch_opps, all_retry_patterns, costs
        )
        result = self._build_analysis_result(
            analysis_id,
            start_time,
            python_files,
            all_patterns,
            all_retry_patterns,
            cache_opps,
            batch_opps,
            costs,
            recommendations,
        )

        self.analysis_history.append(result)
        logger.info(
            "Analysis complete: %d patterns, %d recommendations",
            len(all_patterns),
            len(recommendations),
        )
        return result

    def _collect_files(
        self,
        directories: List[Path],
        exclude_patterns: List[str],
    ) -> List[Path]:
        """Collect Python files from directories.

        Issue #616: Optimized O(n³) → O(n²) using any() for early termination
        instead of manual break loop. The any() function short-circuits on
        first match, providing same O(1) behavior with cleaner code.
        """
        files = []

        for directory in directories:
            if not directory.exists():
                continue

            for file_path in directory.rglob("*.py"):
                # Issue #616: Use any() for O(1) early termination
                if not any(file_path.match(pattern) for pattern in exclude_patterns):
                    files.append(file_path)

        return files

    def _build_report_header(self, result: AnalysisResult) -> List[str]:
        """Build the header section of the summary report. Issue #620."""
        return [
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
        ]

    def _build_cost_analysis_section(
        self, cost_estimates: List[CostEstimate]
    ) -> List[str]:
        """Build the cost analysis section of the summary report. Issue #620."""
        lines = ["COST ANALYSIS", "-" * 40]
        for estimate in cost_estimates:
            lines.append(f"  Model: {estimate.model}")
            lines.append(f"    Daily Calls: {estimate.daily_calls}")
            lines.append(f"    Monthly Cost: ${estimate.monthly_cost_usd:.2f}")
            lines.append(
                f"    Optimized Cost: ${estimate.optimized_monthly_cost_usd:.2f}"
            )
            lines.append("")
        return lines

    def _build_recommendations_section(
        self, recommendations: List[OptimizationRecommendation]
    ) -> List[str]:
        """Build the top recommendations section of the summary report. Issue #620."""
        lines = ["TOP RECOMMENDATIONS", "-" * 40]
        for rec in recommendations[:5]:
            lines.append(f"  [{rec.priority.value.upper()}] {rec.title}")
            lines.append(f"    Impact: {rec.impact}")
            lines.append(f"    Effort: {rec.effort}")
            lines.append("")
        return lines

    def _build_savings_footer(self, savings_percent: float) -> List[str]:
        """Build the savings footer section of the summary report. Issue #620."""
        return [
            "ESTIMATED SAVINGS",
            "-" * 40,
            f"  Total Savings Potential: {savings_percent:.1f}%",
            "",
            "=" * 60,
        ]

    def get_summary_report(self, result: AnalysisResult) -> str:
        """Generate a human-readable summary report. Issue #620."""
        lines = self._build_report_header(result)
        lines.extend(self._build_cost_analysis_section(result.cost_estimates))
        lines.extend(self._build_recommendations_section(result.recommendations))
        lines.extend(self._build_savings_footer(result.total_estimated_savings_percent))
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
