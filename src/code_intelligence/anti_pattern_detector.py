# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Detection System

Identifies code anti-patterns and smells including:
- God classes (>20 methods)
- Feature envy
- Circular dependencies
- Long parameter lists
- Dead code
- Duplicate abstraction

Part of Issue #221 - Anti-Pattern Detection System
Parent Epic: #217 - Advanced Code Intelligence
"""

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class AntiPatternSeverity(Enum):
    """Severity levels for anti-patterns."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AntiPatternType(Enum):
    """Types of anti-patterns detected."""

    # Bloaters
    GOD_CLASS = "god_class"
    LONG_METHOD = "long_method"
    LONG_PARAMETER_LIST = "long_parameter_list"
    LARGE_FILE = "large_file"
    DEEP_NESTING = "deep_nesting"
    DATA_CLUMPS = "data_clumps"

    # Couplers
    CIRCULAR_DEPENDENCY = "circular_dependency"
    FEATURE_ENVY = "feature_envy"
    MESSAGE_CHAINS = "message_chains"
    INAPPROPRIATE_INTIMACY = "inappropriate_intimacy"

    # Dispensables
    DEAD_CODE = "dead_code"
    DUPLICATE_ABSTRACTION = "duplicate_abstraction"
    LAZY_CLASS = "lazy_class"
    SPECULATIVE_GENERALITY = "speculative_generality"

    # Naming Issues
    INCONSISTENT_NAMING = "inconsistent_naming"
    SINGLE_LETTER_VARIABLE = "single_letter_variable"
    MAGIC_NUMBER = "magic_number"

    # Other
    COMPLEX_CONDITIONAL = "complex_conditional"
    MISSING_DOCSTRING = "missing_docstring"


@dataclass
class AntiPatternResult:
    """Result of anti-pattern detection for a single finding."""

    pattern_type: AntiPatternType
    severity: AntiPatternSeverity
    file_path: str
    line_number: int
    entity_name: str
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
            "entity_name": self.entity_name,
            "description": self.description,
            "suggestion": self.suggestion,
            "metrics": self.metrics,
        }


@dataclass
class AnalysisReport:
    """Complete analysis report for a codebase scan."""

    scan_path: str
    total_files: int
    total_classes: int
    total_functions: int
    anti_patterns: List[AntiPatternResult]
    summary: Dict[str, int]
    severity_distribution: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scan_path": self.scan_path,
            "total_files": self.total_files,
            "total_classes": self.total_classes,
            "total_functions": self.total_functions,
            "anti_patterns": [p.to_dict() for p in self.anti_patterns],
            "summary": self.summary,
            "severity_distribution": self.severity_distribution,
            "total_issues": len(self.anti_patterns),
        }


