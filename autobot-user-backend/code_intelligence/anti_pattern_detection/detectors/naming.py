# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Naming Anti-Pattern Detectors

Detects naming-related anti-patterns:
- Inconsistent Naming: Mixed naming conventions in the same scope
- Single Letter Variable: Variables with non-descriptive single letter names
- Magic Number: Unexplained numeric literals
- Complex Conditional: Overly complex boolean expressions
- Missing Docstring: Public API without documentation

Part of Issue #381 - God Class Refactoring
"""

import ast
from typing import Dict, List, Optional

from ..models import AntiPatternResult
from ..severity_utils import get_complex_conditional_severity
from ..types import (
    ALLOWED_MAGIC_NUMBERS,
    CAMEL_CASE_RE,
    SNAKE_CASE_RE,
    AntiPatternSeverity,
    AntiPatternType,
    Thresholds,
)

# Issue #314: Comprehensive list of acceptable single-letter variables
ACCEPTABLE_SINGLE_LETTER_VARS = frozenset(
    {
        # Loop counters (universal convention)
        "i",
        "j",
        "k",
        "n",
        # Coordinates (universal in graphics/math)
        "x",
        "y",
        "z",
        # Mathematical formulas (common in algorithms)
        "a",
        "b",
        "c",
        "d",
        # Common Python conventions
        "e",  # Exception: except Exception as e
        "f",  # File handle: with open(...) as f
        "m",  # Match object: m = re.match(...)
        "p",  # Path: p = Path(...)
        "r",  # Response/result: r = requests.get(...)
        "s",  # String: s = str(...)
        "t",  # Time/tuple: t = time.time()
        "v",  # Value (in dict iteration): for k, v in d.items()
        "w",  # Width/writer
        "h",  # Height/handle
        "q",  # Queue: q = Queue()
        "_",  # Unused variable (universal)
    }
)


class NamingDetector:
    """Detects naming-related anti-patterns in code."""

    def __init__(
        self,
        complex_conditional_threshold: int = Thresholds.COMPLEX_CONDITIONAL_THRESHOLD,
        magic_number_threshold: int = 2,  # Min occurrences to flag
    ):
        """
        Initialize naming detector with configurable thresholds.

        Args:
            complex_conditional_threshold: Max conditions before flagging
            magic_number_threshold: Min occurrences for magic number detection
        """
        self.complex_conditional_threshold = complex_conditional_threshold
        self.magic_number_threshold = magic_number_threshold

    # =========================================================================
    # Naming Convention Detection
    # =========================================================================

    def is_snake_case(self, name: str) -> bool:
        """Check if name follows snake_case convention."""
        return bool(SNAKE_CASE_RE.match(name))

    def is_camel_case(self, name: str) -> bool:
        """Check if name follows camelCase convention."""
        return bool(CAMEL_CASE_RE.match(name)) and "_" not in name

    def detect_naming_issues(
        self,
        node: ast.ClassDef,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect inconsistent naming conventions within a class.

        Args:
            node: AST ClassDef node to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for detected naming issues
        """
        patterns: List[AntiPatternResult] = []

        snake_case: List[str] = []
        camel_case: List[str] = []

        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._classify_function_name(child, snake_case, camel_case)

        # Flag if both conventions are used
        if snake_case and camel_case:
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.INCONSISTENT_NAMING,
                    severity=AntiPatternSeverity.LOW,
                    file_path=file_path,
                    line_number=node.lineno,
                    entity_name=node.name,
                    description=(
                        f"Class '{node.name}' has mixed naming conventions: "
                        f"{len(snake_case)} snake_case, {len(camel_case)} camelCase"
                    ),
                    suggestion="Use consistent snake_case naming (Python standard)",
                    metrics={
                        "snake_case_count": len(snake_case),
                        "camel_case_count": len(camel_case),
                        "snake_case_methods": snake_case[:5],
                        "camel_case_methods": camel_case[:5],
                    },
                )
            )

        return patterns

    def _classify_function_name(
        self,
        child: ast.AST,
        snake_case: List[str],
        camel_case: List[str],
    ) -> None:
        """Classify function name by convention."""
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return

        name = child.name
        if name.startswith("_"):
            return

        if self.is_snake_case(name):
            snake_case.append(name)
        elif self.is_camel_case(name):
            camel_case.append(name)

    # =========================================================================
    # Single Letter Variable Detection
    # =========================================================================

    def detect_single_letter_vars(
        self,
        node: ast.FunctionDef,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect non-descriptive single-letter variable names.

        Args:
            node: AST FunctionDef node to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for problematic single-letter variables
        """
        patterns: List[AntiPatternResult] = []
        problematic_vars: List[str] = []

        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                name = child.id
                if (
                    len(name) == 1
                    and name not in ACCEPTABLE_SINGLE_LETTER_VARS
                    and name not in problematic_vars
                ):
                    problematic_vars.append(name)

        if problematic_vars:
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.SINGLE_LETTER_VARIABLE,
                    severity=AntiPatternSeverity.INFO,
                    file_path=file_path,
                    line_number=node.lineno,
                    entity_name=node.name,
                    description=(
                        f"Function uses non-descriptive single-letter variables: "
                        f"{', '.join(problematic_vars)}"
                    ),
                    suggestion="Use descriptive variable names for better readability",
                    metrics={"variables": problematic_vars},
                )
            )

        return patterns

    # =========================================================================
    # Magic Number Detection
    # =========================================================================

    def detect_magic_numbers(
        self,
        node: ast.AST,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect magic numbers (unexplained numeric literals).

        Args:
            node: AST node to analyze (typically a FunctionDef or Module)
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for detected magic numbers
        """
        patterns: List[AntiPatternResult] = []
        number_occurrences: Dict[float, List[int]] = {}

        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(
                child.value, (int, float)
            ):
                value = child.value
                if value not in ALLOWED_MAGIC_NUMBERS:
                    if value not in number_occurrences:
                        number_occurrences[value] = []
                    number_occurrences[value].append(getattr(child, "lineno", 0))

        # Flag numbers that appear multiple times
        for value, lines in number_occurrences.items():
            if len(lines) >= self.magic_number_threshold:
                patterns.append(
                    AntiPatternResult(
                        pattern_type=AntiPatternType.MAGIC_NUMBER,
                        severity=AntiPatternSeverity.LOW,
                        file_path=file_path,
                        line_number=lines[0],
                        entity_name=str(value),
                        description=f"Magic number {value} appears {len(lines)} times",
                        suggestion="Extract to a named constant for clarity",
                        metrics={
                            "value": value,
                            "occurrences": len(lines),
                            "lines": lines[:5],  # First 5 occurrences
                        },
                    )
                )

        return patterns

    # =========================================================================
    # Complex Conditional Detection
    # =========================================================================

    def detect_complex_conditionals(
        self,
        node: ast.FunctionDef,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect overly complex conditional expressions.

        Args:
            node: AST FunctionDef node to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for complex conditionals
        """
        patterns: List[AntiPatternResult] = []

        for child in ast.walk(node):
            if isinstance(child, ast.BoolOp):
                condition_count = self._count_conditions(child)
                if condition_count > self.complex_conditional_threshold:
                    patterns.append(
                        AntiPatternResult(
                            pattern_type=AntiPatternType.COMPLEX_CONDITIONAL,
                            severity=get_complex_conditional_severity(condition_count),
                            file_path=file_path,
                            line_number=getattr(child, "lineno", node.lineno),
                            entity_name=node.name,
                            description=(
                                f"Complex conditional with {condition_count} "
                                f"conditions (threshold: {self.complex_conditional_threshold})"
                            ),
                            suggestion=(
                                "Extract conditions to well-named boolean variables "
                                "or use early returns"
                            ),
                            metrics={
                                "condition_count": condition_count,
                                "threshold": self.complex_conditional_threshold,
                            },
                        )
                    )

        return patterns

    def _count_conditions(self, node: ast.BoolOp) -> int:
        """Recursively count conditions in a boolean expression."""
        count = 0
        for value in node.values:
            if isinstance(value, ast.BoolOp):
                count += self._count_conditions(value)
            else:
                count += 1
        return count

    # =========================================================================
    # Missing Docstring Detection
    # =========================================================================

    def detect_missing_docstrings(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect public functions/classes without docstrings.

        Args:
            tree: AST tree to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for missing docstrings
        """
        patterns: List[AntiPatternResult] = []

        for child in ast.walk(tree):
            # Check functions
            result = self._check_function_docstring(child, file_path)
            if result:
                patterns.append(result)
                continue

            # Check classes
            result = self._check_class_docstring(child, file_path)
            if result:
                patterns.append(result)

        return patterns

    def _check_function_docstring(
        self,
        child: ast.AST,
        file_path: str,
    ) -> Optional[AntiPatternResult]:
        """Check if public function lacks docstring."""
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return None
        if child.name.startswith("_"):
            return None
        if ast.get_docstring(child):
            return None

        return AntiPatternResult(
            pattern_type=AntiPatternType.MISSING_DOCSTRING,
            severity=AntiPatternSeverity.INFO,
            file_path=file_path,
            line_number=child.lineno,
            entity_name=child.name,
            description=f"Public function '{child.name}' lacks docstring",
            suggestion="Add a docstring explaining purpose and parameters",
            metrics={"type": "function"},
        )

    def _check_class_docstring(
        self,
        child: ast.AST,
        file_path: str,
    ) -> Optional[AntiPatternResult]:
        """Check if public class lacks docstring."""
        if not isinstance(child, ast.ClassDef):
            return None
        if child.name.startswith("_"):
            return None
        if ast.get_docstring(child):
            return None

        return AntiPatternResult(
            pattern_type=AntiPatternType.MISSING_DOCSTRING,
            severity=AntiPatternSeverity.LOW,
            file_path=file_path,
            line_number=child.lineno,
            entity_name=child.name,
            description=f"Public class '{child.name}' lacks docstring",
            suggestion="Add a docstring explaining class purpose",
            metrics={"type": "class"},
        )
