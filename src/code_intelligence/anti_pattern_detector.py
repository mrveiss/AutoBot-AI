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

# Issue #380: Pre-compiled regex patterns for naming convention checks
_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CAMEL_CASE_RE = re.compile(r"^[a-z][a-zA-Z0-9]*$")

# Issue #380: Module-level tuple for function definition AST nodes
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_EXIT_STMT_TYPES = (ast.Return, ast.Raise)


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

    def _check_large_file(
        self, file_path: str, line_count: int
    ) -> Optional[AntiPatternResult]:
        """Check if file exceeds line count threshold."""
        if line_count <= self.LARGE_FILE_THRESHOLD:
            return None
        return AntiPatternResult(
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

    def _run_file_level_detections(
        self, tree: ast.AST, file_path: str
    ) -> List[AntiPatternResult]:
        """Run all file-level anti-pattern detections."""
        patterns: List[AntiPatternResult] = []
        patterns.extend(self._detect_naming_issues(tree, file_path))
        patterns.extend(self._detect_magic_numbers(tree, file_path))
        patterns.extend(self._detect_missing_docstrings(tree, file_path))
        patterns.extend(self._detect_data_clumps(file_path, tree))
        patterns.extend(self._detect_dead_code(tree, file_path))
        return patterns

    def _analyze_ast_nodes(
        self, tree: ast.AST, file_path: str, lines: List[str]
    ) -> Tuple[List[AntiPatternResult], int, int]:
        """Analyze all classes and functions in AST, return patterns and counts."""
        patterns: List[AntiPatternResult] = []
        class_count = 0
        function_count = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_count += 1
                patterns.extend(self._analyze_class(node, file_path, lines))
                patterns.extend(self._detect_lazy_class(node, file_path))
            elif isinstance(node, _FUNCTION_DEF_TYPES):  # Issue #380
                function_count += 1
                patterns.extend(self._analyze_function(node, file_path, lines))

        return patterns, class_count, function_count

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze a single Python file for anti-patterns.

        Args:
            file_path: Path to the Python file

        Returns:
            Dictionary with patterns found and file statistics
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=file_path)
            lines = source.split("\n")
            line_count = len(lines)

            patterns: List[AntiPatternResult] = []

            # Check for large file
            large_file_result = self._check_large_file(file_path, line_count)
            if large_file_result:
                patterns.append(large_file_result)

            # File-level and node-level detections
            patterns.extend(self._run_file_level_detections(tree, file_path))
            node_patterns, class_count, function_count = self._analyze_ast_nodes(
                tree, file_path, lines
            )
            patterns.extend(node_patterns)

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

    def _get_class_methods(self, node: ast.ClassDef) -> List[ast.AST]:
        """Extract method definitions from a class."""
        return [
            n for n in node.body
            if isinstance(n, _FUNCTION_DEF_TYPES)  # Issue #380
        ]

    def _calculate_class_size(self, node: ast.ClassDef) -> int:
        """Calculate the line count of a class."""
        class_start = node.lineno
        class_end = max(
            (getattr(n, "end_lineno", class_start) for n in ast.walk(node)),
            default=class_start,
        )
        return class_end - class_start + 1

    def _check_god_class(
        self, node: ast.ClassDef, file_path: str, method_count: int, class_lines: int
    ) -> Optional[AntiPatternResult]:
        """Check for god class anti-pattern by method count or line count."""
        if method_count > self.GOD_CLASS_METHOD_THRESHOLD:
            return AntiPatternResult(
                pattern_type=AntiPatternType.GOD_CLASS,
                severity=self._get_god_class_severity(method_count),
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
        elif class_lines > self.GOD_CLASS_LINE_THRESHOLD:
            return AntiPatternResult(
                pattern_type=AntiPatternType.GOD_CLASS,
                severity=AntiPatternSeverity.MEDIUM,
                file_path=file_path,
                line_number=node.lineno,
                entity_name=node.name,
                description=f"Class '{node.name}' has {class_lines} lines, "
                f"exceeds threshold of {self.GOD_CLASS_LINE_THRESHOLD}",
                suggestion="Consider extracting methods or splitting responsibilities",
                metrics={"method_count": method_count, "line_count": class_lines},
            )
        return None

    def _analyze_class(
        self, node: ast.ClassDef, file_path: str, lines: List[str]
    ) -> List[AntiPatternResult]:
        """Analyze a class for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        methods = self._get_class_methods(node)
        method_count = len(methods)
        class_lines = self._calculate_class_size(node)

        # God class detection
        god_class_result = self._check_god_class(
            node, file_path, method_count, class_lines
        )
        if god_class_result:
            patterns.append(god_class_result)

        # Analyze each method for anti-patterns
        for method in methods:
            patterns.extend(self._analyze_function(method, file_path, lines))

        return patterns

    def _count_function_params(self, node: ast.FunctionDef) -> int:
        """Count total parameters in a function including *args and **kwargs."""
        param_count = len(node.args.args) + len(node.args.kwonlyargs)
        if node.args.vararg:
            param_count += 1
        if node.args.kwarg:
            param_count += 1
        return param_count

    def _check_long_parameter_list(
        self, node: ast.FunctionDef, file_path: str, param_count: int
    ) -> Optional[AntiPatternResult]:
        """Check for long parameter list anti-pattern."""
        if param_count <= self.LONG_PARAMETER_THRESHOLD:
            return None
        return AntiPatternResult(
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

    def _check_long_method(
        self, node: ast.FunctionDef, file_path: str
    ) -> Optional[AntiPatternResult]:
        """Check for long method anti-pattern."""
        func_start = node.lineno
        func_end = getattr(node, "end_lineno", func_start)
        func_lines = func_end - func_start + 1

        if func_lines <= self.LONG_METHOD_THRESHOLD:
            return None
        return AntiPatternResult(
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

    def _check_deep_nesting(
        self, node: ast.FunctionDef, file_path: str
    ) -> Optional[AntiPatternResult]:
        """Check for deep nesting anti-pattern."""
        max_depth = self._calculate_nesting_depth(node)
        if max_depth <= self.DEEP_NESTING_THRESHOLD:
            return None
        return AntiPatternResult(
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

    def _analyze_function(
        self, node: ast.FunctionDef, file_path: str, lines: List[str]
    ) -> List[AntiPatternResult]:
        """Analyze a function/method for anti-patterns."""
        patterns: List[AntiPatternResult] = []

        # Long parameter list detection
        param_count = self._count_function_params(node)
        long_param_result = self._check_long_parameter_list(node, file_path, param_count)
        if long_param_result:
            patterns.append(long_param_result)

        # Function length detection
        long_method_result = self._check_long_method(node, file_path)
        if long_method_result:
            patterns.append(long_method_result)

        # Deep nesting detection
        deep_nesting_result = self._check_deep_nesting(node, file_path)
        if deep_nesting_result:
            patterns.append(deep_nesting_result)

        # Message chain detection (a.b().c().d() patterns)
        patterns.extend(self._detect_message_chains(node, file_path))

        # Complex conditional detection
        patterns.extend(self._detect_complex_conditionals(node, file_path))

        # Feature envy detection (method uses other class's data more)
        patterns.extend(self._detect_feature_envy(node, file_path))

        return patterns

    def _extract_imports_from_tree(self, tree: ast.AST) -> set:
        """Extract imported module names from AST (Issue #335 - extracted helper)."""
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        return imports

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

            self._import_graph[module_name].update(self._extract_imports_from_tree(tree))

        except Exception as e:
            logger.debug(f"Failed to collect imports from {file_path}: {e}")

    def _detect_circular_dependencies(self) -> List[AntiPatternResult]:
        """Detect circular dependencies in the import graph."""
        patterns: List[AntiPatternResult] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles_found: Set[Tuple[str, ...]] = set()

        def find_cycle(module: str, path: List[str]) -> Optional[List[str]]:
            """Recursively find circular dependency cycle in import graph."""
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
        """Calculate severity based on class method count threshold."""
        if method_count > 50:
            return AntiPatternSeverity.CRITICAL
        elif method_count > 35:
            return AntiPatternSeverity.HIGH
        elif method_count > 25:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    def _get_param_severity(self, param_count: int) -> AntiPatternSeverity:
        """Calculate severity based on function parameter count threshold."""
        if param_count > 10:
            return AntiPatternSeverity.HIGH
        elif param_count > 7:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    def _get_large_file_severity(self, line_count: int) -> AntiPatternSeverity:
        """Calculate severity based on file line count threshold."""
        if line_count > 3000:
            return AntiPatternSeverity.CRITICAL
        elif line_count > 2000:
            return AntiPatternSeverity.HIGH
        elif line_count > 1500:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    def _get_long_method_severity(self, line_count: int) -> AntiPatternSeverity:
        """Calculate severity based on method line count threshold."""
        if line_count > 150:
            return AntiPatternSeverity.HIGH
        elif line_count > 100:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    def _get_nesting_severity(self, depth: int) -> AntiPatternSeverity:
        """Calculate severity based on code nesting depth threshold."""
        if depth > 7:
            return AntiPatternSeverity.HIGH
        elif depth > 5:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.LOW

    # ========== NEW CODE SMELL DETECTIONS ==========

    def _classify_function_name(
        self, child, snake_case: List[str], camel_case: List[str]
    ) -> None:
        """Classify function name by convention (Issue #335 - extracted helper)."""
        name = child.name
        if name.startswith("_"):
            return
        if self._is_snake_case(name):
            snake_case.append(name)
        elif self._is_camel_case(name):
            camel_case.append(name)

    # Issue #314: Comprehensive list of acceptable single-letter variables
    # These are well-established conventions that don't reduce readability
    ACCEPTABLE_SINGLE_LETTER_VARS = frozenset({
        # Loop counters (universal convention)
        "i", "j", "k", "n",
        # Coordinates (universal in graphics/math)
        "x", "y", "z",
        # Mathematical formulas (common in algorithms)
        "a", "b", "c", "d",
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
        "l",  # Less common but used for lists (though discouraged due to 1/l confusion)
        "_",  # Throwaway variable (convention)
    })

    def _check_single_letter_var(
        self, child, single_letter_vars: List[Tuple[str, int]]
    ) -> None:
        """Check for single letter variable (Issue #335 - extracted helper).

        Issue #314: Expanded exceptions to include well-established conventions.
        Only flags truly problematic single-letter variables.
        """
        if not isinstance(child.ctx, ast.Store):
            return
        name = child.id
        if len(name) == 1 and name not in self.ACCEPTABLE_SINGLE_LETTER_VARS:
            single_letter_vars.append((name, getattr(child, "lineno", 0)))

    def _detect_naming_issues(
        self, node: ast.AST, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect naming convention issues."""
        patterns: List[AntiPatternResult] = []
        snake_case_names: List[str] = []
        camel_case_names: List[str] = []
        single_letter_vars: List[Tuple[str, int]] = []

        for child in ast.walk(node):
            if isinstance(child, _FUNCTION_DEF_TYPES):  # Issue #380
                self._classify_function_name(child, snake_case_names, camel_case_names)
            if isinstance(child, ast.Name):
                self._check_single_letter_var(child, single_letter_vars)

        # Check for mixed naming conventions
        if snake_case_names and camel_case_names:
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
        return bool(_SNAKE_CASE_RE.match(name))

    def _is_camel_case(self, name: str) -> bool:
        """Check if name follows camelCase convention."""
        return bool(_CAMEL_CASE_RE.match(name)) and "_" not in name

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

    def _check_function_docstring(
        self, child: ast.AST, file_path: str
    ) -> Optional[AntiPatternResult]:
        """Check if public function lacks docstring (Issue #335 - extracted helper)."""
        if not isinstance(child, _FUNCTION_DEF_TYPES):  # Issue #380
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
        self, child: ast.AST, file_path: str
    ) -> Optional[AntiPatternResult]:
        """Check if public class lacks docstring (Issue #335 - extracted helper)."""
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

    def _detect_missing_docstrings(
        self, node: ast.AST, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect public functions/classes without docstrings."""
        patterns: List[AntiPatternResult] = []

        for child in ast.walk(node):
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

    def _detect_lazy_class(
        self, node: ast.ClassDef, file_path: str
    ) -> List[AntiPatternResult]:
        """Detect classes that do too little (lazy classes)."""
        patterns: List[AntiPatternResult] = []

        # Count methods (excluding __init__ and dunder methods)
        methods = [
            n
            for n in node.body
            if isinstance(n, _FUNCTION_DEF_TYPES)  # Issue #380
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

    # Objects to exclude from Feature Envy detection (Issue #312)
    # These are legitimate patterns, not code smells
    # Issue #380: Use frozenset for O(1) lookups and immutability
    FEATURE_ENVY_EXCLUDED_OBJECTS = frozenset({
        # Standard library modules
        "os", "sys", "time", "datetime", "re", "json", "ast", "typing",
        "pathlib", "subprocess", "socket", "hashlib", "base64", "uuid",
        "asyncio", "logging", "collections", "itertools", "functools",
        "math", "random", "copy", "io", "contextlib", "enum",
        # Common framework/library objects
        "logger", "log", "cls", "np", "numpy", "cv2", "torch", "tf",
        "pd", "plt", "redis", "aiohttp", "httpx", "requests",
        # HTTP/FastAPI patterns (legitimate dependency injection)
        "request", "response", "session", "db", "conn", "cursor",
        "Request", "Response", "Session",
        # Common parameter names (passed-in data is expected to be accessed)
        "data", "config", "settings", "options", "params", "kwargs", "args",
        "node", "tree", "element", "item", "obj", "result", "results",
        # Third-party utilities
        "psutil", "pydantic", "PIL", "Image",
    })

    # Issue #380: Pre-computed lowercase version for case-insensitive lookups
    _FEATURE_ENVY_EXCLUDED_LOWER = frozenset(x.lower() for x in FEATURE_ENVY_EXCLUDED_OBJECTS)

    # Minimum threshold for Feature Envy detection (Issue #312)
    # Increased from 3 to 5 to reduce false positives
    FEATURE_ENVY_MIN_ACCESSES = 5

    def _detect_feature_envy(
        self, node: ast.FunctionDef, file_path: str, class_name: Optional[str] = None
    ) -> List[AntiPatternResult]:
        """
        Detect feature envy - method uses other class's data more than its own.

        This is a heuristic detection that looks for methods accessing external
        object attributes more frequently than self attributes.

        Excludes:
        - Standard library modules (os, time, ast, etc.)
        - Common framework objects (logger, request, response)
        - Parameter names (data passed in is expected to be accessed)
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
                        # Issue #380: Use pre-computed lowercase set
                        if obj_name.lower() not in self._FEATURE_ENVY_EXCLUDED_LOWER:
                            external_accesses[obj_name] = (
                                external_accesses.get(obj_name, 0) + 1
                            )

        # Check if any external object is accessed more than self
        for obj_name, count in external_accesses.items():
            # Increased threshold and require significant imbalance
            if count > self_accesses and count >= self.FEATURE_ENVY_MIN_ACCESSES:
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
            if isinstance(node, _FUNCTION_DEF_TYPES):  # Issue #380
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

    def _is_docstring_or_pass(self, stmt: ast.stmt) -> bool:
        """Check if statement is pass or docstring (Issue #335 - extracted helper)."""
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            return True
        return False

    def _check_unreachable_after_return(
        self, node, file_path: str
    ) -> Optional[AntiPatternResult]:
        """Check for unreachable code after return (Issue #335 - extracted helper)."""
        for i, stmt in enumerate(node.body[:-1]):
            if not isinstance(stmt, _EXIT_STMT_TYPES):  # Issue #380
                continue
            next_stmt = node.body[i + 1]
            if self._is_docstring_or_pass(next_stmt):
                continue
            return AntiPatternResult(
                pattern_type=AntiPatternType.DEAD_CODE,
                severity=AntiPatternSeverity.MEDIUM,
                file_path=file_path,
                line_number=getattr(next_stmt, "lineno", node.lineno),
                entity_name=node.name,
                description="Unreachable code after return/raise",
                suggestion="Remove unreachable statements",
                metrics={"type": "unreachable_after_return"},
            )
        return None

    def _check_empty_except(
        self, node: ast.ExceptHandler, file_path: str
    ) -> Optional[AntiPatternResult]:
        """Check for empty except block (Issue #335 - extracted helper)."""
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
            if isinstance(node, _FUNCTION_DEF_TYPES):  # Issue #380
                result = self._check_unreachable_after_return(node, file_path)
                if result:
                    patterns.append(result)
            if isinstance(node, ast.ExceptHandler):
                result = self._check_empty_except(node, file_path)
                if result:
                    patterns.append(result)

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
