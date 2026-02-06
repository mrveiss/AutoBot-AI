# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Complexity Analyzer for Code Pattern Analysis.

Issue #208: Integrates with radon for comprehensive complexity metrics.
Identifies complexity hotspots and suggests simplifications.
"""

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .types import CodeLocation, ComplexityHotspot, PatternSeverity

# Issue #607: Import shared caches for performance optimization
try:
    from code_intelligence.shared.ast_cache import get_ast_with_content

    HAS_SHARED_CACHE = True
except ImportError:
    HAS_SHARED_CACHE = False

logger = logging.getLogger(__name__)

# Try to import radon - it's optional but recommended
try:
    from radon.complexity import cc_visit
    from radon.metrics import mi_visit
    from radon.raw import analyze

    RADON_AVAILABLE = True
except ImportError:
    RADON_AVAILABLE = False
    logger.warning("radon not installed - using fallback complexity analysis")


# Complexity thresholds
CYCLOMATIC_THRESHOLDS = {
    "low": 5,  # Simple, low risk
    "moderate": 10,  # More complex, moderate risk
    "high": 20,  # Complex, high risk
    "very_high": 30,  # Very complex, very high risk
}

MAINTAINABILITY_THRESHOLDS = {
    "excellent": 80,  # Highly maintainable
    "good": 60,  # Reasonably maintainable
    "moderate": 40,  # Needs improvement
    "poor": 20,  # Hard to maintain
}


@dataclass
class FunctionComplexity:
    """Complexity metrics for a single function."""

    name: str
    file_path: str
    start_line: int
    end_line: int
    cyclomatic_complexity: int = 0
    cognitive_complexity: int = 0
    nesting_depth: int = 0
    parameter_count: int = 0
    line_count: int = 0
    class_name: Optional[str] = None

    @property
    def complexity_rank(self) -> str:
        """Get complexity rank (A-F) based on cyclomatic complexity."""
        cc = self.cyclomatic_complexity
        if cc <= 5:
            return "A"
        elif cc <= 10:
            return "B"
        elif cc <= 20:
            return "C"
        elif cc <= 30:
            return "D"
        elif cc <= 40:
            return "E"
        return "F"

    def is_hotspot(self) -> bool:
        """Check if this function is a complexity hotspot."""
        return (
            self.cyclomatic_complexity > CYCLOMATIC_THRESHOLDS["moderate"]
            or self.nesting_depth > 4
            or self.line_count > 50
        )


@dataclass
class ModuleComplexity:
    """Complexity metrics for a module/file."""

    file_path: str
    functions: List[FunctionComplexity] = field(default_factory=list)
    maintainability_index: float = 100.0
    average_complexity: float = 0.0
    total_lines: int = 0
    blank_lines: int = 0
    comment_lines: int = 0
    code_lines: int = 0

    @property
    def maintainability_rank(self) -> str:
        """Get maintainability rank based on MI."""
        mi = self.maintainability_index
        if mi >= 80:
            return "A"
        elif mi >= 60:
            return "B"
        elif mi >= 40:
            return "C"
        elif mi >= 20:
            return "D"
        return "F"


class NestingDepthVisitor(ast.NodeVisitor):
    """AST visitor to calculate nesting depth."""

    def __init__(self):
        """Initialize with zero depth."""
        self.max_depth = 0
        self.current_depth = 0

    def _increase_depth(self, node: ast.AST) -> None:
        """Increase depth and visit children."""
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1

    def visit_If(self, node: ast.If) -> None:
        """Track if statement depth."""
        self._increase_depth(node)

    def visit_For(self, node: ast.For) -> None:
        """Track for loop depth."""
        self._increase_depth(node)

    def visit_While(self, node: ast.While) -> None:
        """Track while loop depth."""
        self._increase_depth(node)

    def visit_Try(self, node: ast.Try) -> None:
        """Track try block depth."""
        self._increase_depth(node)

    def visit_With(self, node: ast.With) -> None:
        """Track with statement depth."""
        self._increase_depth(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Track except handler depth."""
        self._increase_depth(node)


