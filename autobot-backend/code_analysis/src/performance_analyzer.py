# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Performance Analyzer — deprecated legacy-shaped facade (Issue #12362).

This module used to contain a full, independent regex/AST scanning engine
that duplicated (and had diverged from) the canonical implementation at
``code_intelligence.performance_analysis``. It is kept as an import-
compatible shim — per the "never delete code" policy — for any caller that
still imports ``PerformanceAnalyzer``/``PerformanceIssue`` from this path.

The detection engine is now delegated entirely to the canonical
``code_intelligence.performance_analysis.PerformanceAnalyzer``. This class
adapts the modern, enum-typed ``PerformanceIssue`` (``line_start``/
``line_end``, ``PerformanceIssueType`` enum) to the legacy dataclass shape
below (``line_number``/``issue_type: str``) so that pre-existing callers of
``analyze_performance()`` keep receiving the same response contract.

DEPRECATED: New code should import directly from
``code_intelligence.performance_analysis`` instead.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from constants.ttl_constants import TTL_1_HOUR

from code_intelligence.performance_analysis import (
    PerformanceIssueType as _ModernIssueType,
)
from code_intelligence.performance_analysis import (
    PerformanceAnalyzer as _ModernPerformanceAnalyzer,
)
from code_intelligence.performance_analysis.types import (
    PerformanceIssue as _ModernPerformanceIssue,
)

logger = get_logger(__name__)


@dataclass
class PerformanceIssue:
    """Represents a performance issue in the codebase (legacy shape).

    Issue #12362: Preserved verbatim for backward compatibility. Field names
    (``line_number``, ``issue_type: str``) intentionally differ from the
    canonical ``code_intelligence.performance_analysis.types.PerformanceIssue``
    (``line_start``/``line_end``, ``PerformanceIssueType`` enum) — see
    ``PerformanceAnalyzer._adapt_issue`` below for the field mapping.
    """

    file_path: str
    line_number: int
    function_name: str | None
    issue_type: str  # memory_leak, blocking_call, inefficient_loop, etc.
    description: str
    severity: str  # critical, high, medium, low
    code_snippet: str
    suggestion: str
    estimated_impact: str  # high, medium, low


@dataclass
class PerformanceRecommendation:
    """Performance improvement recommendation (legacy shape)."""

    category: str  # memory, async, loops, database, etc.
    title: str
    description: str
    affected_files: List[str]
    priority: str
    code_examples: List[Dict[str, str]]  # before/after examples


# Issue #12362: Maps a canonical PerformanceIssueType to the legacy 6-bucket
# taxonomy (memory_leaks, blocking_calls, inefficient_loops, database_issues,
# concurrency_issues, resource_waste) that PerformanceIssue.issue_type /
# PerformanceRecommendation.category used pre-consolidation. Explicit at the
# consumer boundary per the type-divergence-handling requirement — every
# member of the modern enum is listed so a new addition to the canonical
# enum fails loudly (KeyError) instead of silently falling into a bucket.
_LEGACY_BUCKET_BY_ISSUE_TYPE: Dict[_ModernIssueType, str] = {
    # Query patterns -> database_issues
    _ModernIssueType.N_PLUS_ONE_QUERY: "database_issues",
    _ModernIssueType.QUERY_IN_LOOP: "database_issues",
    _ModernIssueType.MISSING_INDEX_HINT: "database_issues",
    _ModernIssueType.UNBATCHED_INSERTS: "database_issues",
    # Loop complexity -> inefficient_loops
    _ModernIssueType.NESTED_LOOP_COMPLEXITY: "inefficient_loops",
    _ModernIssueType.INEFFICIENT_LOOP: "inefficient_loops",
    _ModernIssueType.LOOP_INVARIANT_COMPUTATION: "inefficient_loops",
    _ModernIssueType.QUADRATIC_COMPLEXITY: "inefficient_loops",
    # Async/sync issues -> blocking_calls
    _ModernIssueType.SYNC_IN_ASYNC: "blocking_calls",
    _ModernIssueType.BLOCKING_IO_IN_ASYNC: "blocking_calls",
    _ModernIssueType.MISSING_AWAIT: "blocking_calls",
    _ModernIssueType.SEQUENTIAL_AWAITS: "blocking_calls",
    # Memory patterns -> memory_leaks
    _ModernIssueType.UNBOUNDED_COLLECTION: "memory_leaks",
    _ModernIssueType.LARGE_OBJECT_CREATION: "memory_leaks",
    _ModernIssueType.MEMORY_LEAK_RISK: "memory_leaks",
    _ModernIssueType.EXCESSIVE_STRING_CONCAT: "memory_leaks",
    # Cache patterns -> resource_waste (no direct legacy equivalent)
    _ModernIssueType.REPEATED_COMPUTATION: "resource_waste",
    _ModernIssueType.MISSING_CACHE: "resource_waste",
    _ModernIssueType.CACHE_STAMPEDE_RISK: "resource_waste",
    _ModernIssueType.INEFFICIENT_CACHE_KEY: "resource_waste",
    # Data structure issues -> resource_waste
    _ModernIssueType.LIST_FOR_LOOKUP: "resource_waste",
    _ModernIssueType.INEFFICIENT_DICT_ACCESS: "resource_waste",
    _ModernIssueType.REPEATED_LIST_APPEND: "resource_waste",
    # I/O patterns -> memory_leaks (unclosed handles = the old "memory_leaks"
    # regex category)
    _ModernIssueType.REPEATED_FILE_OPEN: "memory_leaks",
    _ModernIssueType.MISSING_CONTEXT_MANAGER: "memory_leaks",
    _ModernIssueType.INEFFICIENT_FILE_READ: "memory_leaks",
    # Network patterns -> resource_waste (old analyzer had no network bucket)
    _ModernIssueType.UNBATCHED_API_CALLS: "resource_waste",
    _ModernIssueType.MISSING_CONNECTION_POOL: "resource_waste",
    _ModernIssueType.REPEATED_HTTP_REQUESTS: "resource_waste",
}


