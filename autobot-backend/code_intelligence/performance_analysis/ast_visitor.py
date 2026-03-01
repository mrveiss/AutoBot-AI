# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance AST Visitor

Issue #381: Extracted from performance_analyzer.py god class refactoring.
Contains the AST visitor that analyzes code for performance patterns.
"""

import ast
import logging
from typing import Dict, List, Optional

from .patterns import (
    BLOCKING_IO_OPERATIONS,
    BLOCKING_IO_PATTERNS_HIGH_CONFIDENCE,
    BLOCKING_IO_PATTERNS_MEDIUM_CONFIDENCE,
    DB_OBJECTS,
    DB_OPERATIONS_CONTEXTUAL,
    DB_OPERATIONS_FALSE_POSITIVES,
    DB_OPERATIONS_HIGH_CONFIDENCE,
    LEGACY_DB_OPERATIONS,
    SAFE_PATTERNS,
)
from .types import (
    COMPLEXITY_LEVELS,
    PerformanceIssue,
    PerformanceIssueType,
    PerformanceSeverity,
)

logger = logging.getLogger(__name__)


class PerformanceASTVisitor(ast.NodeVisitor):
    """AST visitor for performance pattern analysis."""

    def __init__(self, file_path: str, source_lines: List[str]):
        """Initialize AST visitor with file context and loop tracking state."""
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

    def _check_nested_loop_complexity(self, node) -> None:
        """
        Check for nested loop complexity and add performance issue if detected.

        Issue #620.
        """
        if self.loop_depth < 2:
            return

        complexity = COMPLEXITY_LEVELS.get(self.loop_depth + 1, "O(n^4+)")
        severity = (
            PerformanceSeverity.HIGH
            if self.loop_depth >= 3
            else PerformanceSeverity.MEDIUM
        )

        code = self._get_source_segment(
            node.lineno, min(node.lineno + 5, len(self.source_lines))
        )
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

    def _check_db_operations_in_loop(self, node) -> None:
        """
        Check for database operations inside loops (N+1 query pattern).

        Issue #371: Uses refined patterns for database operation detection.
        Issue #620.
        """
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue

            call_name = self._get_call_name(child)
            if not call_name:
                continue

            is_db_op, confidence = self._is_database_operation(call_name)
            if not is_db_op:
                continue

            code = self._get_source_segment(child.lineno, child.lineno)
            severity = (
                PerformanceSeverity.HIGH
                if confidence >= 0.8
                else PerformanceSeverity.MEDIUM
            )
            self.findings.append(
                PerformanceIssue(
                    issue_type=PerformanceIssueType.N_PLUS_ONE_QUERY,
                    severity=severity,
                    file_path=self.file_path,
                    line_start=child.lineno,
                    line_end=child.lineno,
                    description=f"Database operation '{call_name}' inside loop (N+1 pattern)",
                    recommendation="Batch queries or use bulk operations",
                    estimated_complexity="O(n) database calls",
                    estimated_impact="Major database bottleneck",
                    current_code=code,
                    optimized_code="Use batch fetch: db.query(...).filter(id.in_(ids))",
                    confidence=confidence,
                    potential_false_positive=confidence < 0.7,
                )
            )
            break  # Only report once per loop

    def _check_loop_patterns(self, node) -> None:
        """
        Check for performance issues in loops.

        Issue #620: Refactored to use extracted helper methods.
        """
        self._check_nested_loop_complexity(node)
        self._check_db_operations_in_loop(node)

    def _is_database_operation(self, call_name: str) -> tuple:
        """Issue #371: Determine if a call is a database operation with confidence score.

        Returns:
            tuple: (is_db_operation: bool, confidence: float)
        """
        call_name_lower = call_name.lower()

        # Step 1: Check explicit false positives first - NEVER flag these
        for fp_pattern in DB_OPERATIONS_FALSE_POSITIVES:
            if call_name_lower == fp_pattern.lower() or call_name_lower.endswith(
                "." + fp_pattern.lower()
            ):
                return False, 0.0

        # Step 2: Check high confidence patterns (exact match)
        for hc_pattern in DB_OPERATIONS_HIGH_CONFIDENCE:
            if call_name_lower == hc_pattern.lower():
                return True, 0.95
            # Also check if it ends with the pattern (e.g., self.cursor.execute)
            if call_name_lower.endswith("." + hc_pattern.lower().split(".")[-1]):
                # Verify prefix matches expected DB object
                parts = call_name.split(".")
                if len(parts) >= 2:
                    obj_name = parts[-2].lower()
                    # Check if object name suggests DB context
                    if obj_name in DB_OBJECTS:  # Issue #380: use module constant
                        return True, 0.90

        # Step 3: Check contextual patterns
        parts = call_name.split(".")
        if len(parts) >= 2:
            obj_name = parts[-2].lower()
            method_name = parts[-1].lower()

            # Check contextual DB operations
            if method_name in DB_OPERATIONS_CONTEXTUAL:
                valid_prefixes = DB_OPERATIONS_CONTEXTUAL[method_name]
                if obj_name in valid_prefixes:
                    return True, 0.85

        # Step 4: Legacy fallback with low confidence (for backward compatibility)
        # Only flag if it's a clear DB method name AND has suggestive prefix
        for db_op in LEGACY_DB_OPERATIONS:
            if call_name_lower.endswith("." + db_op):
                return True, 0.70

        return False, 0.0

    def _check_call_in_loop(self, node: ast.Call) -> None:
        """Check if expensive calls are made inside loops."""
        if self.loop_depth == 0:
            return

        call_name = self._get_call_name(node)
        if not call_name:
            return

        call_name_lower = call_name.lower()

        # Issue #569: Check SAFE_PATTERNS first to avoid false positives
        # dict.get(), getattr(), router.get() etc. are NOT HTTP requests
        for safe_pattern in SAFE_PATTERNS:
            if safe_pattern.lower() in call_name_lower:
                return  # Skip - this is a safe pattern, not an HTTP call

        # Issue #569: Only flag as HTTP if from known HTTP libraries
        # Generic "get", "post" etc. match too many non-HTTP operations
        http_library_prefixes = (
            "requests.",
            "urllib.",
            "httpx.",
            "aiohttp.",
            "http.client.",
            "urllib3.",
        )

        is_http_call = False
        if call_name_lower.startswith(http_library_prefixes):
            # High confidence: explicit HTTP library prefix
            is_http_call = True
        elif "fetch(" in call_name_lower and "." not in call_name:
            # JavaScript-style fetch() as standalone function
            is_http_call = True

        if is_http_call:
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
                    confidence=0.90,
                )
            )

    def _build_blocking_issue_messages(
        self, is_potential: bool, severity: PerformanceSeverity
    ) -> tuple:
        """
        Build description and impact messages for blocking I/O issues.

        Args:
            is_potential: Whether this is a potential (not definite) issue
            severity: Issue severity level

        Returns:
            Tuple of (desc_prefix, desc_suffix, complexity, impact). Issue #620.
        """
        desc_prefix = "Potential " if is_potential else ""
        desc_suffix = " (needs review)" if severity == PerformanceSeverity.LOW else ""
        complexity = "May block event loop" if is_potential else "Blocks event loop"
        impact = (
            "Review needed - may degrade async performance"
            if is_potential
            else "Degrades async performance"
        )
        if severity == PerformanceSeverity.LOW:
            impact = "Review needed"
        return desc_prefix, desc_suffix, complexity, impact

    def _create_blocking_issue(
        self,
        call_name: str,
        node: ast.Call,
        code: str,
        severity: PerformanceSeverity,
        confidence: float,
        recommendation: str,
        is_potential: bool = False,
        false_positive_reason: str | None = None,
    ) -> None:
        """
        Create and append a blocking I/O performance issue.

        Issue #281: Extracted helper to reduce repetition in _check_blocking_in_async.
        Issue #620: Further refactored to use _build_blocking_issue_messages helper.
        """
        (
            desc_prefix,
            desc_suffix,
            complexity,
            impact,
        ) = self._build_blocking_issue_messages(is_potential, severity)

        self.findings.append(
            PerformanceIssue(
                issue_type=PerformanceIssueType.BLOCKING_IO_IN_ASYNC,
                severity=severity,
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=node.lineno,
                description=f"{desc_prefix}Blocking operation '{call_name}' in async function{desc_suffix}",
                recommendation=recommendation,
                estimated_complexity=complexity,
                estimated_impact=impact,
                current_code=code,
                confidence=confidence,
                potential_false_positive=is_potential,
                false_positive_reason=false_positive_reason,
            )
        )

    def _check_time_sleep_in_async(self, call_name: str, node: ast.Call) -> bool:
        """
        Check for time.sleep() in async context (high confidence special case).

        Issue #281: Extracted helper for time.sleep detection.

        Args:
            call_name: Name of the call
            node: AST node

        Returns:
            True if time.sleep was found and issue added
        """
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
            return True
        return False

    def _check_high_confidence_blocking(
        self, call_name: str, node: ast.Call, code: str
    ) -> bool:
        """Check HIGH confidence blocking patterns (exact match).

        Issue #665: Extracted from _check_blocking_in_async to reduce function length.

        Returns:
            True if a high confidence match was found and issue created.
        """
        for pattern, (
            recommendation,
            confidence,
            is_exact,
        ) in BLOCKING_IO_PATTERNS_HIGH_CONFIDENCE.items():
            if is_exact and call_name == pattern:
                severity = (
                    PerformanceSeverity.HIGH
                    if confidence >= 0.9
                    else PerformanceSeverity.MEDIUM
                )
                self._create_blocking_issue(
                    call_name, node, code, severity, confidence, recommendation
                )
                return True
        return False

    def _check_medium_confidence_blocking(
        self, call_name_lower: str, call_name: str, node: ast.Call, code: str
    ) -> bool:
        """Check MEDIUM confidence blocking patterns (substring match).

        Issue #665: Extracted from _check_blocking_in_async to reduce function length.

        Returns:
            True if a medium confidence match was found and issue created.
        """
        for pattern, (
            recommendation,
            confidence,
            _,
        ) in BLOCKING_IO_PATTERNS_MEDIUM_CONFIDENCE.items():
            if pattern in call_name_lower:
                self._create_blocking_issue(
                    call_name,
                    node,
                    code,
                    PerformanceSeverity.MEDIUM,
                    confidence,
                    recommendation,
                    is_potential=True,
                    false_positive_reason="Generic pattern match - verify if this is actual I/O",
                )
                return True
        return False

    def _check_legacy_blocking_patterns(
        self, call_name_lower: str, call_name: str, node: ast.Call, code: str
    ) -> bool:
        """Check legacy low-confidence blocking patterns.

        Issue #665: Extracted from _check_blocking_in_async to reduce function length.
        Issue #569: Skip dict.get() false positives.
        Issue #1226: Use exact method name matching instead of substring
        matching to eliminate false positives (e.g. "get" matching
        get_redis_client, _get_config, etc.).

        Returns:
            True if a legacy pattern match was found and issue created.
        """
        # Extract actual method name (part after last dot)
        method_name = call_name_lower.rsplit(".", 1)[-1]
        for blocking_op, recommendation in BLOCKING_IO_OPERATIONS.items():
            if method_name == blocking_op:
                if blocking_op == "get" and ".get" in call_name_lower:
                    continue  # Skip dict.get() false positives
                self._create_blocking_issue(
                    call_name,
                    node,
                    code,
                    PerformanceSeverity.LOW,
                    0.4,
                    recommendation,
                    is_potential=True,
                    false_positive_reason=f"Generic pattern '{blocking_op}' matched - may be safe",
                )
                return True
        return False

    def _check_blocking_in_async(self, node: ast.Call) -> None:
        """Check for blocking operations in async context.

        Issue #281/#385/#665: Refactored with confidence-based pattern matching.
        """
        if not self.async_context:
            return

        call_name = self._get_call_name(node)
        if not call_name:
            return

        call_name_lower = call_name.lower()
        if "async" in call_name_lower or "aio" in call_name_lower:
            return  # Already using async version

        code = self._get_source_segment(node.lineno, node.lineno)

        # Step 1: HIGH confidence patterns
        if self._check_high_confidence_blocking(call_name, node, code):
            return

        # Step 2: Skip SAFE patterns
        for safe_pattern in SAFE_PATTERNS:
            if safe_pattern in call_name_lower:
                return

        # Step 3: MEDIUM confidence patterns
        if self._check_medium_confidence_blocking(
            call_name_lower, call_name, node, code
        ):
            return

        # Step 4: Legacy fallback patterns
        if self._check_legacy_blocking_patterns(call_name_lower, call_name, node, code):
            return

        # Step 5: time.sleep special case
        self._check_time_sleep_in_async(call_name, node)

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
            logger.debug("Suppressed exception in try block", exc_info=True)
        return ""
