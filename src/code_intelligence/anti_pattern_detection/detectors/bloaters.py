# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Bloater Anti-Pattern Detectors

Detects "bloater" anti-patterns that indicate code has grown too large:
- God Class: Classes with too many methods or lines
- Long Method: Functions/methods with too many lines
- Long Parameter List: Functions with too many parameters
- Deep Nesting: Excessive nesting depth
- Large File: Files with too many lines
- Data Clumps: Groups of parameters that appear together

Part of Issue #381 - God Class Refactoring
"""

import ast
from typing import List, Optional, Tuple

from ..models import AntiPatternResult
from ..severity_utils import (
    get_data_clump_severity,
    get_god_class_severity,
    get_large_file_severity,
    get_long_method_severity,
    get_nesting_severity,
    get_param_severity,
)
from ..types import AntiPatternSeverity, AntiPatternType, Thresholds


class BloaterDetector:
    """Detects bloater-type anti-patterns in code."""

    def __init__(
        self,
        god_class_method_threshold: int = Thresholds.GOD_CLASS_METHOD_THRESHOLD,
        god_class_line_threshold: int = Thresholds.GOD_CLASS_LINE_THRESHOLD,
        long_param_threshold: int = Thresholds.LONG_PARAMETER_THRESHOLD,
        large_file_threshold: int = Thresholds.LARGE_FILE_THRESHOLD,
        deep_nesting_threshold: int = Thresholds.DEEP_NESTING_THRESHOLD,
        long_method_threshold: int = Thresholds.LONG_METHOD_THRESHOLD,
        data_clump_threshold: int = Thresholds.DATA_CLUMP_OCCURRENCE_THRESHOLD,
    ):
        """
        Initialize bloater detector with configurable thresholds.

        Args:
            god_class_method_threshold: Max methods before class is a god class
            god_class_line_threshold: Max lines before class is a god class
            long_param_threshold: Max parameters before function has too many
            large_file_threshold: Max lines before file is too large
            deep_nesting_threshold: Max nesting depth allowed
            long_method_threshold: Max lines for a method/function
            data_clump_threshold: Min occurrences for data clump detection
        """
        self.god_class_method_threshold = god_class_method_threshold
        self.god_class_line_threshold = god_class_line_threshold
        self.long_param_threshold = long_param_threshold
        self.large_file_threshold = large_file_threshold
        self.deep_nesting_threshold = deep_nesting_threshold
        self.long_method_threshold = long_method_threshold
        self.data_clump_threshold = data_clump_threshold

    # =========================================================================
    # God Class Detection
    # =========================================================================

    def check_god_class(
        self,
        node: ast.ClassDef,
        file_path: str,
        method_count: int,
        class_lines: int,
    ) -> Optional[AntiPatternResult]:
        """
        Check if a class is a god class based on method count or line count.

        Args:
            node: AST node for the class
            file_path: Path to the source file
            method_count: Number of methods in the class
            class_lines: Number of lines in the class

        Returns:
            AntiPatternResult if god class detected, None otherwise
        """
        if method_count > self.god_class_method_threshold:
            return AntiPatternResult(
                pattern_type=AntiPatternType.GOD_CLASS,
                severity=get_god_class_severity(method_count),
                file_path=file_path,
                line_number=node.lineno,
                entity_name=node.name,
                description=(
                    f"Class '{node.name}' has {method_count} methods, "
                    f"exceeds threshold of {self.god_class_method_threshold}"
                ),
                suggestion=(
                    "Consider breaking into smaller, focused classes "
                    "using composition or inheritance"
                ),
                metrics={
                    "method_count": method_count,
                    "line_count": class_lines,
                    "threshold": self.god_class_method_threshold,
                },
            )
        elif class_lines > self.god_class_line_threshold:
            return AntiPatternResult(
                pattern_type=AntiPatternType.GOD_CLASS,
                severity=AntiPatternSeverity.MEDIUM,
                file_path=file_path,
                line_number=node.lineno,
                entity_name=node.name,
                description=(
                    f"Class '{node.name}' has {class_lines} lines, "
                    f"exceeds threshold of {self.god_class_line_threshold}"
                ),
                suggestion="Consider extracting methods or splitting responsibilities",
                metrics={"method_count": method_count, "line_count": class_lines},
            )
        return None

    # =========================================================================
    # Long Parameter List Detection
    # =========================================================================

    def count_function_params(self, node: ast.FunctionDef) -> int:
        """
        Count total parameters in a function including *args and **kwargs.

        Args:
            node: AST FunctionDef node

        Returns:
            Total number of parameters
        """
        param_count = len(node.args.args) + len(node.args.kwonlyargs)
        if node.args.vararg:
            param_count += 1
        if node.args.kwarg:
            param_count += 1
        return param_count

    def check_long_parameter_list(
        self,
        node: ast.FunctionDef,
        file_path: str,
        param_count: Optional[int] = None,
    ) -> Optional[AntiPatternResult]:
        """
        Check if a function has too many parameters.

        Args:
            node: AST FunctionDef node
            file_path: Path to the source file
            param_count: Pre-computed parameter count (optional)

        Returns:
            AntiPatternResult if too many parameters, None otherwise
        """
        if param_count is None:
            param_count = self.count_function_params(node)

        if param_count <= self.long_param_threshold:
            return None

        return AntiPatternResult(
            pattern_type=AntiPatternType.LONG_PARAMETER_LIST,
            severity=get_param_severity(param_count),
            file_path=file_path,
            line_number=node.lineno,
            entity_name=node.name,
            description=(
                f"Function '{node.name}' has {param_count} parameters, "
                f"exceeds threshold of {self.long_param_threshold}"
            ),
            suggestion=(
                "Consider using a configuration object or "
                "dataclass to group related parameters"
            ),
            metrics={
                "param_count": param_count,
                "threshold": self.long_param_threshold,
            },
        )

    # =========================================================================
    # Long Method Detection
    # =========================================================================

    def check_long_method(
        self,
        node: ast.FunctionDef,
        file_path: str,
    ) -> Optional[AntiPatternResult]:
        """
        Check if a method/function is too long.

        Args:
            node: AST FunctionDef node
            file_path: Path to the source file

        Returns:
            AntiPatternResult if method too long, None otherwise
        """
        func_start = node.lineno
        func_end = getattr(node, "end_lineno", func_start)
        func_lines = func_end - func_start + 1

        if func_lines <= self.long_method_threshold:
            return None

        return AntiPatternResult(
            pattern_type=AntiPatternType.LONG_METHOD,
            severity=get_long_method_severity(func_lines),
            file_path=file_path,
            line_number=node.lineno,
            entity_name=node.name,
            description=(
                f"Function '{node.name}' has {func_lines} lines, "
                f"exceeds threshold of {self.long_method_threshold}"
            ),
            suggestion="Consider extracting smaller, focused functions",
            metrics={
                "line_count": func_lines,
                "threshold": self.long_method_threshold,
            },
        )

    # =========================================================================
    # Deep Nesting Detection
    # =========================================================================

    def calculate_nesting_depth(self, node: ast.AST, depth: int = 0) -> int:
        """
        Calculate maximum nesting depth in a code block.

        Args:
            node: AST node to analyze
            depth: Current depth level

        Returns:
            Maximum nesting depth found
        """
        max_depth = depth

        # Nodes that increase nesting depth
        nesting_nodes = (
            ast.If,
            ast.For,
            ast.While,
            ast.With,
            ast.Try,
            ast.ExceptHandler,
        )

        for child in ast.iter_child_nodes(node):
            if isinstance(child, nesting_nodes):
                child_depth = self.calculate_nesting_depth(child, depth + 1)
                max_depth = max(max_depth, child_depth)
            else:
                child_depth = self.calculate_nesting_depth(child, depth)
                max_depth = max(max_depth, child_depth)

        return max_depth

    def check_deep_nesting(
        self,
        node: ast.FunctionDef,
        file_path: str,
    ) -> Optional[AntiPatternResult]:
        """
        Check if a function has excessive nesting.

        Args:
            node: AST FunctionDef node
            file_path: Path to the source file

        Returns:
            AntiPatternResult if nesting too deep, None otherwise
        """
        max_depth = self.calculate_nesting_depth(node)

        if max_depth <= self.deep_nesting_threshold:
            return None

        return AntiPatternResult(
            pattern_type=AntiPatternType.DEEP_NESTING,
            severity=get_nesting_severity(max_depth),
            file_path=file_path,
            line_number=node.lineno,
            entity_name=node.name,
            description=(
                f"Function '{node.name}' has nesting depth of "
                f"{max_depth}, exceeds threshold of {self.deep_nesting_threshold}"
            ),
            suggestion=(
                "Consider early returns, guard clauses, or "
                "extracting nested logic to separate functions"
            ),
            metrics={
                "nesting_depth": max_depth,
                "threshold": self.deep_nesting_threshold,
            },
        )

    # =========================================================================
    # Large File Detection
    # =========================================================================

    def check_large_file(
        self,
        file_path: str,
        line_count: int,
    ) -> Optional[AntiPatternResult]:
        """
        Check if a file is too large.

        Args:
            file_path: Path to the source file
            line_count: Number of lines in the file

        Returns:
            AntiPatternResult if file too large, None otherwise
        """
        if line_count <= self.large_file_threshold:
            return None

        return AntiPatternResult(
            pattern_type=AntiPatternType.LARGE_FILE,
            severity=get_large_file_severity(line_count),
            file_path=file_path,
            line_number=1,
            entity_name=file_path,
            description=(
                f"File has {line_count} lines, "
                f"exceeds threshold of {self.large_file_threshold}"
            ),
            suggestion="Consider splitting into multiple modules by responsibility",
            metrics={
                "line_count": line_count,
                "threshold": self.large_file_threshold,
            },
        )

    # =========================================================================
    # Data Clumps Detection
    # =========================================================================

    def _collect_param_groups(self, tree: ast.AST) -> dict:
        """Collect parameter combination groups from all functions. Issue #620."""
        param_groups: dict[tuple, list] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = self._extract_param_names(node)
                if len(params) >= 3:
                    for combo in self._get_combinations(params, 3):
                        key = tuple(sorted(combo))
                        if key not in param_groups:
                            param_groups[key] = []
                        param_groups[key].append((node.name, node.lineno))
        return param_groups

    def _build_clump_result(
        self, param_combo: tuple, occurrences: list, file_path: str
    ) -> AntiPatternResult:
        """Build AntiPatternResult for a detected data clump. Issue #620."""
        func_names = [occ[0] for occ in occurrences]
        first_line = occurrences[0][1]
        return AntiPatternResult(
            pattern_type=AntiPatternType.DATA_CLUMPS,
            severity=get_data_clump_severity(len(occurrences)),
            file_path=file_path,
            line_number=first_line,
            entity_name=", ".join(param_combo),
            description=(
                f"Parameters ({', '.join(param_combo)}) appear together "
                f"in {len(occurrences)} functions: {', '.join(func_names[:3])}"
                f"{'...' if len(func_names) > 3 else ''}"
            ),
            suggestion=(
                "Consider grouping these parameters into a dataclass " "or named tuple"
            ),
            metrics={
                "parameters": list(param_combo),
                "occurrence_count": len(occurrences),
                "functions": func_names,
            },
        )

    def detect_data_clumps(
        self, tree: ast.AST, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect data clumps - groups of parameters that appear together.

        Args:
            tree: AST tree to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for detected data clumps
        """
        param_groups = self._collect_param_groups(tree)
        results: List[AntiPatternResult] = []
        for param_combo, occurrences in param_groups.items():
            if len(occurrences) >= self.data_clump_threshold:
                results.append(
                    self._build_clump_result(param_combo, occurrences, file_path)
                )
        return results

    def _extract_param_names(self, node: ast.FunctionDef) -> List[str]:
        """Extract parameter names from function, excluding self/cls."""
        params = []
        for arg in node.args.args:
            if arg.arg not in ("self", "cls"):
                params.append(arg.arg)
        return params

    def _get_combinations(self, items: List[str], size: int) -> List[Tuple[str, ...]]:
        """Get all combinations of items of given size."""
        if size > len(items):
            return []

        result = []

        def backtrack(start: int, current: List[str]):
            if len(current) == size:
                result.append(tuple(current))
                return
            for i in range(start, len(items)):
                current.append(items[i])
                backtrack(i + 1, current)
                current.pop()

        backtrack(0, [])
        return result

    # =========================================================================
    # Class Analysis Helpers
    # =========================================================================

    def get_class_methods(self, node: ast.ClassDef) -> List[ast.AST]:
        """
        Get all method definitions from a class.

        Args:
            node: AST ClassDef node

        Returns:
            List of function definition nodes
        """
        return [
            child
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

    def calculate_class_size(self, node: ast.ClassDef) -> int:
        """
        Calculate the total line count of a class.

        Args:
            node: AST ClassDef node

        Returns:
            Number of lines in the class
        """
        class_start = node.lineno
        class_end = max(
            (getattr(n, "end_lineno", class_start) for n in ast.walk(node)),
            default=class_start,
        )
        return class_end - class_start + 1