class PerformanceAnalyzer:
    """Analyzes code for performance issues and memory leaks.

    Issue #12362: Legacy-shaped facade. Detection is delegated to the
    canonical ``code_intelligence.performance_analysis.PerformanceAnalyzer``;
    this class only adapts the response shape and preserves the Redis
    caching contract (``PERFORMANCE_KEY``/``RECOMMENDATIONS_KEY``) that
    existing callers of ``analyze_performance()`` rely on.
    """

    def __init__(self, redis_client=None):
        self.redis_client = redis_client  # Lazy init if None (#2725)

        # Caching keys
        self.PERFORMANCE_KEY = "perf_analysis:issues"
        self.RECOMMENDATIONS_KEY = "perf_analysis:recommendations"

        logger.info(
            "Performance Analyzer (deprecated legacy shim) initialized — "
            "delegating to code_intelligence.performance_analysis"
        )

    async def _ensure_redis(self):
        """Lazy-init async Redis client on first use (#2725)."""
        if self.redis_client is None:
            from autobot_shared.redis_client import get_async_redis_client

            self.redis_client = await get_async_redis_client()

    async def analyze_performance(self, root_path: str = ".", patterns: List[str] = None) -> Dict[str, Any]:
        """Analyze codebase for performance issues.

        Issue #12362: ``patterns`` is accepted for backward compatibility but
        is not used to filter — the canonical analyzer always scans ``*.py``
        files under ``root_path`` (matching the old default of
        ``["**/*.py"]``, the only pattern any known caller ever passed).
        """
        start_time = time.time()

        # Clear previous analysis cache
        await self._clear_cache()

        logger.info(f"Scanning for performance issues in {root_path}")
        modern_issues = await asyncio.to_thread(self._run_modern_analysis, root_path)
        performance_issues = [self._adapt_issue(issue) for issue in modern_issues]
        logger.info(f"Found {len(performance_issues)} potential performance issues")

        # Categorize and prioritize findings
        categorized = await self._categorize_issues(performance_issues)

        # Generate optimization recommendations
        recommendations = await self._generate_optimization_recommendations(categorized)

        # Calculate performance metrics
        metrics = self._calculate_performance_metrics(performance_issues, recommendations)

        analysis_time = time.time() - start_time

        results = {
            "total_performance_issues": len(performance_issues),
            "categories": {cat: len(issues) for cat, issues in categorized.items()},
            "critical_issues": len([i for i in performance_issues if i.severity == "critical"]),
            "high_priority_issues": len([i for i in performance_issues if i.severity == "high"]),
            "recommendations_count": len(recommendations),
            "analysis_time_seconds": analysis_time,
            "performance_details": [self._serialize_performance_issue(i) for i in performance_issues],
            "optimization_recommendations": [self._serialize_recommendation(r) for r in recommendations],
            "metrics": metrics,
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"Performance analysis complete in {analysis_time:.2f}s")
        return results

    def _run_modern_analysis(self, root_path: str) -> List[_ModernPerformanceIssue]:
        """Run the canonical analyzer synchronously (invoked via asyncio.to_thread)."""
        analyzer = _ModernPerformanceAnalyzer(project_root=root_path)
        return analyzer.analyze_directory()

    def _adapt_issue(self, issue: _ModernPerformanceIssue) -> PerformanceIssue:
        """Map a canonical PerformanceIssue onto the legacy dataclass shape."""
        legacy_bucket = _LEGACY_BUCKET_BY_ISSUE_TYPE.get(issue.issue_type, "resource_waste")
        return PerformanceIssue(
            file_path=issue.file_path,
            line_number=issue.line_start,
            function_name=None,  # Not tracked by the canonical analyzer either
            issue_type=legacy_bucket,
            description=issue.description,
            severity=issue.severity.value,
            code_snippet=issue.current_code,
            suggestion=issue.recommendation,
            estimated_impact=issue.estimated_impact,
        )

    async def _categorize_issues(self, performance_issues: List[PerformanceIssue]) -> Dict[str, List[PerformanceIssue]]:
        """Categorize performance issues"""

        categories: Dict[str, List[PerformanceIssue]] = {}
        for issue in performance_issues:
            if issue.issue_type not in categories:
                categories[issue.issue_type] = []
            categories[issue.issue_type].append(issue)

        return categories

    async def _generate_optimization_recommendations(
        self, categorized: Dict[str, List[PerformanceIssue]]
    ) -> List[PerformanceRecommendation]:
        """Generate optimization recommendations"""

        recommendations = []

        for category, issues in categorized.items():
            if not issues:
                continue

            # Group similar issues
            high_impact = [i for i in issues if i.severity in ["critical", "high"]]

            if high_impact:
                recommendation = PerformanceRecommendation(
                    category=category,
                    title=f"Optimize {category.replace('_', ' ').title()}",
                    description=f"Found {len(high_impact)} high-impact {category} issues",
                    affected_files=list(set(i.file_path for i in high_impact)),
                    priority="high" if len(high_impact) > 5 else "medium",
                    code_examples=self._generate_code_examples(category, high_impact[:3]),
                )
                recommendations.append(recommendation)

        return recommendations

    def _generate_code_examples(self, category: str, issues: List[PerformanceIssue]) -> List[Dict[str, str]]:
        """Generate before/after code examples"""

        examples = []

        example_templates = {
            "memory_leaks": {
                "before": 'f = open("file.txt", "r", encoding="utf-8")\ndata = f.read()',
                "after": 'with open("file.txt", "r", encoding="utf-8") as f:\n    data = f.read()',
            },
            "blocking_calls": {
                "before": "async def func():\n    time.sleep(1)",
                "after": "async def func():\n    await asyncio.sleep(1)",
            },
            "inefficient_loops": {
                "before": (
                    "result = []\nfor item in items:\n"
                    "    if condition(item):\n        result.append(transform(item))"
                ),
                "after": "result = [transform(item) for item in items if condition(item)]",
            },
            "database_issues": {
                "before": "for user in users:\n    profile = db.get_profile(user.id)",
                "after": "profiles = db.get_profiles_bulk([u.id for u in users])",
            },
        }

        template = example_templates.get(category)
        if template:
            examples.append(template)

        return examples

    def _calculate_performance_metrics(
        self,
        issues: List[PerformanceIssue],
        recommendations: List[PerformanceRecommendation],
    ) -> Dict[str, Any]:
        """Calculate performance analysis metrics"""

        severity_counts = {
            "critical": len([i for i in issues if i.severity == "critical"]),
            "high": len([i for i in issues if i.severity == "high"]),
            "medium": len([i for i in issues if i.severity == "medium"]),
            "low": len([i for i in issues if i.severity == "low"]),
        }

        category_counts: Dict[str, int] = {}
        for issue in issues:
            category_counts[issue.issue_type] = category_counts.get(issue.issue_type, 0) + 1

        file_counts = len(set(i.file_path for i in issues))

        return {
            "severity_breakdown": severity_counts,
            "category_breakdown": category_counts,
            "files_with_issues": file_counts,
            "optimization_potential": len(recommendations),
            "critical_memory_issues": severity_counts["critical"],
            "blocking_call_count": category_counts.get("blocking_calls", 0),
            "performance_debt_score": self._calculate_debt_score(severity_counts),
        }

    def _calculate_debt_score(self, severity_counts: Dict[str, int]) -> int:
        """Calculate technical debt score for performance"""
        weights = {"critical": 10, "high": 5, "medium": 2, "low": 1}
        return sum(count * weights[severity] for severity, count in severity_counts.items())

    def _serialize_performance_issue(self, issue: PerformanceIssue) -> Dict[str, Any]:
        """Serialize performance issue for output"""
        return {
            "file": issue.file_path,
            "line": issue.line_number,
            "function": issue.function_name,
            "type": issue.issue_type,
            "description": issue.description,
            "severity": issue.severity,
            "suggestion": issue.suggestion,
            "impact": issue.estimated_impact,
            "code_snippet": issue.code_snippet,
        }

    def _serialize_recommendation(self, rec: PerformanceRecommendation) -> Dict[str, Any]:
        """Serialize recommendation for output"""
        return {
            "category": rec.category,
            "title": rec.title,
            "description": rec.description,
            "affected_files": rec.affected_files,
            "priority": rec.priority,
            "code_examples": rec.code_examples,
        }

    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        await self._ensure_redis()
        if self.redis_client:
            try:
                key = self.PERFORMANCE_KEY
                value = json.dumps(results, default=str)
                await self.redis_client.setex(key, TTL_1_HOUR, value)
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def _clear_cache(self):
        """Clear analysis cache"""
        await self._ensure_redis()
        if self.redis_client:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(cursor, match="perf_analysis:*", count=100)
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")
