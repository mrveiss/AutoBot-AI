# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test-Driven Pattern Discovery System

Analyzes test patterns to identify:
- Missing tests and coverage gaps
- Test anti-patterns (flaky tests, overly complex tests)
- Test smells (empty tests, duplicate tests, test code in production)
- Test quality metrics and scoring

Part of Issue #236 - Test-Driven Pattern Discovery
Parent Epic: #217 - Advanced Code Intelligence
"""

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex patterns for non-descriptive test name detection
_BAD_TEST_NAME_PATTERNS = [
    re.compile(r"^test\d+$"),  # test1, test2
    re.compile(r"^test_\d+$"),  # test_1, test_2
    re.compile(r"^test_it$"),
    re.compile(r"^test_this$"),
    re.compile(r"^test_stuff$"),
    re.compile(r"^test_foo$"),
    re.compile(r"^test_bar$"),
]

# Issue #380: Module-level tuples for AST node type checks
_BRANCH_TYPES = (ast.If, ast.For, ast.While, ast.Try, ast.With)
_EMPTY_STMT_TYPES = (ast.Pass, ast.Expr)


# =============================================================================
# Enums for Test Pattern Types and Severity
# =============================================================================


class TestPatternSeverity(Enum):
    """Severity levels for test pattern issues."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TestAntiPatternType(Enum):
    """Types of test anti-patterns detected."""

    # Coverage Issues
    MISSING_TEST = "missing_test"
    LOW_COVERAGE = "low_coverage"
    UNTESTED_BRANCH = "untested_branch"
    MISSING_EDGE_CASE = "missing_edge_case"

    # Test Smells
    EMPTY_TEST = "empty_test"
    DUPLICATE_TEST = "duplicate_test"
    FLAKY_TEST = "flaky_test"
    SLEEPY_TEST = "sleepy_test"
    OVERLY_COMPLEX_TEST = "overly_complex_test"

    # Assertion Issues
    NO_ASSERTION = "no_assertion"
    WEAK_ASSERTION = "weak_assertion"
    MULTIPLE_ASSERTIONS = "multiple_assertions"
    ASSERTION_ROULETTE = "assertion_roulette"

    # Setup/Teardown Issues
    SHARED_FIXTURE = "shared_fixture"
    MISSING_CLEANUP = "missing_cleanup"
    EXCESSIVE_SETUP = "excessive_setup"

    # Test Organization
    TEST_IN_PRODUCTION = "test_in_production"
    PRODUCTION_IN_TEST = "production_in_test"
    TEST_NAMING = "test_naming"
    MISSING_DOCSTRING = "missing_docstring"

    # Dependency Issues
    EXTERNAL_DEPENDENCY = "external_dependency"
    DATABASE_DEPENDENCY = "database_dependency"
    NETWORK_DEPENDENCY = "network_dependency"
    TIME_DEPENDENCY = "time_dependency"


class TestQualityMetric(Enum):
    """Test quality metrics."""

    COVERAGE_SCORE = "coverage_score"
    ASSERTION_DENSITY = "assertion_density"
    COMPLEXITY_SCORE = "complexity_score"
    ISOLATION_SCORE = "isolation_score"
    MAINTAINABILITY_SCORE = "maintainability_score"
    OVERALL_SCORE = "overall_score"


# =============================================================================
# Data Classes for Results
# =============================================================================


@dataclass
class TestAntiPatternResult:
    """Result of test anti-pattern detection for a single finding."""

    pattern_type: TestAntiPatternType
    severity: TestPatternSeverity
    file_path: str
    line_number: int
    test_name: str
    description: str
    suggestion: str
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pattern_type": self.pattern_type.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "test_name": self.test_name,
            "description": self.description,
            "suggestion": self.suggestion,
            "metrics": self.metrics,
        }


@dataclass
class CoverageGap:
    """Represents a coverage gap in the codebase."""

    source_file: str
    source_function: str
    source_line: int
    gap_type: str  # "no_test", "partial_coverage", "missing_edge_case"
    description: str
    suggestion: str
    priority: TestPatternSeverity

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_file": self.source_file,
            "source_function": self.source_function,
            "source_line": self.source_line,
            "gap_type": self.gap_type,
            "description": self.description,
            "suggestion": self.suggestion,
            "priority": self.priority.value,
        }


