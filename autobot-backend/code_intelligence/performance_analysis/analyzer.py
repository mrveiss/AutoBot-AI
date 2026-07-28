# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Performance Analyzer

Issue #381: Extracted from performance_analyzer.py god class refactoring.
Issue #554: Added Vector/Redis/LLM infrastructure for semantic analysis.
Contains the main PerformanceAnalyzer class and convenience functions.
"""

import re
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger
from code_intelligence.shared.analysis_base import (
    HAS_ANALYTICS_INFRASTRUCTURE,
    SIMILARITY_MEDIUM,
    BaseCodeAnalyzer,
)
from utils.line_index import LineIndex  # #12884

from .ast_visitor import PerformanceASTVisitor
from .types import PerformanceIssue, PerformanceIssueType, PerformanceSeverity

logger = get_logger(__name__)


class PerformanceAnalyzer(BaseCodeAnalyzer):
    """
    Main performance pattern analyzer.

    Issue #554: Now includes optional semantic analysis via ChromaDB/Redis/LLM
    infrastructure for detecting semantically similar performance issues.
    Issue #12660: The scan/cache skeleton (``__init__``, ``analyze_file``,
    ``analyze_directory``, ``analyze_directory_async``, ``_regex_analysis``,
    ``_should_exclude``, ``cache_analysis_results``, ``get_cached_analysis``)
    now lives in ``BaseCodeAnalyzer``; this class only provides the AST
    visitor, the performance-specific ``_check_*`` regex checkers, and the
    performance-shaped summary/report methods.
    """

    AST_VISITOR_CLASS = PerformanceASTVisitor
    SEMANTIC_COLLECTION_NAME = "performance_analysis_vectors"
    CACHE_PREFIX = "performance_analysis"

    def _check_list_lookup_pattern(self, file_path: str, content: str, lines: List[str]) -> List[PerformanceIssue]:
        """
        Check for list used as lookup (should be set).

        Issue #620.
        """
        findings: List[PerformanceIssue] = []
        list_lookup_pattern = r"if\s+\w+\s+in\s+\[.*\]:"

        # #12884: build the offset->line map once; the per-match
        # `content[:start].count()` was O(n*m) and held the GIL.
        _line_index = LineIndex(content)
        for match in re.finditer(list_lookup_pattern, content):
            line_num = _line_index.line_of(match.start())
            code = lines[line_num - 1] if line_num <= len(lines) else ""

            findings.append(
                PerformanceIssue(
                    issue_type=PerformanceIssueType.LIST_FOR_LOOKUP,
                    severity=PerformanceSeverity.LOW,
                    file_path=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    description="List literal used for membership check",
                    recommendation="Use set literal for O(1) lookup: if x in {...}",
                    estimated_complexity="O(n) → O(1)",
                    estimated_impact="Faster membership checks",
                    current_code=code.strip(),
                    confidence=0.9,
                )
            )
        return findings

    def _check_repeated_file_opens(self, file_path: str, content: str, lines: List[str]) -> List[PerformanceIssue]:
        """
        Check for repeated file opens in same file.

        Issue #620.
        """
        findings: List[PerformanceIssue] = []
        file_open_pattern = r"open\s*\([^)]+\)"
        open_calls = list(re.finditer(file_open_pattern, content))

        if len(open_calls) >= 3:
            findings.append(
                PerformanceIssue(
                    issue_type=PerformanceIssueType.REPEATED_FILE_OPEN,
                    severity=PerformanceSeverity.MEDIUM,
                    file_path=file_path,
                    line_start=1,
                    line_end=len(lines),
                    description=f"{len(open_calls)} file open() calls in same file",
                    recommendation="Consider caching file contents or using single open",
                    estimated_complexity="Multiple I/O operations",
                    estimated_impact="I/O overhead",
                    confidence=0.6,
                    metrics={"open_count": len(open_calls)},
                )
            )
        return findings

    # Issue #12362: Resource-acquisition calls that leak when not used as a
    # context manager or explicitly released. Mirrors the "memory_leaks"
    # category from the legacy code_analysis.src.performance_analyzer, which
    # had no equivalent in this canonical package (MEMORY_LEAK_RISK was
    # defined in types.py but never emitted).
    _UNCLOSED_RESOURCE_PATTERNS = (
        (r"open\s*\([^)]*\)(?!\s*(?:\.close\(\)|as\s+\w+))", "open()", "f.close() or a 'with' block"),
        (
            r"subprocess\.Popen\s*\([^)]*\)(?!\s*(?:\.wait\(\)|\.communicate\(\)|as\s+\w+))",
            "subprocess.Popen()",
            "proc.wait()/.communicate() or a 'with' block",
        ),
        (
            r"(?:sqlite3|psycopg2|pymysql)\.connect\s*\([^)]*\)(?!\s*(?:\.close\(\)|as\s+\w+))",
            "database connect()",
            "conn.close() or a 'with' block",
        ),
    )

    def _check_unclosed_resources(self, file_path: str, content: str, lines: List[str]) -> List[PerformanceIssue]:
        """
        Check for resource-acquiring calls not scoped by a context manager.

        Issue #12362: Fills the MEMORY_LEAK_RISK detection gap left when the
        legacy analyzer's regex-based "memory_leaks" category was not carried
        over during the #381 god-class refactor.
        """
        findings: List[PerformanceIssue] = []

        for pattern, call_desc, fix in self._UNCLOSED_RESOURCE_PATTERNS:
            # #12884: build the offset->line map once; the per-match
            # `content[:start].count()` was O(n*m) and held the GIL.
            _line_index = LineIndex(content)
            for match in re.finditer(pattern, content):
                # Skip matches already inside a 'with' statement on the same line.
                line_num = _line_index.line_of(match.start())
                code = lines[line_num - 1] if line_num <= len(lines) else ""
                if re.match(r"\s*with\b", code):
                    continue

                findings.append(
                    PerformanceIssue(
                        issue_type=PerformanceIssueType.MEMORY_LEAK_RISK,
                        severity=PerformanceSeverity.MEDIUM,
                        file_path=file_path,
                        line_start=line_num,
                        line_end=line_num,
                        description=f"{call_desc} not scoped by a context manager or explicitly released",
                        recommendation=f"Use {fix} to guarantee release on all code paths",
                        estimated_complexity="Unbounded resource growth",
                        estimated_impact="File descriptor / connection exhaustion under load",
                        current_code=code.strip(),
                        confidence=0.55,
                        potential_false_positive=True,
                        false_positive_reason=(
                            "Static regex cannot confirm the handle is released later in the same scope"
                        ),
                    )
                )

        return findings

    def _check_string_concat_in_loop(self, file_path: str, content: str, lines: List[str]) -> List[PerformanceIssue]:
        """
        Check for += with strings in loop-like context.

        Issue #620.
        """
        findings: List[PerformanceIssue] = []
        string_append_pattern = r"\w+\s*\+=\s*['\"]"

        # #12884: build the offset->line map once; the per-match
        # `content[:start].count()` was O(n*m) and held the GIL.
        _line_index = LineIndex(content)
        for match in re.finditer(string_append_pattern, content):
            line_num = _line_index.line_of(match.start())
            # Check if in a loop context (simple heuristic)
            context_start = max(0, line_num - 5)
            context = "\n".join(lines[context_start:line_num])

            if "for " in context or "while " in context:
                code = lines[line_num - 1] if line_num <= len(lines) else ""
                findings.append(
                    PerformanceIssue(
                        issue_type=PerformanceIssueType.EXCESSIVE_STRING_CONCAT,
                        severity=PerformanceSeverity.MEDIUM,
                        file_path=file_path,
                        line_start=line_num,
                        line_end=line_num,
                        description="String += in loop creates new objects",
                        recommendation="Use list.append() and ''.join()",
                        estimated_complexity="O(n²) string operations",
                        estimated_impact="Quadratic memory allocation",
                        current_code=code.strip(),
                        confidence=0.75,
                    )
                )
        return findings

    def _get_checkers(self) -> List[Callable[[str, str, List[str]], List[PerformanceIssue]]]:
        """Ordered regex checkers run by ``BaseCodeAnalyzer._regex_analysis``."""
        return [
            self._check_list_lookup_pattern,
            self._check_repeated_file_opens,
            self._check_string_concat_in_loop,
            self._check_unclosed_resources,
        ]

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of performance findings.

        Issue #686: Uses exponential decay scoring to prevent score overflow.
        Scores now degrade gracefully instead of immediately hitting 0.
        """
        # Import scoring utilities
        from code_intelligence.shared.scoring import (
            calculate_score_from_severity_counts,
            get_grade_from_score,
        )

        by_severity: Dict[str, int] = {}
        by_type: Dict[str, int] = {}

        for finding in self.results:
            sev = finding.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            itype = finding.issue_type.value
            by_type[itype] = by_type.get(itype, 0) + 1

        # Issue #686: Use exponential decay scoring instead of linear deduction
        # This prevents scores from immediately collapsing to 0 with many issues
        score = calculate_score_from_severity_counts(by_severity)

        total = len(self.results)
        critical = by_severity.get("critical", 0)
        high = by_severity.get("high", 0)

        # Issue #686: Use total_files_scanned instead of files with issues
        files_analyzed = (
            self.total_files_scanned if self.total_files_scanned > 0 else len(set(f.file_path for f in self.results))
        )

        return {
            "total_issues": total,
            "by_severity": by_severity,
            "by_type": by_type,
            "performance_score": score,
            "grade": get_grade_from_score(score),
            "critical_issues": critical,
            "high_issues": high,
            "files_analyzed": files_analyzed,
            "files_with_issues": len(set(f.file_path for f in self.results)),
            "top_issues": self._get_top_issues(),
        }

    def _get_top_issues(self) -> List[Dict[str, Any]]:
        """Get top issues by severity."""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        sorted_issues = sorted(self.results, key=lambda x: severity_order.get(x.severity.value, 5))
        return [issue.to_dict() for issue in sorted_issues[:5]]

    def generate_report(self, format: str = "json") -> str:
        """Generate performance report."""
        import json

        report = {
            "summary": self.get_summary(),
            "findings": [f.to_dict() for f in self.results],
            "recommendations": self._get_recommendations(),
        }

        if format == "json":
            return json.dumps(report, indent=2)
        elif format == "markdown":
            return self._generate_markdown_report(report)
        return json.dumps(report, indent=2)

    def _get_recommendations(self) -> List[str]:
        """Get performance recommendations based on findings."""
        recommendations = []
        seen_types: set = set()

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_findings = sorted(self.results, key=lambda x: severity_order.get(x.severity.value, 4))

        for finding in sorted_findings[:10]:
            if finding.issue_type not in seen_types:
                recommendations.append(f"[{finding.severity.value.upper()}] {finding.recommendation}")
                seen_types.add(finding.issue_type)

        return recommendations

    def _generate_markdown_report(self, report: Dict) -> str:
        """Generate markdown report."""
        md = ["# Performance Analysis Report\n"]

        summary = report["summary"]
        md.append("## Summary\n")
        md.append(f"- **Performance Score**: {summary['performance_score']}/100\n")
        md.append(f"- **Grade**: {summary['grade']}\n")
        md.append(f"- **Total Issues**: {summary['total_issues']}\n")
        md.append(f"- **Critical Issues**: {summary['critical_issues']}\n")
        md.append(f"- **High Issues**: {summary['high_issues']}\n\n")

        if report["recommendations"]:
            md.append("## Top Recommendations\n")
            for rec in report["recommendations"]:
                md.append(f"- {rec}\n")
            md.append("\n")

        if report["findings"]:
            md.append("## Issues Found\n")
            for finding in report["findings"][:20]:
                md.append(f"### {finding['issue_type']}\n")
                md.append(f"- **Severity**: {finding['severity']}\n")
                md.append(f"- **File**: {finding['file_path']}:{finding['line_start']}\n")
                md.append(f"- **Complexity**: {finding['estimated_complexity']}\n")
                md.append(f"- **Description**: {finding['description']}\n")
                md.append(f"- **Fix**: {finding['recommendation']}\n\n")

        return "".join(md)

    # Issue #554: Async semantic analysis methods
    # Issue #12660: analyze_directory_async/cache_analysis_results/
    # get_cached_analysis now live on BaseCodeAnalyzer; only the
    # domain-specific metadata_keys below remain here.

    async def _find_semantic_duplicates(
        self,
        items: List[PerformanceIssue],
    ) -> List[Dict[str, Any]]:
        """
        Find semantically similar performance issues using LLM embeddings.

        Issue #554: Uses the generic _find_semantic_duplicates_with_extraction
        helper from SemanticAnalysisMixin to reduce code duplication.

        Args:
            items: List of detected performance issues

        Returns:
            List of duplicate pairs with similarity scores
        """
        try:
            return await self._find_semantic_duplicates_with_extraction(
                items=items,
                code_extractors=["current_code"],
                metadata_keys={
                    "issue_type": "issue_type",
                    "file_path": "file_path",
                    "line_start": "line_start",
                    "description": "description",
                },
                min_similarity=(SIMILARITY_MEDIUM if HAS_ANALYTICS_INFRASTRUCTURE else 0.7),
            )
        except Exception as e:
            logger.warning("Semantic duplicate detection failed: %s", e)
            return []


