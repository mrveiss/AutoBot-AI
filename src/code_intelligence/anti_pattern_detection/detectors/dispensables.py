# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dispensable Anti-Pattern Detectors

Detects "dispensable" anti-patterns indicating unnecessary code:
- Dead Code: Unreachable code, empty except blocks
- Lazy Class: Classes that do too little
- Duplicate Abstraction: Similar classes or functions
- Speculative Generality: Unused abstractions

Part of Issue #381 - God Class Refactoring
"""

import ast
from typing import List, Optional

from ..models import AntiPatternResult
from ..severity_utils import get_lazy_class_severity
from ..types import AntiPatternSeverity, AntiPatternType, Thresholds

# AST node types for function definitions
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)

# AST node types that exit a function
_EXIT_STMT_TYPES = (ast.Return, ast.Raise)


class DispensableDetector:
    """Detects dispensable-type anti-patterns in code."""

    def __init__(
        self,
        lazy_class_method_threshold: int = Thresholds.LAZY_CLASS_METHOD_THRESHOLD,
        lazy_class_line_threshold: int = Thresholds.LAZY_CLASS_LINE_THRESHOLD,
    ):
        """
        Initialize dispensable detector with configurable thresholds.

        Args:
            lazy_class_method_threshold: Max methods for lazy class
            lazy_class_line_threshold: Max lines for lazy class
        """
        self.lazy_class_method_threshold = lazy_class_method_threshold
        self.lazy_class_line_threshold = lazy_class_line_threshold

    # =========================================================================
    # Dead Code Detection
    # =========================================================================

    def detect_dead_code(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect potential dead code patterns.

        Looks for:
        - Unreachable code after return/raise/break/continue
        - Empty except blocks
        - Pass statements in non-empty blocks

        Args:
            tree: AST tree to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for detected dead code
        """
        patterns: List[AntiPatternResult] = []

        for node in ast.walk(tree):
            # Check functions for unreachable code
            if isinstance(node, _FUNCTION_DEF_TYPES):
                result = self._check_unreachable_after_return(node, file_path)
                if result:
                    patterns.append(result)

            # Check for empty except blocks
            if isinstance(node, ast.ExceptHandler):
                result = self._check_empty_except(node, file_path)
                if result:
                    patterns.append(result)

        return patterns

    def _check_unreachable_after_return(
        self,
        node: ast.AST,
        file_path: str,
    ) -> Optional[AntiPatternResult]:
        """Check for unreachable code after return/raise statements."""
        if not hasattr(node, "body"):
            return None

        for i, stmt in enumerate(node.body[:-1]):
            if not isinstance(stmt, _EXIT_STMT_TYPES):
                continue

            next_stmt = node.body[i + 1]
            if self._is_docstring_or_pass(next_stmt):
                continue

            return AntiPatternResult(
                pattern_type=AntiPatternType.DEAD_CODE,
                severity=AntiPatternSeverity.MEDIUM,
                file_path=file_path,
                line_number=getattr(next_stmt, "lineno", node.lineno),
                entity_name=getattr(node, "name", "unknown"),
                description="Unreachable code after return/raise",
                suggestion="Remove unreachable statements",
                metrics={"type": "unreachable_after_return"},
            )
        return None

    def _check_empty_except(
        self,
        node: ast.ExceptHandler,
        file_path: str,
    ) -> Optional[AntiPatternResult]:
        """Check for empty except blocks."""
        if len(node.body) != 1 or not isinstance(node.body[0], ast.Pass):
            return None

        return AntiPatternResult(
            pattern_type=AntiPatternType.DEAD_CODE,
            severity=AntiPatternSeverity.MEDIUM,
            file_path=file_path,
            line_number=node.lineno,
            entity_name="except_handler",
            description="Empty except block silently ignores errors",
            suggestion="Log the exception or handle it explicitly",
            metrics={"type": "empty_except"},
        )

    def _is_docstring_or_pass(self, stmt: ast.stmt) -> bool:
        """Check if statement is pass or docstring."""
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            return True
        return False

    # =========================================================================
    # Lazy Class Detection
    # =========================================================================

    def detect_lazy_class(
        self,
        node: ast.ClassDef,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect classes that do too little (lazy classes).

        Args:
            node: AST ClassDef node to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for detected lazy classes
        """
        patterns: List[AntiPatternResult] = []

        # Count methods (excluding __init__ and dunder methods)
        methods = [
            n
            for n in node.body
            if isinstance(n, _FUNCTION_DEF_TYPES)
            and not (n.name.startswith("__") and n.name.endswith("__"))
        ]

        # Count attributes
        attributes = [
            n for n in node.body if isinstance(n, (ast.Assign, ast.AnnAssign))
        ]

        total_members = len(methods) + len(attributes)

        if total_members <= self.lazy_class_method_threshold and len(methods) <= 1:
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.LAZY_CLASS,
                    severity=get_lazy_class_severity(len(methods), total_members),
                    file_path=file_path,
                    line_number=node.lineno,
                    entity_name=node.name,
                    description=(
                        f"Class '{node.name}' has only {len(methods)} methods "
                        f"and {len(attributes)} attributes"
                    ),
                    suggestion=(
                        "Consider inlining into calling code or using a "
                        "function/data structure instead"
                    ),
                    metrics={
                        "method_count": len(methods),
                        "attribute_count": len(attributes),
                    },
                )
            )

        return patterns

    # =========================================================================
    # Unused Import Detection (Simple Heuristic)
    # =========================================================================

    def _collect_imported_names(self, tree: ast.AST) -> dict[str, int]:
        """
        Collect all imported names from an AST tree.

        Issue #665: Extracted from detect_unused_imports to reduce complexity.

        Args:
            tree: AST tree to analyze

        Returns:
            Dictionary mapping imported names to their line numbers
        """
        imported_names: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    imported_names[name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name != "*":
                        imported_names[name] = node.lineno
        return imported_names

    def _extract_root_name(self, node: ast.Attribute) -> str | None:
        """
        Extract root name from an attribute chain (e.g., 'os' from 'os.path.join').

        Issue #665: Extracted from detect_unused_imports to reduce complexity.

        Args:
            node: AST Attribute node

        Returns:
            Root name string or None if not a Name node at root
        """
        current = node.value
        while isinstance(current, ast.Attribute):
            current = current.value
        if isinstance(current, ast.Name):
            return current.id
        return None

    def _collect_used_names(self, tree: ast.AST) -> set[str]:
        """
        Collect all names used in an AST tree.

        Issue #665: Extracted from detect_unused_imports to reduce complexity.

        Args:
            tree: AST tree to analyze

        Returns:
            Set of used name strings
        """
        used_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                root_name = self._extract_root_name(node)
                if root_name:
                    used_names.add(root_name)
        return used_names

    def detect_unused_imports(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect potentially unused imports (simple heuristic).

        Issue #665: Refactored to use extracted helpers for collection logic.

        Note: This is a simple heuristic that may have false positives.
        For more accurate detection, use specialized tools like flake8.

        Args:
            tree: AST tree to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for potentially unused imports
        """
        patterns: List[AntiPatternResult] = []

        # Collect imports and used names (Issue #665: use helpers)
        imported_names = self._collect_imported_names(tree)
        used_names = self._collect_used_names(tree)

        # Find potentially unused imports
        for name, line in imported_names.items():
            if name not in used_names and not name.startswith("_"):
                patterns.append(
                    AntiPatternResult(
                        pattern_type=AntiPatternType.DEAD_CODE,
                        severity=AntiPatternSeverity.INFO,
                        file_path=file_path,
                        line_number=line,
                        entity_name=name,
                        description=f"Import '{name}' appears to be unused",
                        suggestion="Remove unused import or use it",
                        metrics={"type": "unused_import", "name": name},
                    )
                )

        return patterns

    # =========================================================================
    # Duplicate Abstraction Detection (Simple)
    # =========================================================================

    def detect_duplicate_classes(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect classes with very similar structure (potential duplicates).

        This is a simple heuristic based on method names.
        Issue #620: Refactored to extract helper methods.

        Args:
            tree: AST tree to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for potential duplicate classes
        """
        patterns: List[AntiPatternResult] = []
        class_signatures: dict[str, tuple[frozenset, int]] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = self._extract_class_method_signature(node)

                if len(methods) >= 3:  # Only consider classes with 3+ methods
                    for existing_name, (
                        existing_methods,
                        _,
                    ) in class_signatures.items():
                        result = self._check_class_overlap(
                            node, methods, existing_name, existing_methods, file_path
                        )
                        if result:
                            patterns.append(result)

                    class_signatures[node.name] = (methods, node.lineno)

        return patterns

    def _extract_class_method_signature(self, node: ast.ClassDef) -> frozenset:
        """
        Extract method names signature from a class definition.

        Issue #620: Extracted from detect_duplicate_classes. Issue #620.

        Args:
            node: AST ClassDef node to extract methods from

        Returns:
            Frozenset of non-dunder method names
        """
        return frozenset(
            n.name
            for n in node.body
            if isinstance(n, _FUNCTION_DEF_TYPES)
            and not (n.name.startswith("__") and n.name.endswith("__"))
        )

    def _check_class_overlap(
        self,
        node: ast.ClassDef,
        methods: frozenset,
        existing_name: str,
        existing_methods: frozenset,
        file_path: str,
    ) -> Optional[AntiPatternResult]:
        """
        Check if two classes have significant method overlap indicating duplication.

        Issue #620: Extracted from detect_duplicate_classes. Issue #620.

        Args:
            node: Current class AST node
            methods: Method names of current class
            existing_name: Name of class to compare against
            existing_methods: Method names of existing class
            file_path: Path to source file

        Returns:
            AntiPatternResult if overlap exceeds 80%, None otherwise
        """
        overlap = methods & existing_methods
        union = methods | existing_methods
        if not union or len(overlap) / len(union) <= 0.8:
            return None

        return AntiPatternResult(
            pattern_type=AntiPatternType.DUPLICATE_ABSTRACTION,
            severity=AntiPatternSeverity.MEDIUM,
            file_path=file_path,
            line_number=node.lineno,
            entity_name=f"{node.name}, {existing_name}",
            description=(
                f"Classes '{node.name}' and '{existing_name}' "
                f"have {len(overlap)}/{len(union)} overlapping methods"
            ),
            suggestion=(
                "Consider extracting common functionality "
                "into a base class or shared module"
            ),
            metrics={
                "overlap_count": len(overlap),
                "overlap_methods": list(overlap)[:5],
                "similarity": round(len(overlap) / len(union), 2),
            },
        )
