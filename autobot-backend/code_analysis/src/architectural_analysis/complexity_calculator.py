# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Complexity Calculator Module

Calculates complexity metrics for classes and functions.
Extracted from ArchitecturalPatternAnalyzer as part of Issue #394.
"""

import ast
from typing import List

# Module-level tuples for AST node type checks
_COMPLEXITY_BRANCH_TYPES = (ast.If, ast.While, ast.For, ast.ExceptHandler)
_BOOLEAN_OP_TYPES = (ast.And, ast.Or)


class ComplexityCalculator:
    """
    Calculator for complexity metrics.

    Measures cyclomatic complexity and structural complexity of code.

    Example:
        >>> calculator = ComplexityCalculator()
        >>> complexity = calculator.calculate_class_complexity(class_node)
    """

    def calculate_class_complexity(self, node: ast.ClassDef) -> int:
        """
        Calculate class complexity.

        Counts methods and attributes defined in the class.

        Args:
            node: AST ClassDef node to analyze

        Returns:
            Complexity score (integer)
        """
        complexity = 0

        # Count methods
        methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
        complexity += len(methods)

        # Count attributes
        complexity += self._count_class_attributes(methods)

        return complexity

    def _count_class_attributes(self, methods: List[ast.FunctionDef]) -> int:
        """Count class attributes defined in __init__."""
        count = 0
        for method in methods:
            if method.name != "__init__":
                continue

            for child in ast.walk(method):
                if isinstance(child, ast.Assign):
                    count += self._count_attribute_assignments(child)

        return count

    def _count_attribute_assignments(self, assign_node: ast.Assign) -> int:
        """Count attribute assignments in an assign node."""
        return sum(
            1 for target in assign_node.targets if isinstance(target, ast.Attribute)
        )

    def calculate_function_complexity(self, node: ast.FunctionDef) -> int:
        """
        Calculate function complexity using cyclomatic complexity.

        Args:
            node: AST FunctionDef node to analyze

        Returns:
            Cyclomatic complexity score
        """
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            if isinstance(child, _COMPLEXITY_BRANCH_TYPES):
                complexity += 1
            elif isinstance(child, _BOOLEAN_OP_TYPES):
                complexity += 1

        return complexity


__all__ = ["ComplexityCalculator"]