def analyze_performance(directory: str | None = None, exclude_patterns: List[str] | None = None) -> Dict[str, Any]:
    """
    Convenience function to analyze performance of a directory.

    Args:
        directory: Directory to analyze (defaults to current directory)
        exclude_patterns: Patterns to exclude from analysis

    Returns:
        Dictionary with results and summary
    """
    analyzer = PerformanceAnalyzer(project_root=directory, exclude_patterns=exclude_patterns)
    results = analyzer.analyze_directory()

    return {
        "results": [r.to_dict() for r in results],
        "summary": analyzer.get_summary(),
        "report": analyzer.generate_report(format="markdown"),
    }


def get_performance_issue_types() -> List[Dict[str, str]]:
    """Get all supported performance issue types with descriptions."""
    type_descriptions = {
        PerformanceIssueType.N_PLUS_ONE_QUERY: "Database query inside loop",
        PerformanceIssueType.QUERY_IN_LOOP: "Query executed in loop body",
        PerformanceIssueType.NESTED_LOOP_COMPLEXITY: "Nested loops with high complexity",
        PerformanceIssueType.SYNC_IN_ASYNC: "Synchronous operation in async context",
        PerformanceIssueType.BLOCKING_IO_IN_ASYNC: "Blocking I/O in async function",
        PerformanceIssueType.SEQUENTIAL_AWAITS: "Sequential awaits that could be parallel",
        PerformanceIssueType.UNBOUNDED_COLLECTION: "Collection that grows without limit",
        PerformanceIssueType.EXCESSIVE_STRING_CONCAT: "String concatenation in loop",
        PerformanceIssueType.REPEATED_COMPUTATION: "Same computation repeated",
        PerformanceIssueType.LIST_FOR_LOOKUP: "List used for membership check",
        PerformanceIssueType.UNBATCHED_API_CALLS: "API calls not batched",
        PerformanceIssueType.QUADRATIC_COMPLEXITY: "O(n²) or higher complexity",
    }

    return [
        {
            "type": pt.value,
            "description": type_descriptions.get(pt, pt.name.replace("_", " ").title()),
            "category": _get_category(pt),
        }
        for pt in PerformanceIssueType
    ]


