# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Analyzer

Main entry point for anti-pattern detection. Coordinates all detector
modules and provides a unified analysis interface.

Part of Issue #381 - God Class Refactoring
"""

import ast
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .detectors import (
    BloaterDetector,
    CouplerDetector,
    DispensableDetector,
    NamingDetector,
)
from .models import AnalysisReport, AntiPatternResult
from .types import (
    AntiPatternSeverity,
    AntiPatternType,
    DEFAULT_IGNORE_PATTERNS,
    Thresholds,
)

logger = logging.getLogger(__name__)


class AntiPatternDetector:
    """
    Detects code anti-patterns and smells in Python code.

    Uses AST parsing to analyze code structure and identify common
    anti-patterns that indicate potential code quality issues.

    This class coordinates multiple specialized detectors:
    - BloaterDetector: God class, long method, deep nesting, etc.
    - CouplerDetector: Circular dependencies, feature envy, message chains
    - DispensableDetector: Dead code, lazy class
    - NamingDetector: Naming issues, magic numbers, complex conditionals
    """

    # Expose thresholds as class attributes for backward compatibility
    GOD_CLASS_METHOD_THRESHOLD = Thresholds.GOD_CLASS_METHOD_THRESHOLD
    GOD_CLASS_LINE_THRESHOLD = Thresholds.GOD_CLASS_LINE_THRESHOLD
    LONG_PARAMETER_THRESHOLD = Thresholds.LONG_PARAMETER_THRESHOLD
    LARGE_FILE_THRESHOLD = Thresholds.LARGE_FILE_THRESHOLD
    DEEP_NESTING_THRESHOLD = Thresholds.DEEP_NESTING_THRESHOLD
    LONG_METHOD_THRESHOLD = Thresholds.LONG_METHOD_THRESHOLD
    MESSAGE_CHAIN_THRESHOLD = Thresholds.MESSAGE_CHAIN_THRESHOLD
    LAZY_CLASS_METHOD_THRESHOLD = Thresholds.LAZY_CLASS_METHOD_THRESHOLD

    def __init__(
        self,
        exclude_dirs: Optional[List[str]] = None,
        detect_circular: bool = True,
        detect_naming: bool = True,
    ):
        """
        Initialize anti-pattern detector.

        Args:
            exclude_dirs: Directories to exclude from analysis
            detect_circular: Whether to detect circular dependencies
            detect_naming: Whether to detect naming issues
        """
        self.exclude_dirs = exclude_dirs or DEFAULT_IGNORE_PATTERNS
        self.detect_circular = detect_circular
        self.detect_naming = detect_naming

        # Initialize specialized detectors
        self._bloater = BloaterDetector()
        self._coupler = CouplerDetector()
        self._dispensable = DispensableDetector()
        self._naming = NamingDetector()

        # State tracking
        self._total_classes = 0
        self._total_functions = 0

    def analyze_directory(self, directory: str) -> AnalysisReport:
        """
        Analyze a directory for anti-patterns.

        Args:
            directory: Path to directory to analyze

        Returns:
            AnalysisReport with all detected anti-patterns
        """
        patterns: List[AntiPatternResult] = []
        self._total_classes = 0
        self._total_functions = 0

        python_files = self._get_python_files(directory)

        # Reset coupler detector's import graph
        self._coupler.reset_import_graph()

        for file_path in python_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    source = f.read()
                    lines = source.split("\n")

                # Check for large file
                result = self._bloater.check_large_file(file_path, len(lines))
                if result:
                    patterns.append(result)

                tree = ast.parse(source, filename=file_path)

                # Collect imports for circular dependency detection
                if self.detect_circular:
                    self._coupler.collect_imports(file_path)

                # Analyze all nodes
                patterns.extend(self._analyze_ast_nodes(tree, file_path, lines))

                # File-level detections
                patterns.extend(self._run_file_level_detections(tree, file_path))

            except SyntaxError as e:
                logger.debug(f"Syntax error in {file_path}: {e}")
            except Exception as e:
                logger.debug(f"Error analyzing {file_path}: {e}")

        # Detect circular dependencies across all files
        if self.detect_circular:
            patterns.extend(self._coupler.detect_circular_dependencies())

        return AnalysisReport(
            scan_path=directory,
            total_files=len(python_files),
            total_classes=self._total_classes,
            total_functions=self._total_functions,
            anti_patterns=patterns,
            summary=self._calculate_summary(patterns),
            severity_distribution=self._calculate_severity_distribution(patterns),
        )

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze a single file for anti-patterns.

        Args:
            file_path: Path to the file to analyze

        Returns:
            Dictionary with analysis results
        """
        patterns: List[AntiPatternResult] = []
        classes = 0
        functions = 0

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
                lines = source.split("\n")

            # Check for large file
            result = self._bloater.check_large_file(file_path, len(lines))
            if result:
                patterns.append(result)

            tree = ast.parse(source, filename=file_path)

            # Count and analyze classes/functions
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes += 1
                    patterns.extend(self._analyze_class(node, file_path, lines))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Only count module-level functions
                    parent_is_class = any(
                        isinstance(p, ast.ClassDef)
                        for p in ast.walk(tree)
                        if node in getattr(p, "body", [])
                    )
                    if not parent_is_class:
                        functions += 1
                        patterns.extend(self._analyze_function(node, file_path, lines))

            # File-level detections
            patterns.extend(self._run_file_level_detections(tree, file_path))

        except SyntaxError as e:
            logger.debug(f"Syntax error in {file_path}: {e}")
        except Exception as e:
            logger.debug(f"Error analyzing {file_path}: {e}")

        return {
            "file_path": file_path,
            "lines": len(lines) if "lines" in dir() else 0,
            "classes": classes,
            "functions": functions,
            "anti_patterns": [p.to_dict() for p in patterns],
            "summary": self._calculate_summary(patterns),
        }

    def _analyze_ast_nodes(
        self,
        tree: ast.AST,
        file_path: str,
        lines: List[str],
    ) -> List[AntiPatternResult]:
        """Analyze all AST nodes for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self._total_classes += 1
                patterns.extend(self._analyze_class(node, file_path, lines))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._total_functions += 1
                # Module-level functions analyzed separately
                # Class methods are analyzed within _analyze_class

        return patterns

    def _analyze_class(
        self,
        node: ast.ClassDef,
        file_path: str,
        lines: List[str],
    ) -> List[AntiPatternResult]:
        """Analyze a class for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        methods = self._bloater.get_class_methods(node)
        method_count = len(methods)
        class_lines = self._bloater.calculate_class_size(node)

        # God class detection
        god_class_result = self._bloater.check_god_class(
            node, file_path, method_count, class_lines
        )
        if god_class_result:
            patterns.append(god_class_result)

        # Lazy class detection
        patterns.extend(self._dispensable.detect_lazy_class(node, file_path))

        # Naming issues in class
        if self.detect_naming:
            patterns.extend(self._naming.detect_naming_issues(node, file_path))

        # Analyze each method
        for method in methods:
            patterns.extend(self._analyze_function(method, file_path, lines))

        return patterns

    def _analyze_function(
        self,
        node: ast.FunctionDef,
        file_path: str,
        lines: List[str],
    ) -> List[AntiPatternResult]:
        """Analyze a function/method for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        # Bloater detections
        param_count = self._bloater.count_function_params(node)
        result = self._bloater.check_long_parameter_list(node, file_path, param_count)
        if result:
            patterns.append(result)

        result = self._bloater.check_long_method(node, file_path)
        if result:
            patterns.append(result)

        result = self._bloater.check_deep_nesting(node, file_path)
        if result:
            patterns.append(result)

        # Coupler detections
        patterns.extend(self._coupler.detect_message_chains(node, file_path))
        patterns.extend(self._coupler.detect_feature_envy(node, file_path))

        # Naming detections
        if self.detect_naming:
            patterns.extend(self._naming.detect_complex_conditionals(node, file_path))
            patterns.extend(self._naming.detect_single_letter_vars(node, file_path))

        return patterns

    def _run_file_level_detections(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> List[AntiPatternResult]:
        """Run file-level detections."""
        patterns: List[AntiPatternResult] = []

        # Dead code detection
        patterns.extend(self._dispensable.detect_dead_code(tree, file_path))

        # Missing docstrings
        if self.detect_naming:
            patterns.extend(self._naming.detect_missing_docstrings(tree, file_path))
            patterns.extend(self._naming.detect_magic_numbers(tree, file_path))

        # Data clumps
        patterns.extend(self._bloater.detect_data_clumps(tree, file_path))

        return patterns

    def _get_python_files(self, directory: str) -> List[str]:
        """Get all Python files in directory, excluding specified patterns."""
        python_files = []
        dir_path = Path(directory)

        for py_file in dir_path.rglob("*.py"):
            should_exclude = False
            for exclude_dir in self.exclude_dirs:
                if exclude_dir in py_file.parts:
                    should_exclude = True
                    break

            if not should_exclude:
                python_files.append(str(py_file))

        return sorted(python_files)

    def _calculate_summary(
        self,
        patterns: List[AntiPatternResult],
    ) -> Dict[str, int]:
        """Calculate summary of anti-patterns by type."""
        summary: Dict[str, int] = {}
        for pattern in patterns:
            key = pattern.pattern_type.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    def _calculate_severity_distribution(
        self,
        patterns: List[AntiPatternResult],
    ) -> Dict[str, int]:
        """Calculate distribution of patterns by severity."""
        dist: Dict[str, int] = {}
        for pattern in patterns:
            key = pattern.severity.value
            dist[key] = dist.get(key, 0) + 1
        return dist


def analyze_codebase(
    directory: str,
    exclude_dirs: Optional[List[str]] = None,
    detect_circular: bool = True,
    detect_naming: bool = True,
) -> AnalysisReport:
    """
    Convenience function to analyze a codebase for anti-patterns.

    Args:
        directory: Path to directory to analyze
        exclude_dirs: Directories to exclude from analysis
        detect_circular: Whether to detect circular dependencies
        detect_naming: Whether to detect naming issues

    Returns:
        AnalysisReport with all detected anti-patterns
    """
    detector = AntiPatternDetector(
        exclude_dirs=exclude_dirs,
        detect_circular=detect_circular,
        detect_naming=detect_naming,
    )
    return detector.analyze_directory(directory)
