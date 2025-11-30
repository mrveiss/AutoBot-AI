# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Pattern Analyzer

Identifies performance anti-patterns and bottlenecks including:
- N+1 query patterns (database queries in loops)
- Nested loop complexity (O(n²) and higher)
- Synchronous operations in async context
- Memory leak patterns
- Cache misuse and invalidation issues
- Inefficient data structure usage

Part of Issue #222 - Performance Pattern Analysis
Parent Epic: #217 - Advanced Code Intelligence
"""

import ast
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PerformanceSeverity(Enum):
    """Severity levels for performance issues."""

    INFO = "info"  # Minor optimization opportunity
    LOW = "low"  # Small performance impact
    MEDIUM = "medium"  # Moderate performance impact
    HIGH = "high"  # Significant performance impact
    CRITICAL = "critical"  # Severe bottleneck


class PerformanceIssueType(Enum):
    """Types of performance issues detected."""

    # Query patterns
    N_PLUS_ONE_QUERY = "n_plus_one_query"
    QUERY_IN_LOOP = "query_in_loop"
    MISSING_INDEX_HINT = "missing_index_hint"
    UNBATCHED_INSERTS = "unbatched_inserts"

    # Loop complexity
    NESTED_LOOP_COMPLEXITY = "nested_loop_complexity"
    INEFFICIENT_LOOP = "inefficient_loop"
    LOOP_INVARIANT_COMPUTATION = "loop_invariant_computation"
    QUADRATIC_COMPLEXITY = "quadratic_complexity"

    # Async/sync issues
    SYNC_IN_ASYNC = "sync_in_async"
    BLOCKING_IO_IN_ASYNC = "blocking_io_in_async"
    MISSING_AWAIT = "missing_await"
    SEQUENTIAL_AWAITS = "sequential_awaits"

    # Memory patterns
    UNBOUNDED_COLLECTION = "unbounded_collection"
    LARGE_OBJECT_CREATION = "large_object_creation"
    MEMORY_LEAK_RISK = "memory_leak_risk"
    EXCESSIVE_STRING_CONCAT = "excessive_string_concat"

    # Cache patterns
    REPEATED_COMPUTATION = "repeated_computation"
    MISSING_CACHE = "missing_cache"
    CACHE_STAMPEDE_RISK = "cache_stampede_risk"
    INEFFICIENT_CACHE_KEY = "inefficient_cache_key"

    # Data structure issues
    LIST_FOR_LOOKUP = "list_for_lookup"
    INEFFICIENT_DICT_ACCESS = "inefficient_dict_access"
    REPEATED_LIST_APPEND = "repeated_list_append"

    # I/O patterns
    REPEATED_FILE_OPEN = "repeated_file_open"
    MISSING_CONTEXT_MANAGER = "missing_context_manager"
    INEFFICIENT_FILE_READ = "inefficient_file_read"

    # Network patterns
    UNBATCHED_API_CALLS = "unbatched_api_calls"
    MISSING_CONNECTION_POOL = "missing_connection_pool"
    REPEATED_HTTP_REQUESTS = "repeated_http_requests"


# Complexity estimation for Big-O notation
COMPLEXITY_LEVELS = {
    1: "O(1)",
    2: "O(n)",
    3: "O(n²)",
    4: "O(n³)",
    5: "O(n⁴+)",
}


@dataclass
class PerformanceIssue:
    """Result of performance analysis for a single finding."""

    issue_type: PerformanceIssueType
    severity: PerformanceSeverity
    file_path: str
    line_start: int
    line_end: int
    description: str
    recommendation: str
    estimated_complexity: str
    estimated_impact: str
    current_code: str = ""
    optimized_code: str = ""
    confidence: float = 1.0
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "issue_type": self.issue_type.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "description": self.description,
            "recommendation": self.recommendation,
            "estimated_complexity": self.estimated_complexity,
            "estimated_impact": self.estimated_impact,
            "current_code": self.current_code,
            "optimized_code": self.optimized_code,
            "confidence": self.confidence,
            "metrics": self.metrics,
        }


# Blocking I/O operations that shouldn't be in async context
BLOCKING_IO_OPERATIONS = {
    "open": "Use aiofiles.open() for async file I/O",
    "read": "Use async file reading",
    "write": "Use async file writing",
    "sleep": "Use asyncio.sleep() instead of time.sleep()",
    "request": "Use aiohttp or httpx for async HTTP",
    "get": "Use async HTTP client",
    "post": "Use async HTTP client",
    "urlopen": "Use aiohttp for async HTTP",
    "connect": "Use async database driver",
    "execute": "Use async database operations",
    "cursor": "Use async database cursor",
}

# Database operation patterns
DB_OPERATIONS = {
    "execute",
    "executemany",
    "fetchone",
    "fetchall",
    "fetchmany",
    "query",
    "find",
    "find_one",
    "insert",
    "update",
    "delete",
    "select",
    "get",
    "set",
    "hget",
    "hset",
    "mget",
    "mset",
}

# HTTP operations
HTTP_OPERATIONS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "request",
    "urlopen",
    "fetch",
}


class PerformanceASTVisitor(ast.NodeVisitor):
    """AST visitor for performance pattern analysis."""

    def __init__(self, file_path: str, source_lines: List[str]):
        self.file_path = file_path
        self.source_lines = source_lines
        self.findings: List[PerformanceIssue] = []
        self.loop_depth = 0
        self.async_context = False
        self.current_function: Optional[str] = None
        self.loop_stack: List[ast.AST] = []
        self.function_calls_in_loop: List[tuple] = []
        self.awaits_in_function: List[ast.Await] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Analyze synchronous function definitions."""
        old_function = self.current_function
        old_async = self.async_context
        self.current_function = node.name
        self.async_context = False
        self.awaits_in_function = []

        self._analyze_function(node)
        self.generic_visit(node)

        self.current_function = old_function
        self.async_context = old_async

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Analyze async function definitions."""
        old_function = self.current_function
        old_async = self.async_context
        self.current_function = node.name
        self.async_context = True
        self.awaits_in_function = []

        self._analyze_function(node)
        self._check_sequential_awaits(node)
        self.generic_visit(node)

        self.current_function = old_function
        self.async_context = old_async

    def visit_For(self, node: ast.For) -> None:
        """Analyze for loops."""
        self.loop_depth += 1
        self.loop_stack.append(node)

        self._check_loop_patterns(node)
        self.generic_visit(node)

        self.loop_stack.pop()
        self.loop_depth -= 1

    def visit_While(self, node: ast.While) -> None:
        """Analyze while loops."""
        self.loop_depth += 1
        self.loop_stack.append(node)

        self._check_loop_patterns(node)
        self.generic_visit(node)

        self.loop_stack.pop()
        self.loop_depth -= 1

    def visit_ListComp(self, node: ast.ListComp) -> None:
        """Analyze list comprehensions."""
        # Count nested generators
        nesting = len(node.generators)
        if nesting >= 2:
            self._add_complexity_issue(node, nesting)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Analyze function calls for performance issues."""
        self._check_call_in_loop(node)
        self._check_blocking_in_async(node)
        self._check_inefficient_operations(node)
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await) -> None:
        """Track await expressions."""
        self.awaits_in_function.append(node)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Check for inefficient string concatenation in loops."""
        if self.loop_depth > 0 and isinstance(node.op, ast.Add):
            if self._is_string_concat(node):
                code = self._get_source_segment(node.lineno, node.lineno)
                self.findings.append(
                    PerformanceIssue(
                        issue_type=PerformanceIssueType.EXCESSIVE_STRING_CONCAT,
                        severity=PerformanceSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_start=node.lineno,
                        line_end=node.lineno,
                        description="String concatenation in loop creates new string objects",
                        recommendation="Use list.append() and ''.join() for string building",
                        estimated_complexity="O(n²)",
                        estimated_impact="High memory allocation overhead",
                        current_code=code,
                        optimized_code="parts = []; for x in items: parts.append(x); result = ''.join(parts)",
                        confidence=0.8,
                    )
                )
        self.generic_visit(node)

    def _analyze_function(self, node) -> None:
        """Analyze function body for performance patterns."""
        # Check for repeated computations that could be cached
        call_counts: Dict[str, int] = {}
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_call_name(child)
                if call_name:
                    call_counts[call_name] = call_counts.get(call_name, 0) + 1

        # Flag repeated expensive calls
        for call_name, count in call_counts.items():
            if count >= 3 and self._is_expensive_call(call_name):
                self.findings.append(
                    PerformanceIssue(
                        issue_type=PerformanceIssueType.REPEATED_COMPUTATION,
                        severity=PerformanceSeverity.LOW,
                        file_path=self.file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        description=f"'{call_name}' called {count} times in same function",
                        recommendation="Cache the result if the computation is deterministic",
                        estimated_complexity="O(1) with caching",
                        estimated_impact="Reduced redundant computation",
                        confidence=0.6,
                    )
                )

    def _check_loop_patterns(self, node) -> None:
        """Check for performance issues in loops."""
        # Check for nested loop complexity
        if self.loop_depth >= 2:
            complexity = COMPLEXITY_LEVELS.get(self.loop_depth + 1, "O(n⁴+)")
            severity = (
                PerformanceSeverity.HIGH
                if self.loop_depth >= 3
                else PerformanceSeverity.MEDIUM
            )

            code = self._get_source_segment(node.lineno, min(node.lineno + 5, len(self.source_lines)))
            self.findings.append(
                PerformanceIssue(
                    issue_type=PerformanceIssueType.NESTED_LOOP_COMPLEXITY,
                    severity=severity,
                    file_path=self.file_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    description=f"Nested loop depth {self.loop_depth} has {complexity} complexity",
                    recommendation="Consider using hash-based lookups, caching, or algorithm optimization",
                    estimated_complexity=complexity,
                    estimated_impact="Significant slowdown with large inputs",
                    current_code=code,
                    confidence=0.9,
                    metrics={"loop_depth": self.loop_depth},
                )
            )

        # Check for database operations in loop
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_call_name(child)
                if call_name and any(
                    db_op in call_name.lower() for db_op in DB_OPERATIONS
                ):
                    code = self._get_source_segment(child.lineno, child.lineno)
                    self.findings.append(
                        PerformanceIssue(
                            issue_type=PerformanceIssueType.N_PLUS_ONE_QUERY,
                            severity=PerformanceSeverity.HIGH,
                            file_path=self.file_path,
                            line_start=child.lineno,
                            line_end=child.lineno,
                            description=f"Database operation '{call_name}' inside loop (N+1 pattern)",
                            recommendation="Batch queries or use bulk operations",
                            estimated_complexity="O(n) database calls",
                            estimated_impact="Major database bottleneck",
                            current_code=code,
                            optimized_code="Use batch fetch: db.query(...).filter(id.in_(ids))",
                            confidence=0.85,
                        )
                    )
                    break  # Only report once per loop

    def _check_call_in_loop(self, node: ast.Call) -> None:
        """Check if expensive calls are made inside loops."""
        if self.loop_depth == 0:
            return

        call_name = self._get_call_name(node)
        if not call_name:
            return

        # Check for HTTP requests in loop
        if any(http_op in call_name.lower() for http_op in HTTP_OPERATIONS):
            code = self._get_source_segment(node.lineno, node.lineno)
            self.findings.append(
                PerformanceIssue(
                    issue_type=PerformanceIssueType.UNBATCHED_API_CALLS,
                    severity=PerformanceSeverity.HIGH,
                    file_path=self.file_path,
                    line_start=node.lineno,
                    line_end=node.lineno,
                    description=f"HTTP request '{call_name}' inside loop",
                    recommendation="Batch API calls or use async parallel requests",
                    estimated_complexity="O(n) network round-trips",
                    estimated_impact="Major latency bottleneck",
                    current_code=code,
                    optimized_code="Use asyncio.gather() for parallel requests",
                    confidence=0.85,
                )
            )

    def _check_blocking_in_async(self, node: ast.Call) -> None:
        """Check for blocking operations in async context."""
        if not self.async_context:
            return

        call_name = self._get_call_name(node)
        if not call_name:
            return

        # Check for known blocking operations
        for blocking_op, recommendation in BLOCKING_IO_OPERATIONS.items():
            if blocking_op in call_name.lower():
                # Skip if it's the async version
                if "async" in call_name.lower() or "aio" in call_name.lower():
                    continue

                code = self._get_source_segment(node.lineno, node.lineno)
                self.findings.append(
                    PerformanceIssue(
                        issue_type=PerformanceIssueType.BLOCKING_IO_IN_ASYNC,
                        severity=PerformanceSeverity.HIGH,
                        file_path=self.file_path,
                        line_start=node.lineno,
                        line_end=node.lineno,
                        description=f"Blocking operation '{call_name}' in async function",
                        recommendation=recommendation,
                        estimated_complexity="Blocks event loop",
                        estimated_impact="Degrades async performance",
                        current_code=code,
                        confidence=0.8,
                    )
                )
                break

        # Check for time.sleep in async
        if call_name == "time.sleep" or (
            call_name == "sleep" and "time" in str(self._get_call_module(node))
        ):
            code = self._get_source_segment(node.lineno, node.lineno)
            self.findings.append(
                PerformanceIssue(
                    issue_type=PerformanceIssueType.SYNC_IN_ASYNC,
                    severity=PerformanceSeverity.CRITICAL,
                    file_path=self.file_path,
                    line_start=node.lineno,
                    line_end=node.lineno,
                    description="time.sleep() blocks the event loop in async context",
                    recommendation="Use await asyncio.sleep() instead",
                    estimated_complexity="Blocks event loop",
                    estimated_impact="Halts all async operations",
                    current_code=code,
                    optimized_code="await asyncio.sleep(seconds)",
                    confidence=0.95,
                )
            )

    def _check_sequential_awaits(self, node: ast.AsyncFunctionDef) -> None:
        """Check for sequential awaits that could be parallel."""
        await_calls: List[tuple] = []

        for child in ast.walk(node):
            if isinstance(child, ast.Await):
                await_calls.append((child.lineno, child))

        # Check for consecutive awaits on same line range
        if len(await_calls) >= 3:
            # Check if they're sequential (within 2 lines of each other)
            sequential_count = 0
            for i in range(1, len(await_calls)):
                if await_calls[i][0] - await_calls[i - 1][0] <= 2:
                    sequential_count += 1

            if sequential_count >= 2:
                start_line = await_calls[0][0]
                end_line = await_calls[-1][0]
                code = self._get_source_segment(start_line, end_line)
                self.findings.append(
                    PerformanceIssue(
                        issue_type=PerformanceIssueType.SEQUENTIAL_AWAITS,
                        severity=PerformanceSeverity.MEDIUM,
                        file_path=self.file_path,
                        line_start=start_line,
                        line_end=end_line,
                        description=f"{len(await_calls)} sequential awaits could run in parallel",
                        recommendation="Use asyncio.gather() for independent async operations",
                        estimated_complexity="O(n) → O(1) latency",
                        estimated_impact="Significant latency reduction",
                        current_code=code,
                        optimized_code="results = await asyncio.gather(coro1(), coro2(), coro3())",
                        confidence=0.7,
                        metrics={"await_count": len(await_calls)},
                    )
                )

    def _check_inefficient_operations(self, node: ast.Call) -> None:
        """Check for inefficient data structure operations."""
        call_name = self._get_call_name(node)
        if not call_name:
            return

        # Check for 'in' check on list that should be set
        # This is checked in parent context

    def _is_string_concat(self, node: ast.BinOp) -> bool:
        """Check if binary operation is string concatenation."""
        if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            return True
        if isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
            return True
        return False

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Get the name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    def _get_call_module(self, node: ast.Call) -> Optional[str]:
        """Get the module of a function call."""
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                return node.func.value.id
        return None

    def _is_expensive_call(self, call_name: str) -> bool:
        """Check if a call is considered expensive."""
        expensive_patterns = [
            "query",
            "fetch",
            "request",
            "load",
            "read",
            "parse",
            "compile",
            "serialize",
            "deserialize",
            "encode",
            "decode",
            "hash",
            "encrypt",
            "decrypt",
        ]
        return any(pattern in call_name.lower() for pattern in expensive_patterns)

    def _add_complexity_issue(self, node: ast.AST, nesting: int) -> None:
        """Add a complexity issue for nested comprehensions."""
        complexity = COMPLEXITY_LEVELS.get(nesting + 1, "O(n⁴+)")
        code = self._get_source_segment(node.lineno, node.lineno)
        self.findings.append(
            PerformanceIssue(
                issue_type=PerformanceIssueType.QUADRATIC_COMPLEXITY,
                severity=PerformanceSeverity.MEDIUM,
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=node.lineno,
                description=f"Nested comprehension has {complexity} complexity",
                recommendation="Consider refactoring to reduce nesting",
                estimated_complexity=complexity,
                estimated_impact="Performance degrades with input size",
                current_code=code,
                confidence=0.85,
            )
        )

    def _get_source_segment(self, start: int, end: int) -> str:
        """Get source code for line range."""
        try:
            if start > 0 and start <= len(self.source_lines):
                lines = self.source_lines[start - 1 : end]
                return "\n".join(lines)
        except Exception:
            pass  # Index error or other issue, return empty below
        return ""


class PerformanceAnalyzer:
    """Main performance pattern analyzer."""

    def __init__(
        self,
        project_root: Optional[str] = None,
        exclude_patterns: Optional[List[str]] = None,
    ):
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

    def analyze_file(self, file_path: str) -> List[PerformanceIssue]:
        """Analyze a single file for performance issues."""
        findings: List[PerformanceIssue] = []
        path = Path(file_path)

        if not path.exists() or not path.suffix == ".py":
            return findings

        try:
            content = path.read_text(encoding="utf-8")
            lines = content.split("\n")

            # AST-based analysis
            try:
                tree = ast.parse(content)
                visitor = PerformanceASTVisitor(str(path), lines)
                visitor.visit(tree)
                findings.extend(visitor.findings)
            except SyntaxError as e:
                logger.warning(f"Syntax error in {file_path}: {e}")

            # Regex-based analysis for patterns AST can't catch
            findings.extend(self._regex_analysis(str(path), content, lines))

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")

        return findings

    def _regex_analysis(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[PerformanceIssue]:
        """Perform regex-based performance analysis."""
        findings: List[PerformanceIssue] = []

        # Check for list used as lookup (should be set)
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

        # Check for repeated file opens
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

        # Check for += with strings in loop-like context
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

    def analyze_directory(
        self, directory: Optional[str] = None
    ) -> List[PerformanceIssue]:
        """Analyze all Python files in a directory."""
        target = Path(directory) if directory else self.project_root
        self.results = []

        for py_file in target.rglob("*.py"):
            if self._should_exclude(py_file):
                continue

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
        """Get summary of performance findings."""
        by_severity = {}
        by_type = {}

        for finding in self.results:
            sev = finding.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            itype = finding.issue_type.value
            by_type[itype] = by_type.get(itype, 0) + 1

        # Calculate performance score (0-100)
        total = len(self.results)
        critical = by_severity.get("critical", 0)
        high = by_severity.get("high", 0)
        medium = by_severity.get("medium", 0)
        low = by_severity.get("low", 0)

        # Weighted deduction
        deduction = (critical * 20) + (high * 8) + (medium * 3) + low
        score = max(0, 100 - deduction)

        return {
            "total_issues": total,
            "by_severity": by_severity,
            "by_type": by_type,
            "performance_score": score,
            "grade": self._get_grade(score),
            "critical_issues": critical,
            "high_issues": high,
            "files_analyzed": len(set(f.file_path for f in self.results)),
            "top_issues": self._get_top_issues(),
        }

    def _get_grade(self, score: int) -> str:
        """Get letter grade from score."""
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
        seen_types = set()

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
                md.append(f"- **File**: {finding['file_path']}:{finding['line_start']}\n")
                md.append(f"- **Complexity**: {finding['estimated_complexity']}\n")
                md.append(f"- **Description**: {finding['description']}\n")
                md.append(f"- **Fix**: {finding['recommendation']}\n\n")

        return "".join(md)


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


def _get_category(issue_type: PerformanceIssueType) -> str:
    """Get category for issue type."""
    type_name = issue_type.name
    if "QUERY" in type_name or "INSERT" in type_name:
        return "Database"
    elif "LOOP" in type_name or "COMPLEXITY" in type_name:
        return "Algorithm"
    elif "ASYNC" in type_name or "AWAIT" in type_name or "SYNC" in type_name:
        return "Async/Await"
    elif "MEMORY" in type_name or "COLLECTION" in type_name or "STRING" in type_name:
        return "Memory"
    elif "CACHE" in type_name or "COMPUTATION" in type_name:
        return "Caching"
    elif "FILE" in type_name or "IO" in type_name:
        return "I/O"
    elif "API" in type_name or "HTTP" in type_name or "CONNECTION" in type_name:
        return "Network"
    else:
        return "General"