@dataclass
class TestQualityReport:
    """Quality metrics for a test file or test suite."""

    file_path: str
    test_count: int
    assertion_count: int
    metrics: Dict[TestQualityMetric, float]
    anti_patterns: List[TestAntiPatternResult]
    coverage_gaps: List[CoverageGap]
    suggestions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "test_count": self.test_count,
            "assertion_count": self.assertion_count,
            "metrics": {k.value: v for k, v in self.metrics.items()},
            "anti_patterns": [p.to_dict() for p in self.anti_patterns],
            "coverage_gaps": [g.to_dict() for g in self.coverage_gaps],
            "suggestions": self.suggestions,
        }


@dataclass
class TestAnalysisReport:
    """Complete test analysis report for a codebase scan."""

    scan_path: str
    total_test_files: int
    total_tests: int
    total_assertions: int
    anti_patterns: List[TestAntiPatternResult]
    coverage_gaps: List[CoverageGap]
    quality_metrics: Dict[TestQualityMetric, float]
    severity_distribution: Dict[str, int]
    suggestions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scan_path": self.scan_path,
            "total_test_files": self.total_test_files,
            "total_tests": self.total_tests,
            "total_assertions": self.total_assertions,
            "anti_patterns": [p.to_dict() for p in self.anti_patterns],
            "coverage_gaps": [g.to_dict() for g in self.coverage_gaps],
            "quality_metrics": {k.value: v for k, v in self.quality_metrics.items()},
            "severity_distribution": self.severity_distribution,
            "total_issues": len(self.anti_patterns),
            "suggestions": self.suggestions,
        }


# =============================================================================
# Test Pattern Analyzer Class
# =============================================================================