def _get_category_keywords() -> list:
    """Get keyword to category mapping (Issue #315)."""
    return [
        (("QUERY", "INSERT"), "Database"),
        (("LOOP", "COMPLEXITY"), "Algorithm"),
        (("ASYNC", "AWAIT", "SYNC"), "Async/Await"),
        (("MEMORY", "COLLECTION", "STRING"), "Memory"),
        (("CACHE", "COMPUTATION"), "Caching"),
        (("FILE", "IO"), "I/O"),
        (("API", "HTTP", "CONNECTION"), "Network"),
    ]


def _get_category(issue_type: PerformanceIssueType) -> str:
    """Get category for issue type (Issue #315 - reduced nesting)."""
    type_name = issue_type.name

    for keywords, category in _get_category_keywords():
        if any(kw in type_name for kw in keywords):
            return category

    return "General"


async def analyze_performance_async(
    directory: str | None = None,
    exclude_patterns: List[str] | None = None,
    use_semantic_analysis: bool = True,
    find_semantic_duplicates: bool = True,
) -> Dict[str, Any]:
    """
    Async convenience function to analyze performance with semantic analysis.

    Issue #554: Async version with ChromaDB/Redis/LLM infrastructure support.

    Args:
        directory: Directory to analyze (defaults to current directory)
        exclude_patterns: Patterns to exclude from analysis
        use_semantic_analysis: Whether to use LLM-based semantic analysis
        find_semantic_duplicates: Whether to find semantically similar issues

    Returns:
        Dictionary with results and summary including semantic matches
    """
    analyzer = PerformanceAnalyzer(
        project_root=directory,
        exclude_patterns=exclude_patterns,
        use_semantic_analysis=use_semantic_analysis,
    )
    return await analyzer.analyze_directory_async(
        find_semantic_duplicates=find_semantic_duplicates,
    )
