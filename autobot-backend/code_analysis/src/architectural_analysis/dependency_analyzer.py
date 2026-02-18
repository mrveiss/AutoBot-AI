# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dependency Analyzer Module

Analyzes and extracts dependencies between components.
Extracted from ArchitecturalPatternAnalyzer as part of Issue #394.
"""

import ast
from typing import Dict, List

# Module-level tuple for function/class types
_FUNC_OR_CLASS_TYPES = (ast.FunctionDef, ast.ClassDef)


class DependencyAnalyzer:
    """
    Analyzer for component dependencies.

    Extracts and analyzes dependencies from AST nodes.

    Example:
        >>> analyzer = DependencyAnalyzer()
        >>> deps = analyzer.extract_class_dependencies(class_node, content)
    """

    def extract_module_dependencies(self, tree: ast.AST) -> List[str]:
        """
        Extract module-level dependencies from imports.

        Args:
            tree: AST module tree

        Returns:
            List of module dependency names
        """
        dependencies = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dependencies.extend([alias.name for alias in node.names])
            elif isinstance(node, ast.ImportFrom) and node.module:
                dependencies.append(node.module)
        return dependencies

    def extract_public_interfaces(self, tree: ast.AST) -> List[str]:
        """
        Extract public functions/classes as interfaces.

        Args:
            tree: AST module tree

        Returns:
            List of public interface names
        """
        return [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, _FUNC_OR_CLASS_TYPES) and not node.name.startswith("_")
        ]

    def extract_class_dependencies(self, node: ast.ClassDef, content: str) -> List[str]:
        """
        Extract dependencies for a class.

        Args:
            node: AST ClassDef node
            content: Source code content

        Returns:
            List of dependency names
        """
        dependencies = []

        # Base classes
        dependencies.extend(self._extract_base_class_dependencies(node))

        # Method calls and attribute access
        dependencies.extend(self._extract_call_dependencies(node))

        return list(set(dependencies))

    def _extract_base_class_dependencies(self, node: ast.ClassDef) -> List[str]:
        """Extract base class dependencies."""
        return [base.id for base in node.bases if isinstance(base, ast.Name)]

    def _extract_call_dependencies(self, node: ast.AST) -> List[str]:
        """Extract dependencies from function/method calls."""
        dependencies = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue

            if isinstance(child.func, ast.Name):
                dependencies.append(child.func.id)
            elif isinstance(child.func, ast.Attribute) and isinstance(
                child.func.value, ast.Name
            ):
                dependencies.append(child.func.value.id)

        return dependencies

    def extract_function_dependencies(
        self, node: ast.FunctionDef, content: str
    ) -> List[str]:
        """
        Extract dependencies for a function.

        Args:
            node: AST FunctionDef node
            content: Source code content

        Returns:
            List of dependency names
        """
        return list(set(self._extract_call_dependencies(node)))

    def detect_circular_dependencies(
        self, dependencies: Dict[str, List[str]]
    ) -> List[str]:
        """
        Detect circular dependencies using DFS.

        Args:
            dependencies: Mapping of component names to their dependencies

        Returns:
            List of component names involved in circular dependencies
        """
        visited = set()
        rec_stack = set()
        circular = []

        def dfs(node):
            if node in rec_stack:
                return True
            if node in visited:
                return False

            visited.add(node)
            rec_stack.add(node)

            for neighbor in dependencies.get(node, []):
                if neighbor in dependencies and dfs(neighbor):
                    circular.append(node)
                    return True

            rec_stack.remove(node)
            return False

        for node in dependencies:
            if node not in visited:
                dfs(node)

        return circular


__all__ = ["DependencyAnalyzer"]
