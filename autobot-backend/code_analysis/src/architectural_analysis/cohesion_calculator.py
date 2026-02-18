# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cohesion Calculator Module

Calculates cohesion metrics for classes and modules.
Extracted from ArchitecturalPatternAnalyzer as part of Issue #394.
"""

import ast
from typing import Dict, List

# Module-level tuple for function/class types
_FUNC_OR_CLASS_TYPES = (ast.FunctionDef, ast.ClassDef)


class CohesionCalculator:
    """
    Calculator for cohesion metrics.

    Measures how closely related the methods and attributes within a class
    or module are to each other.

    Example:
        >>> calculator = CohesionCalculator()
        >>> cohesion = calculator.calculate_class_cohesion(class_node)
    """

    def calculate_class_cohesion(self, node: ast.ClassDef) -> float:
        """
        Calculate class cohesion using method interactions.

        Args:
            node: AST ClassDef node to analyze

        Returns:
            Cohesion score between 0.0 and 1.0
        """
        methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
        if len(methods) <= 1:
            return 1.0

        attribute_refs = self._collect_attribute_references(methods)
        if not attribute_refs:
            return 0.5  # Neutral cohesion

        return self._compute_cohesion_ratio(attribute_refs)

    def _collect_attribute_references(
        self, methods: List[ast.FunctionDef]
    ) -> Dict[str, List[str]]:
        """Collect attribute references from methods."""
        attribute_refs: Dict[str, List[str]] = {}
        for method in methods:
            self._collect_self_attributes(method, attribute_refs)
        return attribute_refs

    def _collect_self_attributes(
        self, method: ast.FunctionDef, attribute_refs: Dict[str, List[str]]
    ) -> None:
        """Collect self.* attribute references from a method."""
        for child in ast.walk(method):
            if not self._is_self_attribute(child):
                continue
            attr_name = child.attr
            if attr_name not in attribute_refs:
                attribute_refs[attr_name] = []
            attribute_refs[attr_name].append(method.name)

    def _is_self_attribute(self, node: ast.AST) -> bool:
        """Check if node is a self.* attribute access."""
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        )

    def _compute_cohesion_ratio(self, attribute_refs: Dict[str, List[str]]) -> float:
        """Compute cohesion ratio from attribute references."""
        shared_attributes = sum(
            1 for methods_list in attribute_refs.values() if len(methods_list) > 1
        )
        total_attributes = len(attribute_refs)
        return shared_attributes / total_attributes if total_attributes > 0 else 0.5

    def calculate_module_cohesion(self, tree: ast.AST) -> float:
        """
        Calculate module cohesion.

        Uses heuristic: ratio of internal calls to total calls.

        Args:
            tree: AST module tree

        Returns:
            Cohesion score between 0.0 and 1.0
        """
        internal_calls = 0
        external_calls = 0

        # Get all defined names in the module
        defined_names = set()
        for node in ast.walk(tree):
            if isinstance(node, _FUNC_OR_CLASS_TYPES):
                defined_names.add(node.name)

        # Count internal vs external calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in defined_names:
                    internal_calls += 1
                else:
                    external_calls += 1

        total_calls = internal_calls + external_calls
        return internal_calls / total_calls if total_calls > 0 else 1.0


__all__ = ["CohesionCalculator"]
