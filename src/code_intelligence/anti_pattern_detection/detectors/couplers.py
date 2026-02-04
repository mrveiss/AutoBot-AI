# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Coupler Anti-Pattern Detectors

Detects "coupler" anti-patterns that indicate excessive coupling:
- Circular Dependency: Modules that import each other
- Feature Envy: Methods that use other class data more than own
- Message Chains: Excessive method chaining (a.b().c().d())
- Inappropriate Intimacy: Classes that know too much about each other

Part of Issue #381 - God Class Refactoring
"""

import ast
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..models import AntiPatternResult
from ..severity_utils import get_feature_envy_severity, get_message_chain_severity
from ..types import AntiPatternSeverity, AntiPatternType, Thresholds

logger = logging.getLogger(__name__)


# Issue #380: Pre-computed excluded objects for feature envy detection
FEATURE_ENVY_EXCLUDED_OBJECTS = frozenset(
    {
        # Standard library modules
        "os",
        "sys",
        "time",
        "datetime",
        "json",
        "re",
        "ast",
        "math",
        "pathlib",
        "logging",
        "typing",
        "collections",
        "functools",
        "itertools",
        "io",
        "tempfile",
        "shutil",
        "glob",
        "fnmatch",
        "subprocess",
        "threading",
        "asyncio",
        "uuid",
        # Common framework/library objects
        "logger",
        "log",
        "request",
        "response",
        "session",
        "app",
        "db",
        "cache",
        "redis",
        "client",
        "conn",
        "connection",
        "cursor",
        "query",
        "model",
        "config",
        "settings",
        "env",
        # Pytest and testing
        "pytest",
        "mock",
        "mocker",
        "fixture",
        "tmp_path",
    }
)

# Pre-computed lowercase version for case-insensitive lookups
_FEATURE_ENVY_EXCLUDED_LOWER = frozenset(
    x.lower() for x in FEATURE_ENVY_EXCLUDED_OBJECTS
)


class CouplerDetector:
    """Detects coupler-type anti-patterns in code."""

    def __init__(
        self,
        message_chain_threshold: int = Thresholds.MESSAGE_CHAIN_THRESHOLD,
        feature_envy_threshold: int = Thresholds.FEATURE_ENVY_EXTERNAL_CALL_THRESHOLD,
    ):
        """
        Initialize coupler detector with configurable thresholds.

        Args:
            message_chain_threshold: Max method chain length before flagging
            feature_envy_threshold: Min external accesses for feature envy
        """
        self.message_chain_threshold = message_chain_threshold
        self.feature_envy_threshold = feature_envy_threshold

        # Import graph for circular dependency detection
        self._import_graph: Dict[str, Set[str]] = {}
        self._module_to_file: Dict[str, str] = {}

    # =========================================================================
    # Circular Dependency Detection
    # =========================================================================

    def collect_imports(self, file_path: str) -> None:
        """
        Collect import statements for circular dependency detection.

        Args:
            file_path: Path to the source file to analyze
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=file_path)
            module_name = self._file_to_module(file_path)

            if module_name not in self._import_graph:
                self._import_graph[module_name] = set()
                self._module_to_file[module_name] = file_path

            self._import_graph[module_name].update(
                self._extract_imports_from_tree(tree)
            )
        except Exception as e:
            logger.debug("Failed to collect imports from %s: %s", file_path, e)

    def _extract_imports_from_tree(self, tree: ast.AST) -> Set[str]:
        """Extract imported module names from AST."""
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        return imports

    def _file_to_module(self, file_path: str) -> str:
        """Convert file path to module name."""
        path = Path(file_path)
        parts = list(path.parts)
        if parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts[-3:]) if len(parts) >= 3 else ".".join(parts)

    def _create_cycle_result(self, cycle: List[str]) -> AntiPatternResult:
        """Create an AntiPatternResult for a detected cycle. Issue #620.

        Args:
            cycle: List of module names forming the cycle

        Returns:
            AntiPatternResult describing the circular dependency
        """
        file_path = self._module_to_file.get(cycle[0], "unknown")
        return AntiPatternResult(
            pattern_type=AntiPatternType.CIRCULAR_DEPENDENCY,
            severity=AntiPatternSeverity.HIGH,
            file_path=file_path,
            line_number=1,
            entity_name=" -> ".join(cycle),
            description=f"Circular dependency detected: {' -> '.join(cycle)}",
            suggestion=(
                "Refactor to break the cycle using "
                "dependency injection, interfaces, or restructuring"
            ),
            metrics={
                "cycle_length": len(cycle),
                "modules": list(cycle),
            },
        )

    def _find_cycle_dfs(
        self,
        module: str,
        path: List[str],
        visited: Set[str],
        rec_stack: Set[str],
    ) -> Optional[List[str]]:
        """Recursively find circular dependency cycle using DFS. Issue #620.

        Args:
            module: Current module being visited
            path: Current path of modules
            visited: Set of all visited modules
            rec_stack: Set of modules in current recursion stack

        Returns:
            List of modules forming a cycle, or None if no cycle found
        """
        visited.add(module)
        rec_stack.add(module)

        for imported in self._import_graph.get(module, []):
            if imported in self._import_graph:
                if imported not in visited:
                    cycle = self._find_cycle_dfs(
                        imported, path + [imported], visited, rec_stack
                    )
                    if cycle:
                        return cycle
                elif imported in rec_stack:
                    cycle_start = path.index(imported) if imported in path else 0
                    return path[cycle_start:] + [imported]

        rec_stack.remove(module)
        return None

    def detect_circular_dependencies(self) -> List[AntiPatternResult]:
        """Detect circular dependencies in the import graph. Issue #620.

        Must call collect_imports() for each file first.

        Returns:
            List of AntiPatternResult for detected circular dependencies
        """
        patterns: List[AntiPatternResult] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles_found: Set[Tuple[str, ...]] = set()

        for module in self._import_graph:
            if module not in visited:
                cycle = self._find_cycle_dfs(module, [module], visited, rec_stack)
                if cycle:
                    cycle_tuple = tuple(sorted(cycle))
                    if cycle_tuple not in cycles_found:
                        cycles_found.add(cycle_tuple)
                        patterns.append(self._create_cycle_result(cycle))

        return patterns

    def reset_import_graph(self) -> None:
        """Clear the import graph for a fresh analysis."""
        self._import_graph.clear()
        self._module_to_file.clear()

    # =========================================================================
    # Feature Envy Detection
    # =========================================================================

    def detect_feature_envy(
        self,
        node: ast.FunctionDef,
        file_path: str,
        class_name: Optional[str] = None,
    ) -> List[AntiPatternResult]:
        """
        Detect feature envy - method uses other class's data more than its own.

        This is a heuristic detection that looks for methods accessing external
        object attributes more frequently than self attributes.

        Args:
            node: AST FunctionDef node to analyze
            file_path: Path to the source file
            class_name: Name of containing class (if any)

        Returns:
            List of AntiPatternResult for detected feature envy
        """
        patterns: List[AntiPatternResult] = []

        self_accesses = 0
        external_accesses: Dict[str, int] = {}

        for child in ast.walk(node):
            if isinstance(child, ast.Attribute):
                if isinstance(child.value, ast.Name):
                    if child.value.id == "self":
                        self_accesses += 1
                    else:
                        obj_name = child.value.id
                        # Skip excluded objects (stdlib, frameworks, params)
                        if obj_name.lower() not in _FEATURE_ENVY_EXCLUDED_LOWER:
                            external_accesses[obj_name] = (
                                external_accesses.get(obj_name, 0) + 1
                            )

        # Check if any external object is accessed more than self
        for obj_name, count in external_accesses.items():
            if count > self_accesses and count >= self.feature_envy_threshold:
                patterns.append(
                    AntiPatternResult(
                        pattern_type=AntiPatternType.FEATURE_ENVY,
                        severity=get_feature_envy_severity(count),
                        file_path=file_path,
                        line_number=node.lineno,
                        entity_name=node.name,
                        description=(
                            f"Method '{node.name}' accesses '{obj_name}' "
                            f"{count} times vs self {self_accesses} times"
                        ),
                        suggestion=(
                            f"Consider moving this method to the '{obj_name}' class"
                        ),
                        metrics={
                            "self_accesses": self_accesses,
                            "external_object": obj_name,
                            "external_accesses": count,
                        },
                    )
                )

        return patterns

    # =========================================================================
    # Message Chain Detection
    # =========================================================================

    def detect_message_chains(
        self,
        node: ast.FunctionDef,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """
        Detect message chains (a.b().c().d() patterns).

        Args:
            node: AST FunctionDef node to analyze
            file_path: Path to the source file

        Returns:
            List of AntiPatternResult for detected message chains
        """
        patterns: List[AntiPatternResult] = []

        for child in ast.walk(node):
            chain_length = self._get_chain_length(child)
            if chain_length >= self.message_chain_threshold:
                patterns.append(
                    AntiPatternResult(
                        pattern_type=AntiPatternType.MESSAGE_CHAINS,
                        severity=get_message_chain_severity(chain_length),
                        file_path=file_path,
                        line_number=getattr(child, "lineno", node.lineno),
                        entity_name=node.name,
                        description=(
                            f"Message chain of length {chain_length} "
                            f"(threshold: {self.message_chain_threshold})"
                        ),
                        suggestion=(
                            "Consider introducing intermediate variables "
                            "or using the Law of Demeter"
                        ),
                        metrics={
                            "chain_length": chain_length,
                            "threshold": self.message_chain_threshold,
                        },
                    )
                )

        return patterns

    def _get_chain_length(self, node: ast.AST, depth: int = 0) -> int:
        """Calculate the length of a method chain."""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                return self._get_chain_length(node.func.value, depth + 1)
        elif isinstance(node, ast.Attribute):
            return self._get_chain_length(node.value, depth + 1)
        return depth
