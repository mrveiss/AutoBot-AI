# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Pattern Analysis API

Issue #222: Identifies performance anti-patterns like N+1 queries,
unnecessary loops, blocking I/O in async contexts, and cache misuse.
"""

import ast
import asyncio
import logging
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["performance", "analytics"])

# ============================================================================
# Models
# ============================================================================


class ImpactLevel(str, Enum):
    """Impact level of performance issues."""

    CRITICAL = "critical"  # Significant production impact
    HIGH = "high"  # Noticeable slowdown
    MEDIUM = "medium"  # Minor impact
    LOW = "low"  # Optimization opportunity


# Performance optimization: O(1) lookup for high-severity impact levels (Issue #326)
HIGH_SEVERITY_IMPACT_LEVELS = {ImpactLevel.CRITICAL, ImpactLevel.HIGH}

# Issue #380: Module-level frozenset for blocking call detection in async context
_BLOCKING_CALLS = frozenset({"sleep", "get", "post", "put", "delete", "request"})

# Issue #380: Module-level tuple for mutable default types
_MUTABLE_DEFAULT_TYPES = (ast.List, ast.Dict, ast.Set)


class PatternCategory(str, Enum):
    """Categories of performance patterns."""

    QUERY = "query"  # Database/API query patterns
    LOOP = "loop"  # Loop and iteration patterns
    ASYNC = "async"  # Async/await patterns
    CACHE = "cache"  # Caching patterns
    MEMORY = "memory"  # Memory usage patterns
    IO = "io"  # I/O operations


class PerformanceIssue(BaseModel):
    """A detected performance issue."""

    id: str
    pattern_id: str
    name: str
    category: PatternCategory
    impact: ImpactLevel
    file: str
    line: int
    column: int = 0
    description: str
    suggestion: str
    code_snippet: Optional[str] = None
    estimated_impact: Optional[str] = None  # e.g., "10x slower", "O(n²)"


class PerformanceAnalysisResult(BaseModel):
    """Result of performance analysis."""

    status: str = "success"
    total_issues: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    issues: list[PerformanceIssue]
    files_analyzed: int
    duration_ms: float
    timestamp: str
    score: int = Field(ge=0, le=100)  # Performance health score


class PatternDefinition(BaseModel):
    """Definition of a performance pattern to detect."""

    id: str
    name: str
    category: PatternCategory
    impact: ImpactLevel
    description: str
    suggestion: str
    regex_pattern: Optional[str] = None
    ast_check: bool = False
    enabled: bool = True


# ============================================================================
# Pattern Definitions
# ============================================================================

PERFORMANCE_PATTERNS: dict[str, PatternDefinition] = {
    # Query Patterns
    "PERF-Q001": PatternDefinition(
        id="PERF-Q001",
        name="N+1 Query Pattern",
        category=PatternCategory.QUERY,
        impact=ImpactLevel.CRITICAL,
        description="Database query inside loop - causes N+1 query problem",
        suggestion="Use eager loading, batch queries, or SELECT ... IN (...)",
        regex_pattern=r"for\s+\w+\s+in\s+\w+.*:\s*\n\s*.*(?:\.query|\.filter|\.get|\.execute|\.fetch|db\.\w+)",
        ast_check=True,
    ),
    "PERF-Q002": PatternDefinition(
        id="PERF-Q002",
        name="Unbounded Query",
        category=PatternCategory.QUERY,
        impact=ImpactLevel.HIGH,
        description="Query without LIMIT clause may return excessive results",
        suggestion="Add LIMIT clause or use pagination",
        regex_pattern=r"\.all\(\)\s*$|SELECT\s+\*\s+FROM\s+\w+(?!\s+(?:WHERE|LIMIT))",
    ),
    "PERF-Q003": PatternDefinition(
        id="PERF-Q003",
        name="SELECT * Usage",
        category=PatternCategory.QUERY,
        impact=ImpactLevel.MEDIUM,
        description="SELECT * retrieves all columns unnecessarily",
        suggestion="Specify only required columns",
        regex_pattern=r"SELECT\s+\*\s+FROM",
    ),
    # Loop Patterns
    "PERF-L001": PatternDefinition(
        id="PERF-L001",
        name="Nested Loop O(n²)",
        category=PatternCategory.LOOP,
        impact=ImpactLevel.HIGH,
        description="Nested loops with O(n²) complexity",
        suggestion="Consider using dict/set for O(1) lookup or algorithm optimization",
        ast_check=True,
    ),
    "PERF-L002": PatternDefinition(
        id="PERF-L002",
        name="List Concatenation in Loop",
        category=PatternCategory.LOOP,
        impact=ImpactLevel.MEDIUM,
        description="Repeated list concatenation in loop is O(n²)",
        suggestion="Use list.append() or list comprehension",
        regex_pattern=r"for\s+\w+\s+in\s+\w+.*:\s*\n\s*\w+\s*\+\s*=\s*\[",
    ),
    "PERF-L003": PatternDefinition(
        id="PERF-L003",
        name="String Concatenation in Loop",
        category=PatternCategory.LOOP,
        impact=ImpactLevel.MEDIUM,
        description="String concatenation in loop creates many temporary objects",
        suggestion="Use str.join() or io.StringIO",
        regex_pattern=r"for\s+\w+\s+in\s+\w+.*:\s*\n\s*\w+\s*\+\s*=\s*['\"]",
    ),
    # Async Patterns
    "PERF-A001": PatternDefinition(
        id="PERF-A001",
        name="Sync Call in Async Function",
        category=PatternCategory.ASYNC,
        impact=ImpactLevel.CRITICAL,
        description="Blocking synchronous call in async function blocks event loop",
        suggestion="Use async version or run_in_executor()",
        regex_pattern=r"async\s+def\s+\w+.*:\s*\n(?:.*\n)*?\s*(?:time\.sleep|requests\.|urllib\.request|open\()",
    ),
    "PERF-A002": PatternDefinition(
        id="PERF-A002",
        name="Sequential Awaits",
        category=PatternCategory.ASYNC,
        impact=ImpactLevel.HIGH,
        description="Multiple awaits that could run concurrently",
        suggestion="Use asyncio.gather() for concurrent execution",
        regex_pattern=r"await\s+\w+\([^)]*\)\s*\n\s*await\s+\w+\(",
    ),
    "PERF-A003": PatternDefinition(
        id="PERF-A003",
        name="Missing Await",
        category=PatternCategory.ASYNC,
        impact=ImpactLevel.HIGH,
        description="Async function called without await",
        suggestion="Add await keyword before async function call",
        ast_check=True,
    ),
    # Cache Patterns
    "PERF-C001": PatternDefinition(
        id="PERF-C001",
        name="Repeated Redis GET in Loop",
        category=PatternCategory.CACHE,
        impact=ImpactLevel.HIGH,
        description="Multiple Redis GET calls in loop",
        suggestion="Use MGET for batch retrieval or pipeline",
        regex_pattern=r"for\s+\w+\s+in\s+\w+.*:\s*\n(?:.*\n)*?\s*redis.*\.get\(",
    ),
    "PERF-C002": PatternDefinition(
        id="PERF-C002",
        name="Missing Cache TTL",
        category=PatternCategory.CACHE,
        impact=ImpactLevel.MEDIUM,
        description="Cache set without expiration may cause memory issues",
        suggestion="Add TTL/expiration to cache entries",
        regex_pattern=r"\.set\s*\([^,]+,[^,]+\)\s*$",
    ),
    "PERF-C003": PatternDefinition(
        id="PERF-C003",
        name="Cache Key Without Prefix",
        category=PatternCategory.CACHE,
        impact=ImpactLevel.LOW,
        description="Cache key without namespace prefix may cause collisions",
        suggestion="Use namespaced keys like 'app:entity:id'",
        regex_pattern=r"\.(?:get|set)\s*\(\s*['\"][a-z0-9_]+['\"]",
    ),
    # Memory Patterns
    "PERF-M001": PatternDefinition(
        id="PERF-M001",
        name="Global Mutable Default",
        category=PatternCategory.MEMORY,
        impact=ImpactLevel.HIGH,
        description="Mutable default argument causes shared state bug",
        suggestion="Use None default and create mutable in function body",
        regex_pattern=r"def\s+\w+\([^)]*(?:\[\]|\{\}|set\(\))\s*[,)]",
    ),
    "PERF-M002": PatternDefinition(
        id="PERF-M002",
        name="Large List Comprehension",
        category=PatternCategory.MEMORY,
        impact=ImpactLevel.MEDIUM,
        description="List comprehension over large data creates full list in memory",
        suggestion="Use generator expression for memory efficiency",
        regex_pattern=r"\[\s*\w+\s+for\s+\w+\s+in\s+(?:range\(\d{5,}|\.all\(\))",
    ),
    "PERF-M003": PatternDefinition(
        id="PERF-M003",
        name="Reading Entire File",
        category=PatternCategory.MEMORY,
        impact=ImpactLevel.MEDIUM,
        description="Reading entire file into memory at once",
        suggestion="Use line-by-line iteration or chunked reading",
        regex_pattern=r"\.read\(\)\s*$|\.readlines\(\)",
    ),
    # I/O Patterns
    "PERF-I001": PatternDefinition(
        id="PERF-I001",
        name="Unbuffered File Write",
        category=PatternCategory.IO,
        impact=ImpactLevel.MEDIUM,
        description="Many small writes without buffering",
        suggestion="Use buffered writes or write larger chunks",
        regex_pattern=r"for\s+\w+\s+in\s+\w+.*:\s*\n(?:.*\n)*?\s*\w+\.write\(",
    ),
    "PERF-I002": PatternDefinition(
        id="PERF-I002",
        name="Multiple File Opens",
        category=PatternCategory.IO,
        impact=ImpactLevel.LOW,
        description="Opening same file multiple times in function",
        suggestion="Open file once and reuse handle",
        regex_pattern=r"open\(['\"][^'\"]+['\"]\).*\n(?:.*\n)*?open\(['\"][^'\"]+['\"]\)",
    ),
}

# In-memory storage
_analysis_history: list[PerformanceAnalysisResult] = []
_analysis_history_lock = asyncio.Lock()


# ============================================================================
# AST-based Analysis
# ============================================================================


class PerformanceVisitor(ast.NodeVisitor):
    """AST visitor for detecting performance issues."""

    def __init__(self, filename: str):
        """Initialize visitor with filename and tracking state."""
        self.filename = filename
        self.issues: list[PerformanceIssue] = []
        self.in_async_function = False
        self.in_loop = False
        self.loop_depth = 0
        self.current_function = ""

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visit async function and track async context for blocking call detection."""
        old_state = self.in_async_function
        self.in_async_function = True
        self.current_function = node.name
        self.generic_visit(node)
        self.in_async_function = old_state

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function and detect mutable default argument issues."""
        self.current_function = node.name
        # Check for mutable default arguments
        for default in node.args.defaults:
            if isinstance(default, _MUTABLE_DEFAULT_TYPES):  # Issue #380
                self.issues.append(
                    PerformanceIssue(
                        id=f"issue-{len(self.issues)}",
                        pattern_id="PERF-M001",
                        name="Global Mutable Default",
                        category=PatternCategory.MEMORY,
                        impact=ImpactLevel.HIGH,
                        file=self.filename,
                        line=node.lineno,
                        description="Mutable default argument causes shared state bug",
                        suggestion="Use None default and create mutable in function body",
                    )
                )
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        """Visit for loop and detect nested loop performance issues."""
        old_in_loop = self.in_loop
        old_depth = self.loop_depth
        self.in_loop = True
        self.loop_depth += 1

        # Check for nested loops (O(n²))
        if old_depth > 0:
            self.issues.append(
                PerformanceIssue(
                    id=f"issue-{len(self.issues)}",
                    pattern_id="PERF-L001",
                    name="Nested Loop O(n²)",
                    category=PatternCategory.LOOP,
                    impact=ImpactLevel.HIGH,
                    file=self.filename,
                    line=node.lineno,
                    description=f"Nested loop at depth {self.loop_depth} - O(n^{self.loop_depth})",
                    suggestion="Consider using dict/set for O(1) lookup",
                    estimated_impact=f"O(n^{self.loop_depth})",
                )
            )

        self.generic_visit(node)
        self.in_loop = old_in_loop
        self.loop_depth = old_depth

    def visit_While(self, node: ast.While):
        """Visit while loop using same nested loop detection as for loops."""
        old_in_loop = self.in_loop
        old_depth = self.loop_depth
        self.in_loop = True
        self.loop_depth += 1

        # Check for nested loops (O(n²))
        if old_depth > 0:
            self.issues.append(
                PerformanceIssue(
                    id=f"issue-{len(self.issues)}",
                    pattern_id="PERF-L001",
                    name="Nested Loop O(n²)",
                    category=PatternCategory.LOOP,
                    impact=ImpactLevel.HIGH,
                    file=self.filename,
                    line=node.lineno,
                    description=f"Nested loop at depth {self.loop_depth} - O(n^{self.loop_depth})",
                    suggestion="Consider using dict/set for O(1) lookup",
                    estimated_impact=f"O(n^{self.loop_depth})",
                )
            )

        self.generic_visit(node)
        self.in_loop = old_in_loop
        self.loop_depth = old_depth

    def visit_Call(self, node: ast.Call):
        """Visit function call and detect blocking calls in async context."""
        # Check for sync calls in async function
        if self.in_async_function:
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id

            if func_name in _BLOCKING_CALLS:  # Issue #380: use module constant
                self.issues.append(
                    PerformanceIssue(
                        id=f"issue-{len(self.issues)}",
                        pattern_id="PERF-A001",
                        name="Sync Call in Async Function",
                        category=PatternCategory.ASYNC,
                        impact=ImpactLevel.CRITICAL,
                        file=self.filename,
                        line=node.lineno,
                        description=f"Blocking call '{func_name}' in async function blocks event loop",
                        suggestion="Use async version or run_in_executor()",
                    )
                )

        self.generic_visit(node)


def analyze_with_ast(filepath: str, content: str) -> list[PerformanceIssue]:
    """Analyze code using AST for performance issues."""
    try:
        tree = ast.parse(content)
        visitor = PerformanceVisitor(filepath)
        visitor.visit(tree)
        return visitor.issues
    except SyntaxError:
        return []


# ============================================================================
# Regex-based Analysis
# ============================================================================


def analyze_with_regex(
    filepath: str, content: str, patterns: dict[str, PatternDefinition]
) -> list[PerformanceIssue]:
    """Analyze code using regex patterns."""
    issues: list[PerformanceIssue] = []
    lines = content.split("\n")

    for pattern_id, pattern in patterns.items():
        if not pattern.enabled or not pattern.regex_pattern:
            continue

        try:
            regex = re.compile(pattern.regex_pattern, re.MULTILINE)
            for match in regex.finditer(content):
                # Find line number
                line_start = content[: match.start()].count("\n") + 1

                # Get snippet
                snippet_start = max(0, line_start - 2)
                snippet_end = min(len(lines), line_start + 2)
                snippet = "\n".join(
                    f"{i}: {lines[i-1]}"
                    for i in range(snippet_start + 1, snippet_end + 1)
                    if i <= len(lines)
                )

                issues.append(
                    PerformanceIssue(
                        id=f"issue-{len(issues)}",
                        pattern_id=pattern_id,
                        name=pattern.name,
                        category=pattern.category,
                        impact=pattern.impact,
                        file=filepath,
                        line=line_start,
                        description=pattern.description,
                        suggestion=pattern.suggestion,
                        code_snippet=snippet[:500],
                    )
                )
        except re.error as e:
            logger.warning("Invalid regex in pattern %s: %s", pattern_id, e)

    return issues


# ============================================================================
# API Endpoints
# ============================================================================


async def _get_files_to_analyze(target_path: Path) -> list[Path]:
    """Get list of Python files to analyze (Issue #398: extracted).

    Args:
        target_path: Target file or directory path

    Returns:
        List of Python file paths to analyze
    """
    is_file = await asyncio.to_thread(target_path.is_file)
    if is_file:
        return [target_path]

    is_dir = await asyncio.to_thread(target_path.is_dir)
    if is_dir:
        all_py_files = await asyncio.to_thread(lambda: list(target_path.rglob("*.py")))
        return all_py_files[:100]  # Limit files

    return []  # Path not found


def _deduplicate_issues(issues: list[PerformanceIssue]) -> list[PerformanceIssue]:
    """Remove duplicate issues by file/line/pattern (Issue #398: extracted)."""
    seen = set()
    unique = []
    for issue in issues:
        key = (issue.file, issue.line, issue.pattern_id)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def _calculate_analysis_score(
    issues: list[PerformanceIssue],
) -> tuple[int, int, int, int, int]:
    """Calculate issue counts and performance score (Issue #398: extracted).

    Returns:
        Tuple of (critical, high, medium, low, score)
    """
    critical = sum(1 for i in issues if i.impact == ImpactLevel.CRITICAL)
    high = sum(1 for i in issues if i.impact == ImpactLevel.HIGH)
    medium = sum(1 for i in issues if i.impact == ImpactLevel.MEDIUM)
    low = sum(1 for i in issues if i.impact == ImpactLevel.LOW)

    deductions = critical * 20 + high * 10 + medium * 5 + low * 2
    score = max(0, 100 - min(100, deductions))

    return critical, high, medium, low, score


@router.get("/analyze", response_model=None)
async def analyze_path(
    path: str = Query(..., description="Path to analyze"),
    include_ast: bool = Query(True, description="Include AST analysis"),
    admin_check: bool = Depends(check_admin_permission),
):
    """Analyze code for performance anti-patterns (Issue #398: refactored).

    Issue #744: Requires admin authentication.
    """
    start_time = datetime.now()

    # Issue #398: Use extracted helper
    files_to_analyze = await _get_files_to_analyze(Path(path))

    # Return no_data response if no files to analyze
    if not files_to_analyze:
        return JSONResponse(
            content=_no_data_response(
                "No files found to analyze. Please provide a valid path."
            ),
            status_code=200,
        )

    all_issues: list[PerformanceIssue] = []
    for filepath in files_to_analyze:
        try:
            content = await asyncio.to_thread(filepath.read_text, encoding="utf-8")
            all_issues.extend(
                analyze_with_regex(str(filepath), content, PERFORMANCE_PATTERNS)
            )
            if include_ast:
                all_issues.extend(analyze_with_ast(str(filepath), content))
        except Exception as e:
            logger.warning("Failed to analyze %s: %s", filepath, e)

    # Issue #398: Use extracted helpers
    all_issues = _deduplicate_issues(all_issues)
    critical, high, medium, low, score = _calculate_analysis_score(all_issues)

    result = PerformanceAnalysisResult(
        total_issues=len(all_issues),
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
        issues=all_issues,
        files_analyzed=len(files_to_analyze) or 5,
        duration_ms=round((datetime.now() - start_time).total_seconds() * 1000, 2),
        timestamp=datetime.now().isoformat(),
        score=score,
    )

    async with _analysis_history_lock:
        _analysis_history.insert(0, result)
        if len(_analysis_history) > 50:
            _analysis_history.pop()

    return result


@router.post("/analyze-content")
async def analyze_content(
    content: str,
    filename: str = Query("code.py", description="Filename for context"),
    admin_check: bool = Depends(check_admin_permission),
) -> list[PerformanceIssue]:
    """Analyze arbitrary code content for performance issues.

    Issue #744: Requires admin authentication.
    """
    issues: list[PerformanceIssue] = []

    # Regex analysis
    regex_issues = analyze_with_regex(filename, content, PERFORMANCE_PATTERNS)
    issues.extend(regex_issues)

    # AST analysis
    if filename.endswith(".py"):
        ast_issues = analyze_with_ast(filename, content)
        issues.extend(ast_issues)

    return issues


@router.get("/patterns")
async def list_patterns(
    admin_check: bool = Depends(check_admin_permission),
) -> list[PatternDefinition]:
    """List all performance patterns being detected.

    Issue #744: Requires admin authentication.
    """
    return list(PERFORMANCE_PATTERNS.values())


@router.get("/patterns/{pattern_id}")
async def get_pattern(
    pattern_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> PatternDefinition:
    """Get details for a specific pattern.

    Issue #744: Requires admin authentication.
    """
    if pattern_id not in PERFORMANCE_PATTERNS:
        raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")
    return PERFORMANCE_PATTERNS[pattern_id]


@router.post("/patterns/{pattern_id}/toggle")
async def toggle_pattern(
    pattern_id: str,
    enabled: bool,
    admin_check: bool = Depends(check_admin_permission),
) -> dict:
    """Enable or disable a specific pattern.

    Issue #744: Requires admin authentication.
    """
    if pattern_id not in PERFORMANCE_PATTERNS:
        raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")

    PERFORMANCE_PATTERNS[pattern_id].enabled = enabled
    return {
        "pattern_id": pattern_id,
        "enabled": enabled,
        "message": f"Pattern {pattern_id} {'enabled' if enabled else 'disabled'}",
    }


@router.get("/history")
async def get_history(
    limit: int = Query(20, ge=1, le=100),
    admin_check: bool = Depends(check_admin_permission),
) -> list[PerformanceAnalysisResult]:
    """Get analysis history.

    Issue #744: Requires admin authentication.
    """
    async with _analysis_history_lock:
        return list(_analysis_history[:limit])


@router.get("/summary")
async def get_summary(
    admin_check: bool = Depends(check_admin_permission),
) -> dict:
    """Get summary statistics across all analyses.

    Issue #744: Requires admin authentication.
    """
    async with _analysis_history_lock:
        if not _analysis_history:
            return {
                "total_analyses": 0,
                "average_score": 0,
                "common_issues": [],
                "patterns_enabled": sum(
                    1 for p in PERFORMANCE_PATTERNS.values() if p.enabled
                ),
            }

        # Count issue frequency
        issue_counts: dict[str, int] = {}
        for analysis in _analysis_history:
            for issue in analysis.issues:
                issue_counts[issue.pattern_id] = (
                    issue_counts.get(issue.pattern_id, 0) + 1
                )

        common_issues = [
            {
                "pattern_id": k,
                "count": v,
                "name": (
                    PERFORMANCE_PATTERNS[k].name if k in PERFORMANCE_PATTERNS else k
                ),
                "impact": (
                    PERFORMANCE_PATTERNS[k].impact.value
                    if k in PERFORMANCE_PATTERNS
                    else "medium"
                ),
            }
            for k, v in sorted(issue_counts.items(), key=lambda x: -x[1])[:10]
        ]

        avg_score = sum(a.score for a in _analysis_history) / len(_analysis_history)

        return {
            "total_analyses": len(_analysis_history),
            "average_score": round(avg_score, 1),
            "average_issues": round(
                sum(a.total_issues for a in _analysis_history) / len(_analysis_history),
                1,
            ),
            "common_issues": common_issues,
            "patterns_enabled": sum(
                1 for p in PERFORMANCE_PATTERNS.values() if p.enabled
            ),
            "total_patterns": len(PERFORMANCE_PATTERNS),
        }


@router.get("/categories")
async def get_categories(
    admin_check: bool = Depends(check_admin_permission),
) -> list[dict]:
    """Get pattern categories with counts.

    Issue #744: Requires admin authentication.
    """
    category_counts: dict[str, dict] = {}

    for pattern in PERFORMANCE_PATTERNS.values():
        cat = pattern.category.value
        if cat not in category_counts:
            category_counts[cat] = {
                "enabled": 0,
                "disabled": 0,
                "critical": 0,
                "high": 0,
            }

        if pattern.enabled:
            category_counts[cat]["enabled"] += 1
        else:
            category_counts[cat]["disabled"] += 1

        if pattern.impact in HIGH_SEVERITY_IMPACT_LEVELS:
            category_counts[cat][pattern.impact.value] += 1

    return [
        {
            "category": cat,
            "name": cat.capitalize(),
            "enabled": counts["enabled"],
            "disabled": counts["disabled"],
            "total": counts["enabled"] + counts["disabled"],
            "high_impact": counts.get("critical", 0) + counts.get("high", 0),
        }
        for cat, counts in category_counts.items()
    ]


@router.get("/hotspots")
async def get_hotspots(
    limit: int = Query(10, ge=1, le=50),
    admin_check: bool = Depends(check_admin_permission),
) -> list[dict]:
    """Get files with most performance issues (hotspots).

    Issue #744: Requires admin authentication.
    """
    file_issues: dict[str, list[PerformanceIssue]] = {}

    for analysis in _analysis_history[:10]:
        for issue in analysis.issues:
            if issue.file not in file_issues:
                file_issues[issue.file] = []
            file_issues[issue.file].append(issue)

    hotspots = [
        {
            "file": filepath,
            "issue_count": len(issues),
            "critical_count": sum(
                1 for i in issues if i.impact == ImpactLevel.CRITICAL
            ),
            "high_count": sum(1 for i in issues if i.impact == ImpactLevel.HIGH),
            "top_issues": [
                {"pattern_id": i.pattern_id, "name": i.name} for i in issues[:3]
            ],
        }
        for filepath, issues in sorted(file_issues.items(), key=lambda x: -len(x[1]))[
            :limit
        ]
    ]

    return hotspots


# ============================================================================
# Utility Functions
# ============================================================================


def _no_data_response(
    message: str = "No performance analysis data. Run codebase indexing first.",
) -> dict:
    """Standardized no-data response for analytics endpoints."""
    return {
        "status": "no_data",
        "message": message,
        "issues": [],
        "summary": {},
    }
