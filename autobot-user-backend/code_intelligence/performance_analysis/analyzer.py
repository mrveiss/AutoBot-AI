# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Analyzer

Issue #381: Extracted from performance_analyzer.py god class refactoring.
Issue #554: Added Vector/Redis/LLM infrastructure for semantic analysis.
Contains the main PerformanceAnalyzer class and convenience functions.
"""

import ast
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ast_visitor import PerformanceASTVisitor
from .types import PerformanceIssue, PerformanceIssueType, PerformanceSeverity

# Issue #554: Import analytics infrastructure for semantic analysis
try:
    from src.code_intelligence.analytics_infrastructure import (
        SIMILARITY_MEDIUM,
        SemanticAnalysisMixin,
    )

    HAS_ANALYTICS_INFRASTRUCTURE = True
except ImportError:
    HAS_ANALYTICS_INFRASTRUCTURE = False
    SemanticAnalysisMixin = object  # Fallback to object if not available

# Issue #607: Import shared caches for performance optimization
try:
    from src.code_intelligence.shared.ast_cache import get_ast_with_content

    HAS_SHARED_CACHE = True
except ImportError:
    HAS_SHARED_CACHE = False

logger = logging.getLogger(__name__)


class PerformanceAnalyzer(SemanticAnalysisMixin):
    """
    Main performance pattern analyzer.

    Issue #554: Now includes optional semantic analysis via ChromaDB/Redis/LLM
    infrastructure for detecting semantically similar performance issues.
    """

    def __init__(
        self,
        project_root: Optional[str] = None,
        exclude_patterns: Optional[List[str]] = None,
        use_semantic_analysis: bool = False,
        use_cache: bool = True,
        use_shared_cache: bool = True,
    ):
        """
        Initialize performance analyzer with project root and exclusion patterns.

        Args:
            project_root: Root directory for analysis
            exclude_patterns: Patterns to exclude from analysis
            use_semantic_analysis: Whether to use LLM-based semantic analysis (Issue #554)
            use_cache: Whether to use Redis caching for results (Issue #554)
            use_shared_cache: Whether to use shared FileListCache/ASTCache (Issue #607)
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.exclude_patterns = exclude_patterns or [
            "venv",
            "node_modules",
            ".git",
            "__pycache__",
            "*.pyc",
            "test_*",
            "*_test.py",
            "archives",
            "migrations",
        ]
        self.results: List[PerformanceIssue] = []
        self.total_files_scanned: int = 0  # Issue #686: Track total files analyzed
        self.use_semantic_analysis = (
            use_semantic_analysis and HAS_ANALYTICS_INFRASTRUCTURE
        )
        self.use_shared_cache = use_shared_cache and HAS_SHARED_CACHE

        # Issue #554: Initialize analytics infrastructure if semantic analysis enabled
        if self.use_semantic_analysis:
            self._init_infrastructure(
                collection_name="performance_analysis_vectors",
                use_llm=True,
                use_cache=use_cache,
                redis_database="analytics",
            )

    def analyze_file(self, file_path: str) -> List[PerformanceIssue]:
        """
        Analyze a single file for performance issues.

        Issue #607: Uses shared ASTCache when available for performance.
        """
        findings: List[PerformanceIssue] = []
        path = Path(file_path)

        if not path.exists() or not path.suffix == ".py":
            return findings

        try:
            # Issue #607: Use shared AST cache if available
            if self.use_shared_cache:
                tree, content = get_ast_with_content(file_path)
                lines = content.split("\n") if content else []
            else:
                content = path.read_text(encoding="utf-8")
                lines = content.split("\n")
                try:
                    tree = ast.parse(content)
                except SyntaxError:
                    tree = None

            # AST-based analysis
            if tree is not None:
                visitor = PerformanceASTVisitor(str(path), lines)
                visitor.visit(tree)
                findings.extend(visitor.findings)
            else:
                logger.warning("Syntax error in %s, skipping AST analysis", file_path)

            # Regex-based analysis for patterns AST can't catch
            if content:
                findings.extend(self._regex_analysis(str(path), content, lines))

        except Exception as e:
            logger.error("Error analyzing %s: %s", file_path, e)

        return findings

    def _check_list_lookup_pattern(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[PerformanceIssue]:
        """
        Check for list used as lookup (should be set).

        Issue #620.
        """
        findings: List[PerformanceIssue] = []
        list_lookup_pattern = r"if\s+\w+\s+in\s+\[.*\]:"

        for match in re.finditer(list_lookup_pattern, content):
            line_num = content[: match.start()].count("\n") + 1
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

    def _check_repeated_file_opens(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[PerformanceIssue]:
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

    def _check_string_concat_in_loop(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[PerformanceIssue]:
        """
        Check for += with strings in loop-like context.

        Issue #620.
        """
        findings: List[PerformanceIssue] = []
        string_append_pattern = r"\w+\s*\+=\s*['\"]"

        for match in re.finditer(string_append_pattern, content):
            line_num = content[: match.start()].count("\n") + 1
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

    def _regex_analysis(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[PerformanceIssue]:
        """
        Perform regex-based performance analysis.

        Issue #620: Refactored with extracted helper methods.
        """
        findings: List[PerformanceIssue] = []

        # Check for list used as lookup (Issue #620: uses helper)
        findings.extend(self._check_list_lookup_pattern(file_path, content, lines))

        # Check for repeated file opens (Issue #620: uses helper)
        findings.extend(self._check_repeated_file_opens(file_path, content, lines))

        # Check for string concat in loops (Issue #620: uses helper)
        findings.extend(self._check_string_concat_in_loop(file_path, content, lines))

        return findings

    def analyze_directory(
        self, directory: Optional[str] = None
    ) -> List[PerformanceIssue]:
        """Analyze all Python files in a directory."""
        target = Path(directory) if directory else self.project_root
        self.results = []
        self.total_files_scanned = 0  # Issue #686: Reset counter

        for py_file in target.rglob("*.py"):
            if self._should_exclude(py_file):
                continue

            self.total_files_scanned += 1  # Issue #686: Count all files scanned
            findings = self.analyze_file(str(py_file))
            self.results.extend(findings)

        return self.results

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        path_str = str(path)
        for pattern in self.exclude_patterns:
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                return True
        return False

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of performance findings.

        Issue #686: Uses exponential decay scoring to prevent score overflow.
        Scores now degrade gracefully instead of immediately hitting 0.
        """
        # Import scoring utilities
        from src.code_intelligence.shared.scoring import (
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
            self.total_files_scanned
            if self.total_files_scanned > 0
            else len(set(f.file_path for f in self.results))
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

    def _get_grade(self, score: int) -> str:
        """
        Get letter grade from score.

        DEPRECATED: Use get_grade_from_score from shared.scoring instead.
        Kept for backward compatibility.
        """
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        return "F"

    def _get_top_issues(self) -> List[Dict[str, Any]]:
        """Get top issues by severity."""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        sorted_issues = sorted(
            self.results, key=lambda x: severity_order.get(x.severity.value, 5)
        )
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
        sorted_findings = sorted(
            self.results, key=lambda x: severity_order.get(x.severity.value, 4)
        )

        for finding in sorted_findings[:10]:
            if finding.issue_type not in seen_types:
                recommendations.append(
                    f"[{finding.severity.value.upper()}] {finding.recommendation}"
                )
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
                md.append(
                    f"- **File**: {finding['file_path']}:{finding['line_start']}\n"
                )
                md.append(f"- **Complexity**: {finding['estimated_complexity']}\n")
                md.append(f"- **Description**: {finding['description']}\n")
                md.append(f"- **Fix**: {finding['recommendation']}\n\n")

        return "".join(md)

    # Issue #554: Async semantic analysis methods

    async def analyze_directory_async(
        self,
        directory: Optional[str] = None,
        find_semantic_duplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Analyze a directory with optional semantic analysis.

        Issue #554: Async version that supports ChromaDB/Redis/LLM infrastructure.

        Args:
            directory: Path to directory to analyze
            find_semantic_duplicates: Whether to find semantically similar issues

        Returns:
            Dictionary with analysis results including semantic matches
        """
        start_time = time.time()

        # Run standard analysis first
        results = self.analyze_directory(directory)

        result = {
            "results": [r.to_dict() for r in results],
            "summary": self.get_summary(),
            "semantic_duplicates": [],
            "infrastructure_metrics": {},
        }

        # Run semantic analysis if enabled
        if self.use_semantic_analysis and find_semantic_duplicates:
            semantic_dups = await self._find_semantic_performance_duplicates(results)
            result["semantic_duplicates"] = semantic_dups

            # Add infrastructure metrics
            result["infrastructure_metrics"] = self._get_infrastructure_metrics()

        result["analysis_time_ms"] = (time.time() - start_time) * 1000
        return result

    async def _find_semantic_performance_duplicates(
        self,
        issues: List[PerformanceIssue],
    ) -> List[Dict[str, Any]]:
        """
        Find semantically similar performance issues using LLM embeddings.

        Issue #554: Uses the generic _find_semantic_duplicates_with_extraction
        helper from SemanticAnalysisMixin to reduce code duplication.

        Args:
            issues: List of detected performance issues

        Returns:
            List of duplicate pairs with similarity scores
        """
        try:
            return await self._find_semantic_duplicates_with_extraction(
                items=issues,
                code_extractors=["current_code"],
                metadata_keys={
                    "issue_type": "issue_type",
                    "file_path": "file_path",
                    "line_start": "line_start",
                    "description": "description",
                },
                min_similarity=SIMILARITY_MEDIUM
                if HAS_ANALYTICS_INFRASTRUCTURE
                else 0.7,
            )
        except Exception as e:
            logger.warning("Semantic duplicate detection failed: %s", e)
            return []

    async def cache_analysis_results(
        self,
        directory: str,
        results: List[PerformanceIssue],
    ) -> bool:
        """
        Cache analysis results in Redis for faster retrieval.

        Issue #554: Uses Redis caching from analytics infrastructure.

        Args:
            directory: Analyzed directory path
            results: Analysis results to cache

        Returns:
            True if cached successfully
        """
        if not self.use_semantic_analysis:
            return False

        cache_key = self._generate_content_hash(directory)
        results_dict = {
            "results": [r.to_dict() for r in results],
            "summary": self.get_summary(),
        }

        return await self._cache_result(
            key=cache_key,
            result=results_dict,
            prefix="performance_analysis",
        )

    async def get_cached_analysis(
        self,
        directory: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached analysis results from Redis.

        Issue #554: Retrieves cached results for faster repeat analysis.

        Args:
            directory: Directory path to look up

        Returns:
            Cached analysis results or None if not found
        """
        if not self.use_semantic_analysis:
            return None

        cache_key = self._generate_content_hash(directory)
        return await self._get_cached_result(
            key=cache_key,
            prefix="performance_analysis",
        )


def analyze_performance(
    directory: Optional[str] = None, exclude_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convenience function to analyze performance of a directory.

    Args:
        directory: Directory to analyze (defaults to current directory)
        exclude_patterns: Patterns to exclude from analysis

    Returns:
        Dictionary with results and summary
    """
    analyzer = PerformanceAnalyzer(
        project_root=directory, exclude_patterns=exclude_patterns
    )
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
    directory: Optional[str] = None,
    exclude_patterns: Optional[List[str]] = None,
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