class CognitiveComplexityVisitor(ast.NodeVisitor):
    """AST visitor to calculate cognitive complexity.

    Cognitive complexity is a metric that measures how difficult code is
    to understand, taking into account nesting, breaks in linear flow, etc.
    """

    def __init__(self):
        """Initialize counters."""
        self.complexity = 0
        self.nesting_level = 0

    def _increment(self, amount: int = 1) -> None:
        """Increment complexity with nesting bonus."""
        self.complexity += amount + self.nesting_level

    def _with_nesting(self, node: ast.AST) -> None:
        """Visit node with increased nesting level."""
        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_If(self, node: ast.If) -> None:
        """If statements add complexity."""
        self._increment()
        self._with_nesting(node)

    def visit_For(self, node: ast.For) -> None:
        """For loops add complexity."""
        self._increment()
        self._with_nesting(node)

    def visit_While(self, node: ast.While) -> None:
        """While loops add complexity."""
        self._increment()
        self._with_nesting(node)

    def visit_Try(self, node: ast.Try) -> None:
        """Try blocks add complexity."""
        self._increment()
        self._with_nesting(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Each except handler adds complexity."""
        self._increment()
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """Boolean operations add complexity for each operator."""
        # Each additional condition after the first adds 1
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_Break(self, node: ast.Break) -> None:
        """Break statements add complexity (flow interruption)."""
        self._increment()

    def visit_Continue(self, node: ast.Continue) -> None:
        """Continue statements add complexity (flow interruption)."""
        self._increment()

    def visit_Raise(self, node: ast.Raise) -> None:
        """Raise statements add complexity (flow interruption)."""
        self._increment()

    def visit_Return(self, node: ast.Return) -> None:
        """Early returns add complexity (except at end of function)."""
        # Note: We can't easily detect if it's the last statement
        # So we'll count all returns for now
        self.generic_visit(node)


class ComplexityAnalyzer:
    """Analyzes code complexity using radon and custom metrics.

    This analyzer provides:
    - Cyclomatic complexity (CC) per function
    - Cognitive complexity per function
    - Maintainability index (MI) per module
    - Halstead metrics for deeper analysis
    - Nesting depth tracking
    - Complexity hotspot identification
    """

    # Default thresholds for hotspot detection
    CC_THRESHOLD = 10  # Functions above this are flagged
    MI_THRESHOLD = 50  # Modules below this need attention
    NESTING_THRESHOLD = 4  # Deep nesting is problematic
    LINE_THRESHOLD = 50  # Long functions need review

    EXCLUDE_DIRS = frozenset(
        {
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".git",
            "archives",
            ".mypy_cache",
        }
    )

    def __init__(
        self,
        cc_threshold: int = 10,
        mi_threshold: float = 50,
        nesting_threshold: int = 4,
        exclude_dirs: Optional[Set[str]] = None,
        use_shared_cache: bool = True,
    ):
        """Initialize complexity analyzer.

        Args:
            cc_threshold: Cyclomatic complexity threshold for hotspots
            mi_threshold: Maintainability index threshold
            nesting_threshold: Maximum acceptable nesting depth
            exclude_dirs: Directories to exclude from analysis
            use_shared_cache: Whether to use shared ASTCache (Issue #607)
        """
        self.cc_threshold = cc_threshold
        self.mi_threshold = mi_threshold
        self.nesting_threshold = nesting_threshold
        self.exclude_dirs = exclude_dirs or self.EXCLUDE_DIRS
        self.use_shared_cache = use_shared_cache and HAS_SHARED_CACHE

    def analyze_file(self, file_path: str) -> ModuleComplexity:
        """Analyze complexity of a single Python file.

        Issue #607: Uses shared ASTCache when available for performance.

        Args:
            file_path: Path to Python file

        Returns:
            ModuleComplexity with all metrics
        """
        module = ModuleComplexity(file_path=file_path)

        try:
            # Issue #607: Use shared AST cache if available
            if self.use_shared_cache:
                tree, source = get_ast_with_content(file_path)
                if tree is None or not source:
                    return module
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    source = f.read()
                # Parse AST for custom analysis
                tree = ast.parse(source, filename=file_path)

            # Use radon if available
            if RADON_AVAILABLE:
                module = self._analyze_with_radon(source, file_path, tree)
            else:
                module = self._analyze_fallback(source, file_path, tree)

        except SyntaxError as e:
            logger.debug("Syntax error in %s: %s", file_path, e)
        except Exception as e:
            logger.debug("Error analyzing %s: %s", file_path, e)

        return module

    def _build_function_complexity_from_cc_result(
        self, result: Any, file_path: str, tree: ast.AST
    ) -> FunctionComplexity:
        """Build FunctionComplexity from a radon cc_visit result. Issue #620.

        Args:
            result: A radon complexity result object
            file_path: Path to the analyzed file
            tree: Parsed AST for additional metrics

        Returns:
            FunctionComplexity with all calculated metrics
        """
        nesting = self._calculate_nesting(tree, result.name)
        cognitive = self._calculate_cognitive_complexity(tree, result.name)

        return FunctionComplexity(
            name=result.name,
            file_path=file_path,
            start_line=result.lineno,
            end_line=result.endline,
            cyclomatic_complexity=result.complexity,
            cognitive_complexity=cognitive,
            nesting_depth=nesting,
            line_count=result.endline - result.lineno + 1,
            class_name=result.classname if hasattr(result, "classname") else None,
        )

    def _analyze_with_radon(
        self, source: str, file_path: str, tree: ast.AST
    ) -> ModuleComplexity:
        """Analyze using radon metrics.

        Args:
            source: Source code string
            file_path: Path to file
            tree: Parsed AST

        Returns:
            ModuleComplexity with radon metrics
        """
        module = ModuleComplexity(file_path=file_path)

        # Raw metrics
        raw_metrics = analyze(source)
        module.total_lines = raw_metrics.loc
        module.blank_lines = raw_metrics.blank
        module.comment_lines = raw_metrics.comments
        module.code_lines = raw_metrics.sloc

        # Maintainability index
        mi_result = mi_visit(source, multi=False)
        module.maintainability_index = mi_result

        # Cyclomatic complexity per function
        cc_results = cc_visit(source)

        for result in cc_results:
            func_complexity = self._build_function_complexity_from_cc_result(
                result, file_path, tree
            )
            module.functions.append(func_complexity)

        # Calculate average complexity
        if module.functions:
            module.average_complexity = sum(
                f.cyclomatic_complexity for f in module.functions
            ) / len(module.functions)

        return module

    def _analyze_fallback(
        self, source: str, file_path: str, tree: ast.AST
    ) -> ModuleComplexity:
        """Fallback analysis without radon.

        Args:
            source: Source code string
            file_path: Path to file
            tree: Parsed AST

        Returns:
            ModuleComplexity with basic metrics
        """
        module = ModuleComplexity(file_path=file_path)

        lines = source.split("\n")
        module.total_lines = len(lines)
        module.blank_lines = sum(1 for line in lines if not line.strip())
        module.comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
        module.code_lines = module.total_lines - module.blank_lines

        # Analyze functions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_complexity = self._analyze_function_fallback(node, file_path)
                module.functions.append(func_complexity)

        # Calculate metrics
        if module.functions:
            module.average_complexity = sum(
                f.cyclomatic_complexity for f in module.functions
            ) / len(module.functions)

        # Estimate MI (simplified formula)
        if module.code_lines > 0:
            avg_cc = module.average_complexity or 1
            module.maintainability_index = max(
                0,
                min(
                    100,
                    171
                    - 5.2 * (module.code_lines / 100)
                    - 0.23 * avg_cc
                    - 16.2 * (module.code_lines / 100),
                ),
            )

        return module

    def _calculate_cyclomatic_complexity_fallback(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity by counting decision points. Issue #620.

        Args:
            node: Function AST node to analyze

        Returns:
            Cyclomatic complexity score (decision points + 1)
        """
        cc = 1  # Base complexity
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For)):
                cc += 1
            elif isinstance(child, ast.ExceptHandler):
                cc += 1
            elif isinstance(child, ast.BoolOp):
                cc += len(child.values) - 1
            elif isinstance(child, ast.comprehension):
                cc += 1 + len(child.ifs)
        return cc

    def _count_function_parameters(self, node: ast.AST) -> int:
        """Count total parameters for a function node. Issue #620.

        Args:
            node: Function AST node

        Returns:
            Total number of parameters including args, kwargs, etc.
        """
        if not hasattr(node, "args"):
            return 0
        args = node.args
        return (
            len(args.args)
            + len(args.posonlyargs)
            + len(args.kwonlyargs)
            + (1 if args.vararg else 0)
            + (1 if args.kwarg else 0)
        )

    def _analyze_function_fallback(
        self, node: ast.AST, file_path: str
    ) -> FunctionComplexity:
        """Analyze a function without radon.

        Args:
            node: Function AST node
            file_path: Path to file

        Returns:
            FunctionComplexity with basic metrics
        """
        # Calculate complexity metrics using helper methods
        cc = self._calculate_cyclomatic_complexity_fallback(node)

        nesting_visitor = NestingDepthVisitor()
        nesting_visitor.visit(node)

        cognitive_visitor = CognitiveComplexityVisitor()
        cognitive_visitor.visit(node)

        param_count = self._count_function_parameters(node)
        end_line = getattr(node, "end_lineno", node.lineno)

        return FunctionComplexity(
            name=node.name,
            file_path=file_path,
            start_line=node.lineno,
            end_line=end_line,
            cyclomatic_complexity=cc,
            cognitive_complexity=cognitive_visitor.complexity,
            nesting_depth=nesting_visitor.max_depth,
            parameter_count=param_count,
            line_count=end_line - node.lineno + 1,
        )

    def _calculate_nesting(self, tree: ast.AST, function_name: str) -> int:
        """Calculate max nesting depth for a function.

        Args:
            tree: Full AST
            function_name: Name of function to analyze

        Returns:
            Maximum nesting depth
        """
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    visitor = NestingDepthVisitor()
                    visitor.visit(node)
                    return visitor.max_depth
        return 0

    def _calculate_cognitive_complexity(self, tree: ast.AST, function_name: str) -> int:
        """Calculate cognitive complexity for a function.

        Args:
            tree: Full AST
            function_name: Name of function to analyze

        Returns:
            Cognitive complexity score
        """
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    visitor = CognitiveComplexityVisitor()
                    visitor.visit(node)
                    return visitor.complexity
        return 0

    def analyze_directory(self, directory: str) -> List[ModuleComplexity]:
        """Analyze all Python files in a directory.

        Args:
            directory: Path to directory

        Returns:
            List of ModuleComplexity for each file
        """
        results = []
        dir_path = Path(directory)

        for py_file in dir_path.rglob("*.py"):
            if any(exc in py_file.parts for exc in self.exclude_dirs):
                continue

            module = self.analyze_file(str(py_file))
            results.append(module)

        return results

    def find_hotspots(self, modules: List[ModuleComplexity]) -> List[ComplexityHotspot]:
        """Find complexity hotspots across modules.

        Args:
            modules: List of analyzed modules

        Returns:
            List of ComplexityHotspot findings
        """
        hotspots = []

        for module in modules:
            for func in module.functions:
                if func.is_hotspot():
                    hotspot = self._create_hotspot(func, module)
                    hotspots.append(hotspot)

        # Sort by severity (cyclomatic complexity)
        return sorted(hotspots, key=lambda x: x.cyclomatic_complexity, reverse=True)

    def _create_hotspot(
        self, func: FunctionComplexity, module: ModuleComplexity
    ) -> ComplexityHotspot:
        """Create a ComplexityHotspot from function metrics.

        Args:
            func: Function complexity metrics
            module: Parent module metrics

        Returns:
            ComplexityHotspot instance
        """
        # Determine severity
        if func.cyclomatic_complexity > 30:
            severity = PatternSeverity.CRITICAL
        elif func.cyclomatic_complexity > 20:
            severity = PatternSeverity.HIGH
        elif func.cyclomatic_complexity > 10:
            severity = PatternSeverity.MEDIUM
        else:
            severity = PatternSeverity.LOW

        # Generate suggestions
        suggestions = self._generate_suggestions(func)

        location = CodeLocation(
            file_path=func.file_path,
            start_line=func.start_line,
            end_line=func.end_line,
            function_name=func.name,
            class_name=func.class_name,
        )

        return ComplexityHotspot(
            pattern_type=None,  # Set by __post_init__
            severity=severity,
            description=f"High complexity function: {func.name} (CC={func.cyclomatic_complexity})",
            locations=[location],
            suggestion="; ".join(suggestions[:2]),
            confidence=0.9,
            cyclomatic_complexity=func.cyclomatic_complexity,
            maintainability_index=module.maintainability_index,
            cognitive_complexity=func.cognitive_complexity,
            nesting_depth=func.nesting_depth,
            simplification_suggestions=suggestions,
        )

    def _generate_suggestions(self, func: FunctionComplexity) -> List[str]:
        """Generate simplification suggestions for a function.

        Args:
            func: Function complexity metrics

        Returns:
            List of suggestion strings
        """
        suggestions = []

        # High cyclomatic complexity
        if func.cyclomatic_complexity > 15:
            suggestions.append("Extract conditional branches into separate methods")
            suggestions.append(
                "Consider using strategy pattern for multiple conditions"
            )

        if func.cyclomatic_complexity > 10:
            suggestions.append("Break down into smaller, focused functions")

        # Deep nesting
        if func.nesting_depth > 4:
            suggestions.append("Reduce nesting with early returns/guard clauses")
            suggestions.append("Extract nested logic into helper methods")

        if func.nesting_depth > 3:
            suggestions.append("Consider flattening nested conditions")

        # Long functions
        if func.line_count > 50:
            suggestions.append("Function is too long - extract logical sections")

        if func.line_count > 30:
            suggestions.append("Consider splitting into smaller functions")

        # High cognitive complexity
        if func.cognitive_complexity > 15:
            suggestions.append("Simplify control flow to improve readability")

        # Fallback suggestion
        if not suggestions:
            suggestions.append("Consider refactoring for better maintainability")

        return suggestions

    def _calculate_report_averages(
        self,
        all_functions: List[FunctionComplexity],
        modules: List[ModuleComplexity],
    ) -> tuple:
        """Calculate average complexity and maintainability metrics. Issue #620.

        Args:
            all_functions: List of all functions across modules
            modules: List of analyzed modules

        Returns:
            Tuple of (average_cc, average_mi)
        """
        avg_cc = (
            sum(f.cyclomatic_complexity for f in all_functions) / len(all_functions)
            if all_functions
            else 0
        )
        avg_mi = (
            sum(m.maintainability_index for m in modules) / len(modules)
            if modules
            else 100
        )
        return avg_cc, avg_mi

    def _build_complexity_distribution(
        self, all_functions: List[FunctionComplexity]
    ) -> Dict[str, int]:
        """Build complexity rank distribution from functions. Issue #620.

        Args:
            all_functions: List of all functions across modules

        Returns:
            Dictionary mapping complexity rank (A-F) to count
        """
        cc_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}
        for func in all_functions:
            cc_dist[func.complexity_rank] += 1
        return cc_dist

    def _format_worst_functions(
        self, all_functions: List[FunctionComplexity], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Format worst complexity offenders for report. Issue #620.

        Args:
            all_functions: List of all functions across modules
            limit: Maximum number of functions to include

        Returns:
            List of formatted function dictionaries
        """
        worst_functions = sorted(
            all_functions, key=lambda x: x.cyclomatic_complexity, reverse=True
        )[:limit]
        return [
            {
                "name": f.name,
                "file": f.file_path,
                "line": f.start_line,
                "cc": f.cyclomatic_complexity,
                "rank": f.complexity_rank,
            }
            for f in worst_functions
        ]

    def generate_report(self, modules: List[ModuleComplexity]) -> Dict[str, Any]:
        """Generate a summary report of complexity analysis.

        Args:
            modules: List of analyzed modules

        Returns:
            Dictionary with summary statistics
        """
        if not modules:
            return {
                "total_modules": 0,
                "total_functions": 0,
                "hotspots": 0,
                "average_complexity": 0,
                "average_mi": 0,
            }

        all_functions = [f for m in modules for f in m.functions]
        hotspots = self.find_hotspots(modules)
        avg_cc, avg_mi = self._calculate_report_averages(all_functions, modules)

        return {
            "total_modules": len(modules),
            "total_functions": len(all_functions),
            "total_lines": sum(m.total_lines for m in modules),
            "code_lines": sum(m.code_lines for m in modules),
            "hotspots_count": len(hotspots),
            "average_complexity": round(avg_cc, 2),
            "average_maintainability": round(avg_mi, 2),
            "complexity_distribution": self._build_complexity_distribution(
                all_functions
            ),
            "worst_functions": self._format_worst_functions(all_functions),
            "hotspots": [h.to_dict() for h in hotspots[:10]],
        }
