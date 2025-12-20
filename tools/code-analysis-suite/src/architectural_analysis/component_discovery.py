# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Component Discovery Module

Discovers and extracts architectural components from code.
Extracted from ArchitecturalPatternAnalyzer as part of Issue #394.
"""

import ast
import logging
from pathlib import Path
from typing import List, Optional

from .types import ArchitecturalComponent
from .cohesion_calculator import CohesionCalculator
from .complexity_calculator import ComplexityCalculator
from .dependency_analyzer import DependencyAnalyzer
from .pattern_detector import PatternDetector

logger = logging.getLogger(__name__)


class ComponentDiscovery:
    """
    Discovers architectural components in a codebase.

    Extracts classes, functions, and modules as architectural components.

    Example:
        >>> discovery = ComponentDiscovery()
        >>> components = await discovery.discover_components(".", ["**/*.py"])
    """

    # Default patterns to skip
    DEFAULT_SKIP_PATTERNS = [
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "test_",
        "_test.py",
        ".pyc",
    ]

    def __init__(
        self,
        skip_patterns: List[str] = None,
        cohesion_calculator: CohesionCalculator = None,
        complexity_calculator: ComplexityCalculator = None,
        dependency_analyzer: DependencyAnalyzer = None,
        pattern_detector: PatternDetector = None,
    ):
        """
        Initialize component discovery.

        Args:
            skip_patterns: Patterns to skip during discovery
            cohesion_calculator: Cohesion calculator instance
            complexity_calculator: Complexity calculator instance
            dependency_analyzer: Dependency analyzer instance
            pattern_detector: Pattern detector instance
        """
        self.skip_patterns = skip_patterns or self.DEFAULT_SKIP_PATTERNS
        self._cohesion = cohesion_calculator or CohesionCalculator()
        self._complexity = complexity_calculator or ComplexityCalculator()
        self._deps = dependency_analyzer or DependencyAnalyzer()
        self._patterns = pattern_detector or PatternDetector()

    async def discover_components(
        self, root_path: str, patterns: List[str]
    ) -> List[ArchitecturalComponent]:
        """
        Discover architectural components in the codebase.

        Args:
            root_path: Root directory to search
            patterns: Glob patterns for files to analyze

        Returns:
            List of discovered ArchitecturalComponent objects
        """
        components = []
        root = Path(root_path)

        for pattern in patterns:
            for file_path in root.glob(pattern):
                await self._process_file_for_components(file_path, components)

        return components

    async def _process_file_for_components(
        self, file_path: Path, components: List[ArchitecturalComponent]
    ) -> None:
        """Process a single file to extract components."""
        if not file_path.is_file() or self._should_skip_file(file_path):
            return

        try:
            file_components = await self._extract_components_from_file(str(file_path))
            components.extend(file_components)
        except Exception as e:
            logger.warning(f"Failed to extract components from {file_path}: {e}")

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        path_str = str(file_path)
        return any(pattern in path_str for pattern in self.skip_patterns)

    async def _extract_components_from_file(
        self, file_path: str
    ) -> List[ArchitecturalComponent]:
        """Extract architectural components from a file."""
        components = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=file_path)
            self._extract_nodes_from_tree(tree, file_path, content, components)

            # Module-level component
            module_component = self._analyze_module_component(file_path, tree, content)
            if module_component:
                components.append(module_component)

        except SyntaxError:
            # Skip files with syntax errors
            pass
        except Exception as e:
            logger.error(f"Error extracting components from {file_path}: {e}")

        return components

    def _extract_nodes_from_tree(
        self,
        tree: ast.AST,
        file_path: str,
        content: str,
        components: List[ArchitecturalComponent],
    ) -> None:
        """Extract class and function nodes from AST tree."""
        for node in ast.walk(tree):
            component = self._extract_single_node(node, tree, file_path, content)
            if component:
                components.append(component)

    def _extract_single_node(
        self, node: ast.AST, tree: ast.AST, file_path: str, content: str
    ) -> Optional[ArchitecturalComponent]:
        """Extract a single node as a component."""
        if isinstance(node, ast.ClassDef):
            return self._analyze_class_component(node, file_path, content)
        if isinstance(node, ast.FunctionDef) and not self._is_method(node, tree):
            return self._analyze_function_component(node, file_path, content)
        return None

    def _analyze_class_component(
        self, node: ast.ClassDef, file_path: str, content: str
    ) -> Optional[ArchitecturalComponent]:
        """Analyze a class as an architectural component."""
        try:
            # Extract dependencies
            dependencies = self._deps.extract_class_dependencies(node, content)

            # Extract interfaces (methods)
            interfaces = [
                method.name
                for method in node.body
                if isinstance(method, ast.FunctionDef)
            ]

            # Check if abstract
            is_abstract = self._is_abstract_class(node)

            # Calculate metrics
            coupling_score = len(dependencies)
            cohesion_score = self._cohesion.calculate_class_cohesion(node)
            complexity_score = self._complexity.calculate_class_complexity(node)

            # Detect patterns
            patterns = self._patterns.detect_class_patterns(node, content)

            return ArchitecturalComponent(
                file_path=file_path,
                component_type="class",
                name=node.name,
                line_number=node.lineno,
                dependencies=list(set(dependencies)),
                interfaces=interfaces,
                is_abstract=is_abstract,
                coupling_score=coupling_score,
                cohesion_score=cohesion_score,
                complexity_score=complexity_score,
                patterns=patterns,
            )
        except Exception as e:
            logger.error(f"Error analyzing class {node.name}: {e}")
            return None

    def _analyze_function_component(
        self, node: ast.FunctionDef, file_path: str, content: str
    ) -> Optional[ArchitecturalComponent]:
        """Analyze a function as an architectural component."""
        try:
            # Extract dependencies
            dependencies = self._deps.extract_function_dependencies(node, content)

            return ArchitecturalComponent(
                file_path=file_path,
                component_type="function",
                name=node.name,
                line_number=node.lineno,
                dependencies=list(set(dependencies)),
                interfaces=[node.name],
                is_abstract=False,
                coupling_score=len(dependencies),
                cohesion_score=1.0,
                complexity_score=self._complexity.calculate_function_complexity(node),
                patterns=[],
            )
        except Exception as e:
            logger.error(f"Error analyzing function {node.name}: {e}")
            return None

    def _analyze_module_component(
        self, file_path: str, tree: ast.AST, content: str
    ) -> Optional[ArchitecturalComponent]:
        """Analyze a module as an architectural component."""
        try:
            module_name = Path(file_path).stem
            dependencies = self._deps.extract_module_dependencies(tree)
            interfaces = self._deps.extract_public_interfaces(tree)

            return ArchitecturalComponent(
                file_path=file_path,
                component_type="module",
                name=module_name,
                line_number=1,
                dependencies=list(set(dependencies)),
                interfaces=interfaces,
                is_abstract=False,
                coupling_score=len(set(dependencies)),
                cohesion_score=self._cohesion.calculate_module_cohesion(tree),
                complexity_score=len(interfaces),
                patterns=[],
            )
        except Exception as e:
            logger.error(f"Error analyzing module {file_path}: {e}")
            return None

    def _is_method(self, node: ast.FunctionDef, tree: ast.AST) -> bool:
        """Check if a function is a method (inside a class)."""
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                if node in parent.body:
                    return True
        return False

    def _is_abstract_class(self, node: ast.ClassDef) -> bool:
        """Check if a class is abstract."""
        return self._has_abc_base(node) or self._has_abstract_method(node)

    def _has_abc_base(self, node: ast.ClassDef) -> bool:
        """Check for ABC inheritance."""
        return any(
            isinstance(base, ast.Name) and "ABC" in base.id for base in node.bases
        )

    def _has_abstract_method(self, node: ast.ClassDef) -> bool:
        """Check for abstract methods."""
        for method in node.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            if self._is_abstractmethod_decorated(method):
                return True
        return False

    def _is_abstractmethod_decorated(self, method: ast.FunctionDef) -> bool:
        """Check if method has abstractmethod decorator."""
        return any(
            isinstance(dec, ast.Name) and dec.id == "abstractmethod"
            for dec in method.decorator_list
        )


__all__ = ["ComponentDiscovery"]