class AntiPatternDetector:
    """
    Detects code anti-patterns and smells in Python code.

    Uses AST parsing to analyze code structure and identify common
    anti-patterns that indicate potential code quality issues.
    """

    # Thresholds for detection
    GOD_CLASS_METHOD_THRESHOLD = 20
    GOD_CLASS_LINE_THRESHOLD = 500
    LONG_PARAMETER_THRESHOLD = 5
    LARGE_FILE_THRESHOLD = 1000
    DEEP_NESTING_THRESHOLD = 4
    LONG_METHOD_THRESHOLD = 50
    MESSAGE_CHAIN_THRESHOLD = 4  # a.b().c().d() = 4 chains
    COMPLEX_CONDITIONAL_THRESHOLD = 3  # Max conditions in single expression
    LAZY_CLASS_METHOD_THRESHOLD = 2  # Classes with 2 or fewer methods
    MAGIC_NUMBER_THRESHOLD = 5  # Same number appearing 5+ times

    def __init__(
        self,
        exclude_dirs: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ):
        """
        Initialize the anti-pattern detector.

        Args:
            exclude_dirs: Directories to exclude from analysis
            exclude_patterns: File patterns to exclude
        """
        self.exclude_dirs = exclude_dirs or [
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".git",
            "archives",
            "archive",
            ".mypy_cache",
        ]
        self.exclude_patterns = exclude_patterns or ["test_*.py", "*_test.py"]

        # Track imports for circular dependency detection
        self._import_graph: Dict[str, Set[str]] = {}
        self._module_to_file: Dict[str, str] = {}

    def analyze_directory(self, directory: str) -> AnalysisReport:
        """
        Analyze all Python files in a directory for anti-patterns.

        Args:
            directory: Path to the directory to analyze

        Returns:
            AnalysisReport containing all findings
        """
        logger.info(f"Starting anti-pattern analysis of: {directory}")

        all_patterns: List[AntiPatternResult] = []
        total_files = 0
        total_classes = 0
        total_functions = 0

        # Reset import graph for circular dependency detection
        self._import_graph = {}
        self._module_to_file = {}

        # First pass: collect all imports
        for py_file in self._get_python_files(directory):
            self._collect_imports(py_file)

        # Second pass: analyze each file
        for py_file in self._get_python_files(directory):
            try:
                results = self.analyze_file(py_file)
                all_patterns.extend(results["patterns"])
                total_files += 1
                total_classes += results["class_count"]
                total_functions += results["function_count"]
            except Exception as e:
                logger.warning(f"Failed to analyze {py_file}: {e}")

        # Detect circular dependencies
        circular_deps = self._detect_circular_dependencies()
        all_patterns.extend(circular_deps)

        # Calculate summary
        summary = self._calculate_summary(all_patterns)
        severity_dist = self._calculate_severity_distribution(all_patterns)

        report = AnalysisReport(
            scan_path=directory,
            total_files=total_files,
            total_classes=total_classes,
            total_functions=total_functions,
            anti_patterns=all_patterns,
            summary=summary,
            severity_distribution=severity_dist,
        )

        logger.info(
            f"Analysis complete: {len(all_patterns)} anti-patterns found "
            f"in {total_files} files"
        )

        return report

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze a single Python file for anti-patterns.

        Args:
            file_path: Path to the Python file

        Returns:
            Dictionary with patterns found and file statistics
        """
        patterns: List[AntiPatternResult] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=file_path)
            lines = source.split("\n")
            line_count = len(lines)

            # Check for large file
            if line_count > self.LARGE_FILE_THRESHOLD:
                patterns.append(
                    AntiPatternResult(
                        pattern_type=AntiPatternType.LARGE_FILE,
                        severity=self._get_large_file_severity(line_count),
                        file_path=file_path,
                        line_number=1,
                        entity_name=os.path.basename(file_path),
                        description=f"File has {line_count} lines, "
                        f"exceeds threshold of {self.LARGE_FILE_THRESHOLD}",
                        suggestion="Consider splitting into smaller, focused modules",
                        metrics={"line_count": line_count},
                    )
                )

            # File-level detections
            patterns.extend(self._detect_naming_issues(tree, file_path))
            patterns.extend(self._detect_magic_numbers(tree, file_path))
            patterns.extend(self._detect_missing_docstrings(tree, file_path))
            patterns.extend(self._detect_data_clumps(file_path, tree))
            patterns.extend(self._detect_dead_code(tree, file_path))

            # Analyze classes and functions
            class_count = 0
            function_count = 0

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_count += 1
                    class_patterns = self._analyze_class(node, file_path, lines)
                    patterns.extend(class_patterns)
                    # Lazy class detection
                    patterns.extend(self._detect_lazy_class(node, file_path))

                elif isinstance(node, ast.FunctionDef) or isinstance(
                    node, ast.AsyncFunctionDef
                ):
                    function_count += 1
                    func_patterns = self._analyze_function(node, file_path, lines)
                    patterns.extend(func_patterns)

            return {
                "patterns": patterns,
                "class_count": class_count,
                "function_count": function_count,
                "line_count": line_count,
            }

        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return {"patterns": [], "class_count": 0, "function_count": 0}
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            return {"patterns": [], "class_count": 0, "function_count": 0}

    def _analyze_class(
        self, node: ast.ClassDef, file_path: str, lines: List[str]
    ) -> List[AntiPatternResult]:
        """Analyze a class for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        # Count methods
        methods = [
            n
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        method_count = len(methods)

        # Calculate class size
        class_start = node.lineno
        class_end = max(
            (getattr(n, "end_lineno", class_start) for n in ast.walk(node)),
            default=class_start,
        )
        class_lines = class_end - class_start + 1

        # God class detection
        if method_count > self.GOD_CLASS_METHOD_THRESHOLD:
            severity = self._get_god_class_severity(method_count)
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.GOD_CLASS,
                    severity=severity,
                    file_path=file_path,
                    line_number=node.lineno,
                    entity_name=node.name,
                    description=f"Class '{node.name}' has {method_count} methods, "
                    f"exceeds threshold of {self.GOD_CLASS_METHOD_THRESHOLD}",
                    suggestion="Consider breaking into smaller, focused classes "
                    "using composition or inheritance",
                    metrics={
                        "method_count": method_count,
                        "line_count": class_lines,
                        "threshold": self.GOD_CLASS_METHOD_THRESHOLD,
                    },
                )
            )

        # Also check by line count
        elif class_lines > self.GOD_CLASS_LINE_THRESHOLD:
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.GOD_CLASS,
                    severity=AntiPatternSeverity.MEDIUM,
                    file_path=file_path,
                    line_number=node.lineno,
                    entity_name=node.name,
                    description=f"Class '{node.name}' has {class_lines} lines, "
                    f"exceeds threshold of {self.GOD_CLASS_LINE_THRESHOLD}",
                    suggestion="Consider extracting methods or splitting "
                    "responsibilities",
                    metrics={
                        "method_count": method_count,
                        "line_count": class_lines,
                    },
                )
            )

        # Analyze each method for anti-patterns
        for method in methods:
            method_patterns = self._analyze_function(method, file_path, lines)
            patterns.extend(method_patterns)

        return patterns

    def _analyze_function(
        self, node: ast.FunctionDef, file_path: str, lines: List[str]
    ) -> List[AntiPatternResult]:
        """Analyze a function/method for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        # Long parameter list detection
        param_count = len(node.args.args) + len(node.args.kwonlyargs)
        if node.args.vararg:
            param_count += 1
        if node.args.kwarg:
            param_count += 1

        if param_count > self.LONG_PARAMETER_THRESHOLD:
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.LONG_PARAMETER_LIST,
                    severity=self._get_param_severity(param_count),
                    file_path=file_path,
                    line_number=node.lineno,
                    entity_name=node.name,
                    description=f"Function '{node.name}' has {param_count} parameters, "
                    f"exceeds threshold of {self.LONG_PARAMETER_THRESHOLD}",
                    suggestion="Consider using a configuration object or "
                    "dataclass to group related parameters",
                    metrics={
                        "param_count": param_count,
                        "threshold": self.LONG_PARAMETER_THRESHOLD,
                    },
                )
            )

        # Function length detection
        func_start = node.lineno
        func_end = getattr(node, "end_lineno", func_start)
        func_lines = func_end - func_start + 1

        if func_lines > self.LONG_METHOD_THRESHOLD:
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.LONG_METHOD,
                    severity=self._get_long_method_severity(func_lines),
                    file_path=file_path,
                    line_number=node.lineno,
                    entity_name=node.name,
                    description=f"Function '{node.name}' has {func_lines} lines, "
                    f"exceeds threshold of {self.LONG_METHOD_THRESHOLD}",
                    suggestion="Consider extracting smaller, focused functions",
                    metrics={
                        "line_count": func_lines,
                        "threshold": self.LONG_METHOD_THRESHOLD,
                    },
                )
            )

        # Deep nesting detection
        max_depth = self._calculate_nesting_depth(node)
        if max_depth > self.DEEP_NESTING_THRESHOLD:
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.DEEP_NESTING,
                    severity=self._get_nesting_severity(max_depth),
                    file_path=file_path,
                    line_number=node.lineno,
                    entity_name=node.name,
                    description=f"Function '{node.name}' has nesting depth of "
                    f"{max_depth}, exceeds threshold of {self.DEEP_NESTING_THRESHOLD}",
                    suggestion="Consider early returns, guard clauses, or "
                    "extracting nested logic to separate functions",
                    metrics={
                        "nesting_depth": max_depth,
                        "threshold": self.DEEP_NESTING_THRESHOLD,
                    },
                )
            )

        # Message chain detection (a.b().c().d() patterns)
        patterns.extend(self._detect_message_chains(node, file_path))

        # Complex conditional detection
        patterns.extend(self._detect_complex_conditionals(node, file_path))

        # Feature envy detection (method uses other class's data more)
        patterns.extend(self._detect_feature_envy(node, file_path))

        return patterns

    def _collect_imports(self, file_path: str) -> None:
        """Collect import statements for circular dependency detection."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=file_path)
            module_name = self._file_to_module(file_path)

            if module_name not in self._import_graph:
                self._import_graph[module_name] = set()
                self._module_to_file[module_name] = file_path

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._import_graph[module_name].add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self._import_graph[module_name].add(node.module)

        except Exception as e:
            logger.debug(f"Failed to collect imports from {file_path}: {e}")

    def _detect_circular_dependencies(self) -> List[AntiPatternResult]:
        """Detect circular dependencies in the import graph."""
        patterns: List[AntiPatternResult] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles_found: Set[Tuple[str, ...]] = set()

        def find_cycle(module: str, path: List[str]) -> Optional[List[str]]:
            visited.add(module)
            rec_stack.add(module)

            for imported in self._import_graph.get(module, []):
                if imported in self._import_graph:
                    if imported not in visited:
                        cycle = find_cycle(imported, path + [imported])
                        if cycle:
                            return cycle
                    elif imported in rec_stack:
                        # Found cycle
                        cycle_start = path.index(imported) if imported in path else 0
                        return path[cycle_start:] + [imported]

            rec_stack.remove(module)
            return None

        for module in self._import_graph:
            if module not in visited:
                cycle = find_cycle(module, [module])
                if cycle:
                    cycle_tuple = tuple(sorted(cycle))
                    if cycle_tuple not in cycles_found:
                        cycles_found.add(cycle_tuple)
                        file_path = self._module_to_file.get(
                            cycle[0], "unknown"
                        )
                        patterns.append(
                            AntiPatternResult(
                                pattern_type=AntiPatternType.CIRCULAR_DEPENDENCY,
                                severity=AntiPatternSeverity.HIGH,
                                file_path=file_path,
                                line_number=1,
                                entity_name=" -> ".join(cycle),
                                description=f"Circular dependency detected: "
                                f"{' -> '.join(cycle)}",
                                suggestion="Refactor to break the cycle using "
                                "dependency injection, interfaces, or restructuring",
                                metrics={
                                    "cycle_length": len(cycle),
                                    "modules": list(cycle),
                                },
                            )
                        )

        return patterns

    def _calculate_nesting_depth(self, node: ast.AST, depth: int = 0) -> int:
        """Calculate maximum nesting depth of a function."""
        max_depth = depth

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
                child_depth = self._calculate_nesting_depth(child, depth + 1)
                max_depth = max(max_depth, child_depth)
            else:
                child_depth = self._calculate_nesting_depth(child, depth)
                max_depth = max(max_depth, child_depth)

        return max_depth

    def _get_python_files(self, directory: str) -> List[str]:
        """Get all Python files in directory, excluding specified patterns."""
        python_files = []
        dir_path = Path(directory)

        for py_file in dir_path.rglob("*.py"):
            # Check if in excluded directory
            should_exclude = False
            for exclude_dir in self.exclude_dirs:
                if exclude_dir in py_file.parts:
                    should_exclude = True
                    break

            if not should_exclude:
                python_files.append(str(py_file))

        return sorted(python_files)

    def _file_to_module(self, file_path: str) -> str:
        """Convert file path to module name."""
        path = Path(file_path)
        # Remove .py extension and convert path separators to dots
        parts = list(path.parts)
        if parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts[-3:]) if len(parts) >= 3 else ".".join(parts)

    def _calculate_summary(
        self, patterns: List[AntiPatternResult]
    ) -> Dict[str, int]:
        """Calculate summary of anti-patterns by type."""
        summary: Dict[str, int] = {}
        for pattern in patterns:
            key = pattern.pattern_type.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    def _calculate_severity_distribution(
        self, patterns: List[AntiPatternResult]
    ) -> Dict[str, int]:
        """Calculate distribution of patterns by severity."""
        dist: Dict[str, int] = {}
        for pattern in patterns:
            key = pattern.severity.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    # Severity calculation methods
    def _get_god_class_severity(self, method_count: int) -> AntiPatternSeverity:
        if method_count > 50:
            return AntiPatternSeverity.CRITICAL
        elif method_count > 35:
            return AntiPatternSeverity.HIGH
        elif method_count > 25:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    def _get_param_severity(self, param_count: int) -> AntiPatternSeverity:
        if param_count > 10:
            return AntiPatternSeverity.HIGH
        elif param_count > 7:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    def _get_large_file_severity(self, line_count: int) -> AntiPatternSeverity:
        if line_count > 3000:
            return AntiPatternSeverity.CRITICAL
        elif line_count > 2000:
            return AntiPatternSeverity.HIGH
        elif line_count > 1500:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    def _get_long_method_severity(self, line_count: int) -> AntiPatternSeverity:
        if line_count > 150:
            return AntiPatternSeverity.HIGH
        elif line_count > 100:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    def _get_nesting_severity(self, depth: int) -> AntiPatternSeverity:
        if depth > 7:
            return AntiPatternSeverity.HIGH
        elif depth > 5:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    # ========== NEW CODE SMELL DETECTIONS ==========

    def _detect_naming_issues(
        self, node: ast.AST, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect naming convention issues."""
        patterns: List[AntiPatternResult] = []

        # Collect all names with their styles
        snake_case_names: List[str] = []
        camel_case_names: List[str] = []
        single_letter_vars: List[Tuple[str, int]] = []

        for child in ast.walk(node):
            # Check function names
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
                if not name.startswith("_"):  # Skip dunder/private
                    if self._is_snake_case(name):
                        snake_case_names.append(name)
                    elif self._is_camel_case(name):
                        camel_case_names.append(name)

            # Check variable assignments for single-letter names
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                name = child.id
                # Allow common loop variables: i, j, k, n, x, y, z
                if len(name) == 1 and name not in "ijknxyz_":
                    single_letter_vars.append((name, getattr(child, "lineno", 0)))

        # Check for mixed naming conventions
        if snake_case_names and camel_case_names:
            # Only flag if significant mixing (>20% of either style)
            total = len(snake_case_names) + len(camel_case_names)
            if min(len(snake_case_names), len(camel_case_names)) / total > 0.2:
                patterns.append(
                    AntiPatternResult(
                        pattern_type=AntiPatternType.INCONSISTENT_NAMING,
                        severity=AntiPatternSeverity.LOW,
                        file_path=file_path,
                        line_number=1,
                        entity_name="mixed_naming",
                        description=f"Mixed naming conventions: {len(snake_case_names)} "
                        f"snake_case, {len(camel_case_names)} camelCase",
                        suggestion="Standardize on snake_case for Python functions/variables",
                        metrics={
                            "snake_case_count": len(snake_case_names),
                            "camel_case_count": len(camel_case_names),
                        },
                    )
                )

        # Flag single-letter variables (except common loop vars)
        for var_name, line_num in single_letter_vars:
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.SINGLE_LETTER_VARIABLE,
                    severity=AntiPatternSeverity.INFO,
                    file_path=file_path,
                    line_number=line_num,
                    entity_name=var_name,
                    description=f"Single-letter variable '{var_name}' reduces readability",
                    suggestion="Use descriptive variable names",
                    metrics={"variable": var_name},
                )
            )

        return patterns

    def _is_snake_case(self, name: str) -> bool:
        """Check if name follows snake_case convention."""
        return bool(re.match(r"^[a-z][a-z0-9_]*$", name))

    def _is_camel_case(self, name: str) -> bool:
        """Check if name follows camelCase convention."""
        return bool(re.match(r"^[a-z][a-zA-Z0-9]*$", name)) and "_" not in name

    def _detect_message_chains(
        self, node: ast.FunctionDef, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect method chaining (a.b().c().d() patterns)."""
        patterns: List[AntiPatternResult] = []

        for child in ast.walk(node):
            chain_length = self._get_chain_length(child)
            if chain_length >= self.MESSAGE_CHAIN_THRESHOLD:
                patterns.append(
                    AntiPatternResult(
                        pattern_type=AntiPatternType.MESSAGE_CHAINS,
                        severity=AntiPatternSeverity.MEDIUM
                        if chain_length > 5
                        else AntiPatternSeverity.LOW,
                        file_path=file_path,
                        line_number=getattr(child, "lineno", node.lineno),
                        entity_name=node.name,
                        description=f"Message chain of length {chain_length} "
                        f"(threshold: {self.MESSAGE_CHAIN_THRESHOLD})",
                        suggestion="Consider introducing intermediate variables "
                        "or using the Law of Demeter",
                        metrics={
                            "chain_length": chain_length,
                            "threshold": self.MESSAGE_CHAIN_THRESHOLD,
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

    def _detect_magic_numbers(
        self, node: ast.AST, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect magic numbers (unexplained numeric literals)."""
        patterns: List[AntiPatternResult] = []
        number_occurrences: Dict[float, List[int]] = {}

        # Exempt common acceptable values
        exempt_values = {0, 1, 2, -1, 10, 100, 1000, 0.0, 1.0, 0.5}

        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(
                child.value, (int, float)
            ):
                value = child.value
                if value not in exempt_values:
                    if value not in number_occurrences:
                        number_occurrences[value] = []
                    number_occurrences[value].append(getattr(child, "lineno", 0))

        # Flag numbers that appear multiple times
        for value, lines in number_occurrences.items():
            if len(lines) >= self.MAGIC_NUMBER_THRESHOLD:
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

    def _detect_complex_conditionals(
        self, node: ast.FunctionDef, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect overly complex conditional expressions."""
        patterns: List[AntiPatternResult] = []

        for child in ast.walk(node):
            if isinstance(child, ast.BoolOp):
                # Count the number of conditions
                condition_count = self._count_conditions(child)
                if condition_count > self.COMPLEX_CONDITIONAL_THRESHOLD:
                    patterns.append(
                        AntiPatternResult(
                            pattern_type=AntiPatternType.COMPLEX_CONDITIONAL,
                            severity=AntiPatternSeverity.MEDIUM
                            if condition_count > 5
                            else AntiPatternSeverity.LOW,
                            file_path=file_path,
                            line_number=getattr(child, "lineno", node.lineno),
                            entity_name=node.name,
                            description=f"Complex conditional with {condition_count} "
                            f"conditions (threshold: {self.COMPLEX_CONDITIONAL_THRESHOLD})",
                            suggestion="Extract conditions to well-named boolean variables "
                            "or use early returns",
                            metrics={
                                "condition_count": condition_count,
                                "threshold": self.COMPLEX_CONDITIONAL_THRESHOLD,
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

    def _detect_missing_docstrings(
        self, node: ast.AST, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect public functions/classes without docstrings."""
        patterns: List[AntiPatternResult] = []

        for child in ast.walk(node):
            # Check functions
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not child.name.startswith("_"):  # Public function
                    if not ast.get_docstring(child):
                        patterns.append(
                            AntiPatternResult(
                                pattern_type=AntiPatternType.MISSING_DOCSTRING,
                                severity=AntiPatternSeverity.INFO,
                                file_path=file_path,
                                line_number=child.lineno,
                                entity_name=child.name,
                                description=f"Public function '{child.name}' lacks docstring",
                                suggestion="Add a docstring explaining purpose and parameters",
                                metrics={"type": "function"},
                            )
                        )

            # Check classes
            elif isinstance(child, ast.ClassDef):
                if not child.name.startswith("_"):  # Public class
                    if not ast.get_docstring(child):
                        patterns.append(
                            AntiPatternResult(
                                pattern_type=AntiPatternType.MISSING_DOCSTRING,
                                severity=AntiPatternSeverity.LOW,
                                file_path=file_path,
                                line_number=child.lineno,
                                entity_name=child.name,
                                description=f"Public class '{child.name}' lacks docstring",
                                suggestion="Add a docstring explaining class purpose",
                                metrics={"type": "class"},
                            )
                        )

        return patterns

    def _detect_lazy_class(
        self, node: ast.ClassDef, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect classes that do too little (lazy classes)."""
        patterns: List[AntiPatternResult] = []

        # Count methods (excluding __init__ and dunder methods)
        methods = [
            n
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not (n.name.startswith("__") and n.name.endswith("__"))
        ]

        # Count attributes
        attributes = [
            n
            for n in node.body
            if isinstance(n, ast.Assign) or isinstance(n, ast.AnnAssign)
        ]

        total_members = len(methods) + len(attributes)

        if total_members <= self.LAZY_CLASS_METHOD_THRESHOLD and len(methods) <= 1:
            patterns.append(
                AntiPatternResult(
                    pattern_type=AntiPatternType.LAZY_CLASS,
                    severity=AntiPatternSeverity.INFO,
                    file_path=file_path,
                    line_number=node.lineno,
                    entity_name=node.name,
                    description=f"Class '{node.name}' has only {len(methods)} methods "
                    f"and {len(attributes)} attributes",
                    suggestion="Consider inlining into calling code or using a "
                    "function/data structure instead",
                    metrics={
                        "method_count": len(methods),
                        "attribute_count": len(attributes),
                    },
                )
            )

        return patterns

    def _detect_feature_envy(
        self, node: ast.FunctionDef, file_path: str, class_name: Optional[str] = None
    ) -> List[AntiPatternResult]:
        """
        Detect feature envy - method uses other class's data more than its own.

        This is a heuristic detection that looks for methods accessing external
        object attributes more frequently than self attributes.
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
                        external_accesses[obj_name] = (
                            external_accesses.get(obj_name, 0) + 1
                        )

        # Check if any external object is accessed more than self
        for obj_name, count in external_accesses.items():
            if count > self_accesses and count >= 3:  # At least 3 accesses
                patterns.append(
                    AntiPatternResult(
                        pattern_type=AntiPatternType.FEATURE_ENVY,
                        severity=AntiPatternSeverity.MEDIUM,
                        file_path=file_path,
                        line_number=node.lineno,
                        entity_name=node.name,
                        description=f"Method '{node.name}' accesses '{obj_name}' "
                        f"{count} times vs self {self_accesses} times",
                        suggestion=f"Consider moving this method to the '{obj_name}' class",
                        metrics={
                            "self_accesses": self_accesses,
                            "external_object": obj_name,
                            "external_accesses": count,
                        },
                    )
                )

        return patterns

    def _detect_data_clumps(
        self, file_path: str, tree: ast.AST
    ) -> List[AntiPatternResult]:
        """
        Detect data clumps - groups of variables that are always used together.

        Look for parameters that frequently appear together across multiple functions.
        """
        patterns: List[AntiPatternResult] = []

        # Collect parameter sets from all functions
        param_sets: List[Tuple[str, int, frozenset]] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = frozenset(
                    arg.arg for arg in node.args.args if arg.arg != "self"
                )
                if len(params) >= 3:  # Only consider functions with 3+ params
                    param_sets.append((node.name, node.lineno, params))

        # Find overlapping parameter groups
        seen_clumps: Set[frozenset] = set()
        for i, (name1, line1, params1) in enumerate(param_sets):
            for j, (name2, line2, params2) in enumerate(param_sets[i + 1 :], i + 1):
                overlap = params1 & params2
                if len(overlap) >= 3:  # 3 or more common params = potential clump
                    clump_key = frozenset(overlap)
                    if clump_key not in seen_clumps:
                        seen_clumps.add(clump_key)
                        patterns.append(
                            AntiPatternResult(
                                pattern_type=AntiPatternType.DATA_CLUMPS,
                                severity=AntiPatternSeverity.LOW,
                                file_path=file_path,
                                line_number=line1,
                                entity_name=f"{name1}, {name2}",
                                description=f"Parameters {sorted(overlap)} appear together "
                                f"in multiple functions",
                                suggestion="Consider grouping these parameters into a "
                                "dataclass or configuration object",
                                metrics={
                                    "clump_size": len(overlap),
                                    "parameters": sorted(overlap),
                                    "functions": [name1, name2],
                                },
                            )
                        )

        return patterns

    def _detect_dead_code(
        self, tree: ast.AST, file_path: str
    ) -> List[AntiPatternResult]:
        """
        Detect potential dead code patterns.

        Looks for:
        - Unreachable code after return/raise/break/continue
        - Empty except blocks
        - Pass statements in non-empty blocks
        """
        patterns: List[AntiPatternResult] = []

        for node in ast.walk(tree):
            # Check for unreachable code after control flow statements
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for i, stmt in enumerate(node.body[:-1]):  # All but last
                    if isinstance(stmt, (ast.Return, ast.Raise)):
                        # Check if there's more code after return/raise
                        next_stmt = node.body[i + 1]
                        # Skip if next is just a pass or docstring
                        if not isinstance(next_stmt, ast.Pass):
                            if not (
                                isinstance(next_stmt, ast.Expr)
                                and isinstance(next_stmt.value, ast.Constant)
                            ):
                                patterns.append(
                                    AntiPatternResult(
                                        pattern_type=AntiPatternType.DEAD_CODE,
                                        severity=AntiPatternSeverity.MEDIUM,
                                        file_path=file_path,
                                        line_number=getattr(
                                            next_stmt, "lineno", node.lineno
                                        ),
                                        entity_name=node.name,
                                        description="Unreachable code after return/raise",
                                        suggestion="Remove unreachable statements",
                                        metrics={"type": "unreachable_after_return"},
                                    )
                                )

            # Check for empty except blocks
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    patterns.append(
                        AntiPatternResult(
                            pattern_type=AntiPatternType.DEAD_CODE,
                            severity=AntiPatternSeverity.MEDIUM,
                            file_path=file_path,
                            line_number=node.lineno,
                            entity_name="except_handler",
                            description="Empty except block silently ignores errors",
                            suggestion="Log the exception or handle it explicitly",
                            metrics={"type": "empty_except"},
                        )
                    )

        return patterns


# Convenience function for quick analysis
def analyze_codebase(
    directory: str, exclude_dirs: Optional[List[str]] = None
) -> AnalysisReport:
    """
    Analyze a codebase for anti-patterns.

    Args:
        directory: Path to the directory to analyze
        exclude_dirs: Optional list of directories to exclude

    Returns:
        AnalysisReport with all findings
    """
    detector = AntiPatternDetector(exclude_dirs=exclude_dirs)
    return detector.analyze_directory(directory)