class TestPatternAnalyzer:
    """
    Analyzes test patterns to identify coverage gaps, anti-patterns, and quality issues.

    Uses AST parsing to analyze test code structure and identify common
    test smells and anti-patterns that indicate potential test quality issues.
    """

    # Thresholds for detection
    COMPLEX_TEST_LINE_THRESHOLD = 50
    COMPLEX_TEST_BRANCH_THRESHOLD = 5
    MAX_ASSERTIONS_PER_TEST = 10
    MIN_ASSERTIONS_PER_TEST = 1
    SLEEP_CALL_THRESHOLD = 0  # Any sleep is suspicious
    SETUP_LINE_THRESHOLD = 20
    ASSERTION_DENSITY_THRESHOLD = 0.1  # assertions per line

    # Patterns for detection
    FLAKY_PATTERNS = [
        r"time\.sleep",
        r"asyncio\.sleep",
        r"random\.",
        r"datetime\.now",
        r"time\.time",
        r"uuid\.",
    ]

    EXTERNAL_DEPENDENCY_PATTERNS = [
        r"requests\.",
        r"httpx\.",
        r"aiohttp\.",
        r"urllib\.",
        r"socket\.",
    ]

    DATABASE_PATTERNS = [
        r"\.execute\(",
        r"\.commit\(",
        r"\.rollback\(",
        r"cursor\.",
        r"connection\.",
        r"session\.",
    ]

    ASSERTION_METHODS = {
        "assert",
        "assertEqual",
        "assertNotEqual",
        "assertTrue",
        "assertFalse",
        "assertIs",
        "assertIsNot",
        "assertIsNone",
        "assertIsNotNone",
        "assertIn",
        "assertNotIn",
        "assertIsInstance",
        "assertNotIsInstance",
        "assertRaises",
        "assertWarns",
        "assertAlmostEqual",
        "assertNotAlmostEqual",
        "assertGreater",
        "assertGreaterEqual",
        "assertLess",
        "assertLessEqual",
        "assertRegex",
        "assertNotRegex",
        "assertCountEqual",
        "assertMultiLineEqual",
        "assertSequenceEqual",
        "assertListEqual",
        "assertTupleEqual",
        "assertSetEqual",
        "assertDictEqual",
        # pytest assertions
        "assert_called",
        "assert_called_once",
        "assert_called_with",
        "assert_called_once_with",
        "assert_any_call",
        "assert_has_calls",
        "assert_not_called",
    }

    def __init__(
        self,
        exclude_dirs: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        test_file_patterns: Optional[List[str]] = None,
    ):
        """
        Initialize the TestPatternAnalyzer.

        Args:
            exclude_dirs: Directories to exclude from analysis
            exclude_patterns: File patterns to exclude
            test_file_patterns: Patterns to identify test files
        """
        self.exclude_dirs = exclude_dirs or [
            "__pycache__",
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "dist",
            "build",
            ".pytest_cache",
            ".mypy_cache",
        ]
        self.exclude_patterns = exclude_patterns or [
            r".*\.pyc$",
            r".*\.pyo$",
            r".*\.egg-info.*",
        ]
        self.test_file_patterns = test_file_patterns or [
            r"test_.*\.py$",
            r".*_test\.py$",
            r"tests\.py$",
        ]

        # Compile patterns
        self._flaky_patterns = [re.compile(p) for p in self.FLAKY_PATTERNS]
        self._external_patterns = [re.compile(p) for p in self.EXTERNAL_DEPENDENCY_PATTERNS]
        self._database_patterns = [re.compile(p) for p in self.DATABASE_PATTERNS]
        self._exclude_patterns = [re.compile(p) for p in self.exclude_patterns]
        self._test_patterns = [re.compile(p) for p in self.test_file_patterns]

    def is_test_file(self, file_path: str) -> bool:
        """Check if a file is a test file based on naming patterns."""
        filename = os.path.basename(file_path)
        return any(p.match(filename) for p in self._test_patterns)

    def _should_exclude(self, path: str) -> bool:
        """Check if a path should be excluded from analysis."""
        path_parts = Path(path).parts
        for exclude_dir in self.exclude_dirs:
            if exclude_dir in path_parts:
                return True
        for pattern in self._exclude_patterns:
            if pattern.match(path):
                return True
        return False

    # =========================================================================
    # AST Analysis Helpers
    # =========================================================================

    def _is_assertion_call(self, call_node: ast.Call) -> bool:
        """Check if a Call node is an assertion method (Issue #315: extracted).

        Args:
            call_node: AST Call node to check

        Returns:
            True if the call is an assertion method
        """
        func = call_node.func
        if isinstance(func, ast.Attribute):
            return func.attr in self.ASSERTION_METHODS
        if isinstance(func, ast.Name):
            return func.id in self.ASSERTION_METHODS
        return False

    def _count_assertions(self, node: ast.AST) -> int:
        """Count the number of assertions in an AST node.

        Issue #315: Refactored to use helper for reduced nesting.
        """
        count = 0
        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                count += 1
            elif isinstance(child, ast.Call) and self._is_assertion_call(child):
                count += 1
        return count

    def _count_branches(self, node: ast.AST) -> int:
        """Count the number of branches (if/for/while/try) in an AST node."""
        count = 0
        for child in ast.walk(node):
            if isinstance(child, _BRANCH_TYPES):  # Issue #380
                count += 1
        return count

    def _get_function_lines(self, node: ast.FunctionDef) -> int:
        """Get the number of lines in a function."""
        if hasattr(node, "end_lineno") and node.end_lineno:
            return node.end_lineno - node.lineno + 1
        return 0

    def _has_pattern(self, content: str, patterns: List[re.Pattern]) -> bool:
        """Check if content matches any of the given patterns."""
        return any(p.search(content) for p in patterns)

    def _extract_test_functions(self, tree: ast.AST) -> List[ast.FunctionDef]:
        """Extract all test functions from an AST."""
        tests = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith("test_") or node.name.startswith("test"):
                    tests.append(node)
        return tests

    def _extract_test_classes(self, tree: ast.AST) -> List[ast.ClassDef]:
        """Extract all test classes from an AST."""
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name.startswith("Test") or node.name.endswith("Test"):
                    classes.append(node)
        return classes

    # =========================================================================
    # Anti-Pattern Detection Methods
    # =========================================================================

    def _detect_empty_test(
        self, func: ast.FunctionDef, file_path: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect tests with no assertions or only pass statements."""
        assertions = self._count_assertions(func)
        body_is_pass = (
            len(func.body) == 1
            and isinstance(func.body[0], ast.Pass)
        )
        body_is_docstring_only = (
            len(func.body) == 1
            and isinstance(func.body[0], ast.Expr)
            and isinstance(func.body[0].value, ast.Constant)
        )

        if assertions == 0 or body_is_pass or body_is_docstring_only:
            return TestAntiPatternResult(
                pattern_type=TestAntiPatternType.EMPTY_TEST,
                severity=TestPatternSeverity.HIGH,
                file_path=file_path,
                line_number=func.lineno,
                test_name=func.name,
                description=f"Test '{func.name}' has no assertions or is empty",
                suggestion="Add meaningful assertions to verify expected behavior",
                metrics={"assertion_count": assertions},
            )
        return None

    def _detect_no_assertion(
        self, func: ast.FunctionDef, file_path: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect tests without any assertions."""
        assertions = self._count_assertions(func)

        # Skip if already detected as empty
        if assertions == 0:
            # Check if there's actual code (not just pass/docstring)
            # Issue #380: Use module-level constant
            has_code = any(
                not isinstance(stmt, _EMPTY_STMT_TYPES)
                or (isinstance(stmt, ast.Expr) and not isinstance(stmt.value, ast.Constant))
                for stmt in func.body
            )
            if has_code:
                return TestAntiPatternResult(
                    pattern_type=TestAntiPatternType.NO_ASSERTION,
                    severity=TestPatternSeverity.HIGH,
                    file_path=file_path,
                    line_number=func.lineno,
                    test_name=func.name,
                    description=f"Test '{func.name}' executes code but has no assertions",
                    suggestion="Add assertions to verify the code produces expected results",
                    metrics={"assertion_count": 0},
                )
        return None

    def _detect_overly_complex_test(
        self, func: ast.FunctionDef, file_path: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect tests that are too complex."""
        lines = self._get_function_lines(func)
        branches = self._count_branches(func)

        if lines > self.COMPLEX_TEST_LINE_THRESHOLD or branches > self.COMPLEX_TEST_BRANCH_THRESHOLD:
            return TestAntiPatternResult(
                pattern_type=TestAntiPatternType.OVERLY_COMPLEX_TEST,
                severity=TestPatternSeverity.MEDIUM,
                file_path=file_path,
                line_number=func.lineno,
                test_name=func.name,
                description=f"Test '{func.name}' is overly complex ({lines} lines, {branches} branches)",
                suggestion="Break into smaller, focused tests that test one behavior each",
                metrics={"lines": lines, "branches": branches},
            )
        return None

    def _detect_multiple_assertions(
        self, func: ast.FunctionDef, file_path: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect tests with too many assertions (may test multiple things)."""
        assertions = self._count_assertions(func)

        if assertions > self.MAX_ASSERTIONS_PER_TEST:
            return TestAntiPatternResult(
                pattern_type=TestAntiPatternType.MULTIPLE_ASSERTIONS,
                severity=TestPatternSeverity.LOW,
                file_path=file_path,
                line_number=func.lineno,
                test_name=func.name,
                description=f"Test '{func.name}' has {assertions} assertions (max recommended: {self.MAX_ASSERTIONS_PER_TEST})",
                suggestion="Consider splitting into multiple focused tests",
                metrics={"assertion_count": assertions},
            )
        return None

    def _detect_flaky_patterns(
        self, func: ast.FunctionDef, file_path: str, content: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect patterns that may cause flaky tests."""
        # Get the source lines for this function
        if hasattr(func, "end_lineno") and func.end_lineno:
            lines = content.split("\n")[func.lineno - 1 : func.end_lineno]
            func_content = "\n".join(lines)
        else:
            func_content = content

        if self._has_pattern(func_content, self._flaky_patterns):
            return TestAntiPatternResult(
                pattern_type=TestAntiPatternType.FLAKY_TEST,
                severity=TestPatternSeverity.HIGH,
                file_path=file_path,
                line_number=func.lineno,
                test_name=func.name,
                description=f"Test '{func.name}' contains patterns that may cause flakiness (time.sleep, random, datetime)",
                suggestion="Use deterministic mocks for time, random, and datetime operations",
                metrics={},
            )
        return None

    def _detect_sleep_calls(
        self, func: ast.FunctionDef, file_path: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect explicit sleep calls in tests."""
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "sleep":
                        return TestAntiPatternResult(
                            pattern_type=TestAntiPatternType.SLEEPY_TEST,
                            severity=TestPatternSeverity.MEDIUM,
                            file_path=file_path,
                            line_number=node.lineno,
                            test_name=func.name,
                            description=f"Test '{func.name}' uses sleep() which slows down test suite",
                            suggestion="Use polling with timeouts or mock async operations",
                            metrics={},
                        )
        return None

    def _detect_external_dependencies(
        self, func: ast.FunctionDef, file_path: str, content: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect external network dependencies in tests."""
        if hasattr(func, "end_lineno") and func.end_lineno:
            lines = content.split("\n")[func.lineno - 1 : func.end_lineno]
            func_content = "\n".join(lines)
        else:
            func_content = content

        if self._has_pattern(func_content, self._external_patterns):
            return TestAntiPatternResult(
                pattern_type=TestAntiPatternType.NETWORK_DEPENDENCY,
                severity=TestPatternSeverity.MEDIUM,
                file_path=file_path,
                line_number=func.lineno,
                test_name=func.name,
                description=f"Test '{func.name}' has external network dependencies",
                suggestion="Mock external HTTP calls using responses, httpretty, or pytest-httpx",
                metrics={},
            )
        return None

    def _detect_database_dependencies(
        self, func: ast.FunctionDef, file_path: str, content: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect database dependencies in tests."""
        if hasattr(func, "end_lineno") and func.end_lineno:
            lines = content.split("\n")[func.lineno - 1 : func.end_lineno]
            func_content = "\n".join(lines)
        else:
            func_content = content

        if self._has_pattern(func_content, self._database_patterns):
            return TestAntiPatternResult(
                pattern_type=TestAntiPatternType.DATABASE_DEPENDENCY,
                severity=TestPatternSeverity.LOW,
                file_path=file_path,
                line_number=func.lineno,
                test_name=func.name,
                description=f"Test '{func.name}' has database dependencies",
                suggestion="Use test fixtures, in-memory databases, or mocks for database operations",
                metrics={},
            )
        return None

    def _detect_missing_docstring(
        self, func: ast.FunctionDef, file_path: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect tests without docstrings."""
        docstring = ast.get_docstring(func)

        if not docstring:
            return TestAntiPatternResult(
                pattern_type=TestAntiPatternType.MISSING_DOCSTRING,
                severity=TestPatternSeverity.INFO,
                file_path=file_path,
                line_number=func.lineno,
                test_name=func.name,
                description=f"Test '{func.name}' lacks a docstring",
                suggestion="Add a docstring explaining what behavior is being tested",
                metrics={},
            )
        return None

    def _detect_test_naming_issues(
        self, func: ast.FunctionDef, file_path: str
    ) -> Optional[TestAntiPatternResult]:
        """Detect poor test naming conventions."""
        name = func.name

        # Issue #380: Use pre-compiled patterns for non-descriptive name check
        for pattern in _BAD_TEST_NAME_PATTERNS:
            if pattern.match(name):
                return TestAntiPatternResult(
                    pattern_type=TestAntiPatternType.TEST_NAMING,
                    severity=TestPatternSeverity.LOW,
                    file_path=file_path,
                    line_number=func.lineno,
                    test_name=name,
                    description=f"Test '{name}' has a non-descriptive name",
                    suggestion="Use descriptive names like 'test_should_return_error_when_input_invalid'",
                    metrics={},
                )
        return None

    # =========================================================================
    # Coverage Gap Detection
    # =========================================================================

    def _build_tested_modules(self, test_files: List[str]) -> Set[str]:
        """Build set of module names that have tests (Issue #315 - extracted helper)."""
        tested_modules: Set[str] = set()
        for test_file in test_files:
            base = os.path.basename(test_file)
            if base.startswith("test_"):
                tested_modules.add(base[5:-3])  # Remove "test_" and ".py"
            elif base.endswith("_test.py"):
                tested_modules.add(base[:-8])  # Remove "_test.py"
        return tested_modules

    def _create_module_gap(self, source_file: str, module_name: str) -> CoverageGap:
        """Create gap for untested module (Issue #315 - extracted helper)."""
        return CoverageGap(
            source_file=source_file,
            source_function="<module>",
            source_line=1,
            gap_type="no_test",
            description=f"Module '{module_name}' has no corresponding test file",
            suggestion=f"Create test_{module_name}.py with tests for public functions",
            priority=TestPatternSeverity.MEDIUM,
        )

    def _create_function_gap(
        self, source_file: str, node: ast.FunctionDef
    ) -> CoverageGap:
        """Create gap for untested function (Issue #315 - extracted helper)."""
        return CoverageGap(
            source_file=source_file,
            source_function=node.name,
            source_line=node.lineno,
            gap_type="no_test",
            description=f"Function '{node.name}' has no test coverage",
            suggestion=f"Add test_{{scenario}}_{node.name} tests",
            priority=TestPatternSeverity.MEDIUM,
        )

    def _find_untested_functions(
        self, source_file: str, module_name: str, tested_modules: Set[str]
    ) -> List[CoverageGap]:
        """Find untested public functions in a source file (Issue #315 - extracted helper)."""
        gaps: List[CoverageGap] = []
        if module_name in tested_modules:
            return gaps

        try:
            with open(source_file, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                    gaps.append(self._create_function_gap(source_file, node))
        except Exception as e:
            logger.debug("Could not parse %s: %s", source_file, e)

        return gaps

    def _find_coverage_gaps(
        self,
        source_files: List[str],
        test_files: List[str],
    ) -> List[CoverageGap]:
        """Find coverage gaps by comparing source files to test files (Issue #315 - refactored)."""
        gaps: List[CoverageGap] = []
        tested_modules = self._build_tested_modules(test_files)

        for source_file in source_files:
            if self._should_exclude(source_file) or self.is_test_file(source_file):
                continue

            module_name = os.path.basename(source_file)[:-3]  # Remove ".py"
            if module_name.startswith("_"):
                continue

            if module_name not in tested_modules:
                gaps.append(self._create_module_gap(source_file, module_name))

            gaps.extend(
                self._find_untested_functions(source_file, module_name, tested_modules)
            )

        return gaps

    # =========================================================================
    # Quality Metrics
    # =========================================================================

    def _calculate_quality_metrics(
        self,
        test_files: List[str],
        anti_patterns: List[TestAntiPatternResult],
    ) -> Dict[TestQualityMetric, float]:
        """Calculate overall test quality metrics."""
        total_tests = 0
        total_assertions = 0
        total_lines = 0

        for test_file in test_files:
            try:
                with open(test_file, "r", encoding="utf-8") as f:
                    content = f.read()
                tree = ast.parse(content)
                tests = self._extract_test_functions(tree)
                total_tests += len(tests)

                for test in tests:
                    total_assertions += self._count_assertions(test)
                    total_lines += self._get_function_lines(test)
            except Exception as e:
                logger.debug("Could not analyze %s: %s", test_file, e)

        # Calculate metrics
        metrics = {}

        # Assertion density (assertions per test)
        if total_tests > 0:
            metrics[TestQualityMetric.ASSERTION_DENSITY] = total_assertions / total_tests
        else:
            metrics[TestQualityMetric.ASSERTION_DENSITY] = 0.0

        # Complexity score (inverse of average test size)
        if total_tests > 0:
            avg_lines = total_lines / total_tests
            # Scale: <20 lines = 100, >50 lines = 0
            metrics[TestQualityMetric.COMPLEXITY_SCORE] = max(0, 100 - (avg_lines - 20) * 2.5)
        else:
            metrics[TestQualityMetric.COMPLEXITY_SCORE] = 0.0

        # Issue score (fewer issues = higher score)
        issue_penalty = len(anti_patterns) * 5
        metrics[TestQualityMetric.MAINTAINABILITY_SCORE] = max(0, 100 - issue_penalty)

        # Calculate overall score
        weights = {
            TestQualityMetric.ASSERTION_DENSITY: 0.25,
            TestQualityMetric.COMPLEXITY_SCORE: 0.35,
            TestQualityMetric.MAINTAINABILITY_SCORE: 0.40,
        }

        overall = 0.0
        for metric, weight in weights.items():
            value = metrics.get(metric, 0)
            # Normalize assertion density to 0-100 scale
            if metric == TestQualityMetric.ASSERTION_DENSITY:
                value = min(100, value * 25)  # 4 assertions per test = 100
            overall += value * weight

        metrics[TestQualityMetric.OVERALL_SCORE] = overall

        return metrics

    # =========================================================================
    # Main Analysis Methods
    # =========================================================================

    def analyze_test_file(self, file_path: str) -> TestQualityReport:
        """
        Analyze a single test file for anti-patterns and quality issues.

        Args:
            file_path: Path to the test file

        Returns:
            TestQualityReport with findings
        """
        anti_patterns = []
        suggestions = []
        test_count = 0
        assertion_count = 0

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            tests = self._extract_test_functions(tree)
            test_count = len(tests)

            for func in tests:
                assertion_count += self._count_assertions(func)

                # Run all detection methods
                detectors = [
                    self._detect_empty_test,
                    self._detect_no_assertion,
                    self._detect_overly_complex_test,
                    self._detect_multiple_assertions,
                    self._detect_sleep_calls,
                    self._detect_missing_docstring,
                    self._detect_test_naming_issues,
                ]

                for detector in detectors:
                    result = detector(func, file_path)
                    if result:
                        anti_patterns.append(result)

                # Detectors that need content
                content_detectors = [
                    self._detect_flaky_patterns,
                    self._detect_external_dependencies,
                    self._detect_database_dependencies,
                ]

                for detector in content_detectors:
                    result = detector(func, file_path, content)
                    if result:
                        anti_patterns.append(result)

            # Generate suggestions
            if test_count == 0:
                suggestions.append("Add test functions to this test file")
            if assertion_count < test_count:
                suggestions.append("Ensure each test has at least one assertion")

        except Exception as e:
            logger.error("Error analyzing test file %s: %s", file_path, e)
            suggestions.append(f"Failed to analyze: {e}")

        metrics = self._calculate_quality_metrics([file_path], anti_patterns)

        return TestQualityReport(
            file_path=file_path,
            test_count=test_count,
            assertion_count=assertion_count,
            metrics=metrics,
            anti_patterns=anti_patterns,
            coverage_gaps=[],
            suggestions=suggestions,
        )

    def analyze_directory(self, directory: str) -> TestAnalysisReport:
        """
        Analyze all test files in a directory.

        Args:
            directory: Root directory to scan

        Returns:
            TestAnalysisReport with comprehensive findings
        """
        test_files = []
        source_files = []
        all_anti_patterns = []
        total_tests = 0
        total_assertions = 0

        # Collect all Python files
        for root, dirs, files in os.walk(directory):
            # Filter excluded directories
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]

            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = os.path.join(root, file)

                if self._should_exclude(file_path):
                    continue

                if self.is_test_file(file_path):
                    test_files.append(file_path)
                else:
                    source_files.append(file_path)

        # Analyze each test file
        for test_file in test_files:
            report = self.analyze_test_file(test_file)
            total_tests += report.test_count
            total_assertions += report.assertion_count
            all_anti_patterns.extend(report.anti_patterns)

        # Find coverage gaps
        coverage_gaps = self._find_coverage_gaps(source_files, test_files)

        # Calculate severity distribution
        severity_dist: Dict[str, int] = {}
        for pattern in all_anti_patterns:
            severity = pattern.severity.value
            severity_dist[severity] = severity_dist.get(severity, 0) + 1

        # Calculate overall metrics
        quality_metrics = self._calculate_quality_metrics(test_files, all_anti_patterns)

        # Generate suggestions
        suggestions = []
        if len(coverage_gaps) > 0:
            suggestions.append(f"Add tests for {len(coverage_gaps)} untested modules/functions")
        if severity_dist.get("high", 0) > 0:
            suggestions.append(f"Fix {severity_dist['high']} high-severity test issues")
        if quality_metrics.get(TestQualityMetric.OVERALL_SCORE, 0) < 70:
            suggestions.append("Improve test quality score by addressing anti-patterns")

        return TestAnalysisReport(
            scan_path=directory,
            total_test_files=len(test_files),
            total_tests=total_tests,
            total_assertions=total_assertions,
            anti_patterns=all_anti_patterns,
            coverage_gaps=coverage_gaps,
            quality_metrics=quality_metrics,
            severity_distribution=severity_dist,
            suggestions=suggestions,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def analyze_tests(path: str) -> TestAnalysisReport:
    """
    Analyze tests in a file or directory.

    Args:
        path: Path to file or directory

    Returns:
        TestAnalysisReport with findings
    """
    analyzer = TestPatternAnalyzer()

    if os.path.isfile(path):
        report = analyzer.analyze_test_file(path)
        return TestAnalysisReport(
            scan_path=path,
            total_test_files=1,
            total_tests=report.test_count,
            total_assertions=report.assertion_count,
            anti_patterns=report.anti_patterns,
            coverage_gaps=report.coverage_gaps,
            quality_metrics=report.metrics,
            severity_distribution={
                s.value: sum(1 for p in report.anti_patterns if p.severity == s)
                for s in TestPatternSeverity
            },
            suggestions=report.suggestions,
        )
    else:
        return analyzer.analyze_directory(path)


def get_test_anti_pattern_types() -> List[str]:
    """Get list of all test anti-pattern types."""
    return [t.value for t in TestAntiPatternType]


def get_test_quality_metrics() -> List[str]:
    """Get list of all test quality metrics."""
    return [m.value for m in TestQualityMetric]


def get_test_severity_levels() -> List[str]:
    """Get list of all severity levels."""
    return [s.value for s in TestPatternSeverity]
