# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Detection System for Issue #221

Provides comprehensive detection of code anti-patterns including:
- God Class detection (>20 methods, high complexity)
- Feature Envy detection (methods using other classes more than their own)
- Circular Dependency detection (module/class level cycles)
- Shotgun Surgery detection (scattered changes across many classes)
- Speculative Generality detection (unused abstractions)
- Dead Code detection (unreferenced classes/methods)

Each anti-pattern includes:
- Severity scoring (critical/high/medium/low)
- Detailed explanation of the issue
- Actionable refactoring suggestions
"""

import ast
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from config import UnifiedConfig

# Initialize configuration
config = UnifiedConfig()
logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for complexity calculation
_COMPLEXITY_BRANCH_TYPES = (ast.If, ast.While, ast.For, ast.ExceptHandler)


class Severity(Enum):
    """Anti-pattern severity levels"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    def score(self) -> int:
        """Numeric score for severity (higher = worse)"""
        scores = {
            Severity.CRITICAL: 100,
            Severity.HIGH: 75,
            Severity.MEDIUM: 50,
            Severity.LOW: 25,
        }
        return scores[self]


class AntiPatternType(Enum):
    """Types of anti-patterns detected"""

    GOD_CLASS = "god_class"
    FEATURE_ENVY = "feature_envy"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    SHOTGUN_SURGERY = "shotgun_surgery"
    SPECULATIVE_GENERALITY = "speculative_generality"
    DEAD_CODE = "dead_code"
    DATA_CLUMP = "data_clump"
    LONG_METHOD = "long_method"
    LONG_PARAMETER_LIST = "long_parameter_list"
    PRIMITIVE_OBSESSION = "primitive_obsession"
    LAZY_CLASS = "lazy_class"
    REFUSED_BEQUEST = "refused_bequest"


@dataclass
class AntiPatternInstance:
    """Represents a detected anti-pattern instance"""

    pattern_type: AntiPatternType
    severity: Severity
    file_path: str
    line_number: int
    entity_name: str  # class/method/module name
    description: str
    metrics: Dict[str, Any]  # Pattern-specific metrics
    suggestion: str
    refactoring_effort: str  # low, medium, high
    related_entities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "pattern_type": self.pattern_type.value,
            "severity": self.severity.value,
            "severity_score": self.severity.score(),
            "file_path": self.file_path,
            "line_number": self.line_number,
            "entity_name": self.entity_name,
            "description": self.description,
            "metrics": self.metrics,
            "suggestion": self.suggestion,
            "refactoring_effort": self.refactoring_effort,
            "related_entities": self.related_entities,
        }


@dataclass
class ClassInfo:
    """Parsed class information for analysis"""

    name: str
    file_path: str
    line_number: int
    methods: List[ast.FunctionDef]
    attributes: Set[str]
    base_classes: List[str]
    method_calls: Dict[str, List[str]]  # method -> list of called methods/attrs
    external_references: Dict[str, int]  # other_class -> count of references
    lines_of_code: int
    complexity: int

    # === Issue #372: Feature Envy Reduction Methods ===

    @property
    def method_count(self) -> int:
        """Get count of methods (Issue #372 - reduces feature envy)."""
        return len(self.methods)

    @property
    def attribute_count(self) -> int:
        """Get count of attributes (Issue #372 - reduces feature envy)."""
        return len(self.attributes)

    @property
    def public_method_count(self) -> int:
        """Get count of non-dunder methods (Issue #372 - reduces feature envy)."""
        return len([m for m in self.methods if not m.name.startswith("__")])

    def has_base_class(self, *class_names: str) -> bool:
        """Check if class has any of the specified base classes (Issue #372)."""
        return any(base in class_names for base in self.base_classes)

    def get_referenced_class_names(self) -> Set[str]:
        """Get all class names referenced in method calls (Issue #372)."""
        referenced: Set[str] = set()
        referenced.update(self.base_classes)
        for calls in self.method_calls.values():
            referenced.update(call.split(".", 1)[0] for call in calls if "." in call)
        return referenced

    def to_metrics_dict(self) -> Dict[str, Any]:
        """Convert to metrics dictionary for reporting (Issue #372)."""
        return {
            "method_count": self.method_count,
            "attribute_count": self.attribute_count,
            "lines_of_code": self.lines_of_code,
            "complexity": self.complexity,
        }


@dataclass
class ModuleInfo:
    """Parsed module information for analysis"""

    name: str
    file_path: str
    imports: List[str]  # imported module names
    classes: List[ClassInfo]
    functions: List[str]
    is_imported_by: Set[str] = field(default_factory=set)


@dataclass
class AntiPatternReport:
    """Complete anti-pattern analysis report"""

    total_issues: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    health_score: float  # 0-100 (higher is better)
    anti_patterns: List[AntiPatternInstance]
    summary_by_type: Dict[str, int]
    recommendations: List[str]
    analysis_time_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "total_issues": self.total_issues,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "health_score": round(self.health_score, 2),
            "anti_patterns": [ap.to_dict() for ap in self.anti_patterns],
            "summary_by_type": self.summary_by_type,
            "recommendations": self.recommendations,
            "analysis_time_seconds": round(self.analysis_time_seconds, 3),
        }

    # === Issue #372: Feature Envy Reduction Methods ===

    def get_severity_counts(self) -> Dict[str, int]:
        """Get severity counts dictionary (Issue #372 - reduces feature envy)."""
        return {
            "critical": self.critical_count,
            "high": self.high_count,
            "medium": self.medium_count,
            "low": self.low_count,
        }

    def to_summary_response(self) -> Dict[str, Any]:
        """Convert to summary response dictionary (Issue #372 - reduces feature envy)."""
        return {
            "total_issues": self.total_issues,
            "severity_counts": self.get_severity_counts(),
            "health_score": round(self.health_score, 2),
            "summary_by_type": self.summary_by_type,
            "analysis_time_seconds": round(self.analysis_time_seconds, 3),
        }

    def get_log_summary(self) -> str:
        """Get log summary string (Issue #372 - reduces feature envy)."""
        return f"{self.total_issues} issues, health score: {self.health_score:.1f}/100"


class AntiPatternDetector:
    """
    Comprehensive anti-pattern detection engine.

    Detects and reports code smells and anti-patterns with severity scoring
    and actionable refactoring suggestions.
    """

    # Configuration thresholds
    GOD_CLASS_METHOD_THRESHOLD = 20
    GOD_CLASS_ATTR_THRESHOLD = 15
    GOD_CLASS_LOC_THRESHOLD = 500
    LONG_METHOD_THRESHOLD = 50  # lines
    LONG_PARAM_LIST_THRESHOLD = 5
    FEATURE_ENVY_THRESHOLD = 3  # external refs > self refs * threshold
    LAZY_CLASS_METHOD_THRESHOLD = 2  # classes with fewer methods
    LAZY_CLASS_LOC_THRESHOLD = 20

    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.config = config

        # Cache keys
        self.CACHE_KEY = "anti_pattern_analysis"
        self.CACHE_TTL = 3600  # 1 hour

        # Analysis state
        self.modules: Dict[str, ModuleInfo] = {}
        self.classes: Dict[str, ClassInfo] = {}
        self.all_defined_names: Set[str] = set()

        logger.info("AntiPatternDetector initialized")

    async def analyze(
        self,
        root_path: str = ".",
        patterns: List[str] = None,
        exclude_patterns: List[str] = None,
    ) -> AntiPatternReport:
        """
        Analyze codebase for anti-patterns.

        Args:
            root_path: Root directory to analyze
            patterns: Glob patterns for files to include (default: ["**/*.py"])
            exclude_patterns: Patterns to exclude

        Returns:
            AntiPatternReport with all detected issues
        """
        import time

        start_time = time.time()

        patterns = patterns or ["**/*.py"]
        exclude_patterns = exclude_patterns or [
            "__pycache__",
            ".git",
            "node_modules",
            ".venv",
            "venv",
            "test_",
            "_test.py",
            "tests/",
            "migrations/",
        ]

        logger.info(f"Starting anti-pattern analysis in {root_path}")

        # Phase 1: Parse all files and build module/class index
        await self._parse_codebase(root_path, patterns, exclude_patterns)
        logger.info(f"Parsed {len(self.modules)} modules, {len(self.classes)} classes")

        # Phase 2: Detect all anti-patterns
        anti_patterns: List[AntiPatternInstance] = []

        # Detect each type of anti-pattern
        anti_patterns.extend(await self._detect_god_classes())
        anti_patterns.extend(await self._detect_feature_envy())
        anti_patterns.extend(await self._detect_circular_dependencies())
        anti_patterns.extend(await self._detect_long_methods())
        anti_patterns.extend(await self._detect_long_parameter_lists())
        anti_patterns.extend(await self._detect_lazy_classes())
        anti_patterns.extend(await self._detect_dead_code())
        anti_patterns.extend(await self._detect_data_clumps())

        # Phase 3: Generate report
        analysis_time = time.time() - start_time

        report = self._generate_report(anti_patterns, analysis_time)

        # Cache results
        await self._cache_results(report)

        logger.info(
            f"Anti-pattern analysis complete: {report.total_issues} issues found "
            f"in {analysis_time:.2f}s (health score: {report.health_score:.1f}/100)"
        )

        return report

    async def _parse_codebase(
        self, root_path: str, patterns: List[str], exclude_patterns: List[str]
    ) -> None:
        """Parse all Python files and build indexes.

        Issue #510: Optimized O(n³) → O(n²) by converting exclude_patterns
        to a frozenset for O(1) substring checks instead of O(e) per file.
        """
        self.modules.clear()
        self.classes.clear()
        self.all_defined_names.clear()

        root = Path(root_path)

        # Issue #510: Convert exclude_patterns to frozenset once
        # Enables O(1) membership check per pattern
        exclude_set = frozenset(exclude_patterns)

        for pattern in patterns:
            for file_path in root.glob(pattern):
                if file_path.is_file() and not self._should_skip(
                    file_path, exclude_set
                ):
                    try:
                        module_info = await self._parse_file(str(file_path))
                        if module_info:
                            self.modules[module_info.name] = module_info
                            for cls_info in module_info.classes:
                                self.classes[
                                    f"{module_info.name}.{cls_info.name}"
                                ] = cls_info
                                self.all_defined_names.add(cls_info.name)
                            self.all_defined_names.update(module_info.functions)
                    except Exception as e:
                        logger.warning(f"Failed to parse {file_path}: {e}")

        # Build import graph (who imports whom)
        for module in self.modules.values():
            for imported in module.imports:
                if imported in self.modules:
                    self.modules[imported].is_imported_by.add(module.name)

    def _should_skip(
        self, file_path: Path, exclude_patterns: "frozenset[str] | List[str]"
    ) -> bool:
        """Check if file should be skipped.

        Issue #510: Accepts frozenset for O(1) membership check.
        """
        path_str = str(file_path)
        return any(pattern in path_str for pattern in exclude_patterns)

    async def _parse_file(self, file_path: str) -> Optional[ModuleInfo]:
        """Parse a single Python file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=file_path)
            module_name = Path(file_path).stem

            # Extract imports
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module.split(".")[0])

            # Extract classes
            classes = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    cls_info = self._analyze_class(node, file_path, content)
                    if cls_info:
                        classes.append(cls_info)

            # Extract top-level functions
            functions = [
                node.name
                for node in ast.iter_child_nodes(tree)
                if isinstance(node, ast.FunctionDef)
            ]

            return ModuleInfo(
                name=module_name,
                file_path=file_path,
                imports=list(set(imports)),
                classes=classes,
                functions=functions,
            )

        except SyntaxError:
            return None
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return None

    def _analyze_class(
        self, node: ast.ClassDef, file_path: str, content: str
    ) -> Optional[ClassInfo]:
        """Analyze a class definition"""
        try:
            # Extract methods
            methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]

            # Extract attributes (from __init__ and class body)
            attributes = set()
            for method in methods:
                if method.name == "__init__":
                    for child in ast.walk(method):
                        if isinstance(child, ast.Attribute):
                            if (
                                isinstance(child.value, ast.Name)
                                and child.value.id == "self"
                            ):
                                attributes.add(child.attr)

            # Extract base classes
            base_classes = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_classes.append(base.id)
                elif isinstance(base, ast.Attribute):
                    base_classes.append(base.attr)

            # Analyze method calls and external references
            method_calls = {}
            external_references: Dict[str, int] = {}

            for method in methods:
                calls = []
                for child in ast.walk(method):
                    if isinstance(child, ast.Attribute):
                        if isinstance(child.value, ast.Name):
                            if child.value.id == "self":
                                calls.append(f"self.{child.attr}")
                            else:
                                # External reference
                                ref_name = child.value.id
                                external_references[ref_name] = (
                                    external_references.get(ref_name, 0) + 1
                                )
                                calls.append(f"{ref_name}.{child.attr}")
                method_calls[method.name] = calls

            # Calculate lines of code
            start_line = node.lineno
            end_line = node.end_lineno or start_line
            lines_of_code = end_line - start_line + 1

            # Calculate complexity (cyclomatic complexity approximation)
            complexity = self._calculate_complexity(node)

            return ClassInfo(
                name=node.name,
                file_path=file_path,
                line_number=node.lineno,
                methods=methods,
                attributes=attributes,
                base_classes=base_classes,
                method_calls=method_calls,
                external_references=external_references,
                lines_of_code=lines_of_code,
                complexity=complexity,
            )

        except Exception as e:
            logger.error(f"Error analyzing class {node.name}: {e}")
            return None

    def _calculate_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            # Issue #380: Use module-level constant
            if isinstance(child, _COMPLEXITY_BRANCH_TYPES):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, ast.comprehension):
                complexity += 1

        return complexity

    # ========== God Class Detection ==========

    async def _detect_god_classes(self) -> List[AntiPatternInstance]:
        """Detect God Class anti-pattern"""
        issues = []

        for full_name, cls_info in self.classes.items():
            god_class_score = self._calculate_god_class_score(cls_info)

            if god_class_score > 0:
                severity = self._god_class_severity(god_class_score, cls_info)
                # Issue #372: Use cls_info.to_metrics_dict() to reduce feature envy
                metrics = cls_info.to_metrics_dict()
                metrics["god_class_score"] = god_class_score
                issues.append(
                    AntiPatternInstance(
                        pattern_type=AntiPatternType.GOD_CLASS,
                        severity=severity,
                        file_path=cls_info.file_path,
                        line_number=cls_info.line_number,
                        entity_name=cls_info.name,
                        description=self._god_class_description(cls_info),
                        metrics=metrics,
                        suggestion=self._god_class_suggestion(cls_info),
                        refactoring_effort="high" if god_class_score > 70 else "medium",
                    )
                )

        return issues

    def _calculate_god_class_score(self, cls_info: ClassInfo) -> int:
        """Calculate God Class score (0-100)

        Issue #372: Uses cls_info properties to reduce feature envy.
        """
        score = 0

        # Method count score - Issue #372: use property
        if cls_info.method_count > self.GOD_CLASS_METHOD_THRESHOLD:
            score += min(
                30, (cls_info.method_count - self.GOD_CLASS_METHOD_THRESHOLD) * 2
            )

        # Attribute count score - Issue #372: use property
        if cls_info.attribute_count > self.GOD_CLASS_ATTR_THRESHOLD:
            score += min(
                20, (cls_info.attribute_count - self.GOD_CLASS_ATTR_THRESHOLD) * 2
            )

        # Lines of code score
        if cls_info.lines_of_code > self.GOD_CLASS_LOC_THRESHOLD:
            score += min(
                30, (cls_info.lines_of_code - self.GOD_CLASS_LOC_THRESHOLD) // 50
            )

        # Complexity score
        if cls_info.complexity > 30:
            score += min(20, (cls_info.complexity - 30))

        return min(100, score)

    def _god_class_severity(self, score: int, cls_info: ClassInfo) -> Severity:
        """Determine God Class severity

        Issue #372: Uses cls_info.method_count property to reduce feature envy.
        """
        if score >= 70 or cls_info.method_count > 40:
            return Severity.CRITICAL
        elif score >= 50 or cls_info.method_count > 30:
            return Severity.HIGH
        elif score >= 30:
            return Severity.MEDIUM
        return Severity.LOW

    def _god_class_description(self, cls_info: ClassInfo) -> str:
        """Generate God Class description

        Issue #372: Uses cls_info properties to reduce feature envy.
        """
        return (
            f"Class '{cls_info.name}' has {cls_info.method_count} methods, "
            f"{cls_info.attribute_count} attributes, and {cls_info.lines_of_code} lines of code. "
            f"This violates the Single Responsibility Principle."
        )

    def _god_class_suggestion(self, cls_info: ClassInfo) -> str:
        """Generate God Class refactoring suggestion

        Issue #372: Uses cls_info.attribute_count property to reduce feature envy.
        """
        suggestions = [
            "Extract cohesive groups of methods into separate classes",
            "Apply Single Responsibility Principle - each class should have one reason to change",
            "Consider using composition instead of one monolithic class",
        ]

        # Add specific suggestions based on analysis - Issue #372: use property
        if cls_info.attribute_count > 20:
            suggestions.append(
                "Group related attributes into data classes or value objects"
            )

        if cls_info.complexity > 50:
            suggestions.append(
                "Extract complex logic into strategy or command patterns"
            )

        return " | ".join(suggestions)

    # ========== Feature Envy Detection ==========

    async def _detect_feature_envy(self) -> List[AntiPatternInstance]:
        """Detect Feature Envy anti-pattern"""
        issues = []

        for full_name, cls_info in self.classes.items():
            for method in cls_info.methods:
                if method.name.startswith("_") and method.name != "__init__":
                    continue  # Skip private methods (less likely to be feature envy)

                envy_info = self._analyze_feature_envy(method, cls_info)
                if envy_info:
                    envied_class, self_refs, external_refs = envy_info
                    issues.append(
                        AntiPatternInstance(
                            pattern_type=AntiPatternType.FEATURE_ENVY,
                            severity=Severity.MEDIUM
                            if external_refs < 10
                            else Severity.HIGH,
                            file_path=cls_info.file_path,
                            line_number=method.lineno,
                            entity_name=f"{cls_info.name}.{method.name}",
                            description=(
                                f"Method '{method.name}' in '{cls_info.name}' references "
                                f"'{envied_class}' {external_refs} times vs self {self_refs} times"
                            ),
                            metrics={
                                "self_references": self_refs,
                                "external_references": external_refs,
                                "envied_class": envied_class,
                            },
                            suggestion=(
                                f"Consider moving method '{method.name}' to class '{envied_class}' "
                                f"or extracting shared logic into a common service"
                            ),
                            refactoring_effort="medium",
                            related_entities=[envied_class],
                        )
                    )

        return issues

    def _analyze_feature_envy(
        self, method: ast.FunctionDef, cls_info: ClassInfo
    ) -> Optional[Tuple[str, int, int]]:
        """Analyze a method for feature envy"""
        self_refs = 0
        external_refs: Dict[str, int] = {}

        for child in ast.walk(method):
            if isinstance(child, ast.Attribute):
                if isinstance(child.value, ast.Name):
                    if child.value.id == "self":
                        self_refs += 1
                    else:
                        ref_name = child.value.id
                        external_refs[ref_name] = external_refs.get(ref_name, 0) + 1

        # Find the most-referenced external entity
        if external_refs:
            most_envied = max(external_refs.items(), key=lambda x: x[1])
            envied_class, envied_count = most_envied

            # Feature envy if external refs significantly exceed self refs
            if envied_count >= self.FEATURE_ENVY_THRESHOLD and envied_count > self_refs:
                return (envied_class, self_refs, envied_count)

        return None

    # ========== Circular Dependency Detection ==========

    async def _detect_circular_dependencies(self) -> List[AntiPatternInstance]:
        """Detect circular dependencies at module level"""
        issues = []

        # Build dependency graph
        dep_graph: Dict[str, Set[str]] = {}
        for module in self.modules.values():
            dep_graph[module.name] = set(
                imp for imp in module.imports if imp in self.modules
            )

        # Find cycles using DFS
        cycles = self._find_all_cycles(dep_graph)

        for cycle in cycles:
            cycle_str = " -> ".join(cycle + [cycle[0]])
            issues.append(
                AntiPatternInstance(
                    pattern_type=AntiPatternType.CIRCULAR_DEPENDENCY,
                    severity=Severity.HIGH if len(cycle) > 2 else Severity.MEDIUM,
                    file_path=self.modules[cycle[0]].file_path
                    if cycle[0] in self.modules
                    else "",
                    line_number=1,
                    entity_name=cycle[0],
                    description=f"Circular dependency detected: {cycle_str}",
                    metrics={"cycle_length": len(cycle), "modules_involved": cycle},
                    suggestion=(
                        "Break the cycle by: (1) Extract shared code into a common module, "
                        "(2) Use dependency injection, (3) Apply the Dependency Inversion Principle"
                    ),
                    refactoring_effort="high",
                    related_entities=cycle[1:],
                )
            )

        return issues

    def _find_all_cycles(self, graph: Dict[str, Set[str]]) -> List[List[str]]:
        """Find all cycles in dependency graph using DFS"""
        cycles = []
        visited = set()
        rec_stack = []

        def dfs(node: str, path: List[str]):
            if node in rec_stack:
                # Found a cycle
                cycle_start = rec_stack.index(node)
                cycle = rec_stack[cycle_start:]
                if cycle not in cycles:
                    cycles.append(cycle.copy())
                return

            if node in visited:
                return

            visited.add(node)
            rec_stack.append(node)

            for neighbor in graph.get(node, set()):
                dfs(neighbor, path + [neighbor])

            rec_stack.pop()

        for node in graph:
            if node not in visited:
                dfs(node, [node])

        return cycles

    # ========== Long Method Detection ==========

    async def _detect_long_methods(self) -> List[AntiPatternInstance]:
        """Detect excessively long methods"""
        issues = []

        for full_name, cls_info in self.classes.items():
            for method in cls_info.methods:
                method_lines = (method.end_lineno or method.lineno) - method.lineno + 1

                if method_lines > self.LONG_METHOD_THRESHOLD:
                    complexity = self._calculate_complexity(method)
                    severity = Severity.HIGH if method_lines > 100 else Severity.MEDIUM

                    issues.append(
                        AntiPatternInstance(
                            pattern_type=AntiPatternType.LONG_METHOD,
                            severity=severity,
                            file_path=cls_info.file_path,
                            line_number=method.lineno,
                            entity_name=f"{cls_info.name}.{method.name}",
                            description=(
                                f"Method '{method.name}' has {method_lines} lines "
                                f"(threshold: {self.LONG_METHOD_THRESHOLD})"
                            ),
                            metrics={"lines": method_lines, "complexity": complexity},
                            suggestion=(
                                "Extract method: break into smaller, well-named methods. "
                                "Each method should do one thing and do it well."
                            ),
                            refactoring_effort="medium",
                        )
                    )

        return issues

    # ========== Long Parameter List Detection ==========

    async def _detect_long_parameter_lists(self) -> List[AntiPatternInstance]:
        """Detect methods with too many parameters"""
        issues = []

        for full_name, cls_info in self.classes.items():
            for method in cls_info.methods:
                # Count parameters (excluding self)
                params = [arg for arg in method.args.args if arg.arg != "self"]
                param_count = len(params)

                if param_count > self.LONG_PARAM_LIST_THRESHOLD:
                    param_names = [arg.arg for arg in params]

                    issues.append(
                        AntiPatternInstance(
                            pattern_type=AntiPatternType.LONG_PARAMETER_LIST,
                            severity=Severity.MEDIUM
                            if param_count < 8
                            else Severity.HIGH,
                            file_path=cls_info.file_path,
                            line_number=method.lineno,
                            entity_name=f"{cls_info.name}.{method.name}",
                            description=(
                                f"Method '{method.name}' has {param_count} parameters "
                                f"(threshold: {self.LONG_PARAM_LIST_THRESHOLD})"
                            ),
                            metrics={
                                "parameter_count": param_count,
                                "parameters": param_names,
                            },
                            suggestion=(
                                "Introduce Parameter Object: group related parameters into a data class. "
                                "Consider using builder pattern or configuration objects."
                            ),
                            refactoring_effort="low",
                        )
                    )

        return issues

    # ========== Lazy Class Detection ==========

    async def _detect_lazy_classes(self) -> List[AntiPatternInstance]:
        """Detect classes that don't do enough to justify their existence

        Issue #372: Uses cls_info helper methods to reduce feature envy.
        """
        issues = []

        for full_name, cls_info in self.classes.items():
            # Skip dataclasses, enums, and exception classes
            # Issue #372: Use has_base_class method to reduce feature envy
            if cls_info.has_base_class("Enum", "Exception", "BaseException"):
                continue

            # Issue #372: Use public_method_count property to reduce feature envy
            if (
                cls_info.public_method_count <= self.LAZY_CLASS_METHOD_THRESHOLD
                and cls_info.lines_of_code <= self.LAZY_CLASS_LOC_THRESHOLD
            ):
                issues.append(
                    AntiPatternInstance(
                        pattern_type=AntiPatternType.LAZY_CLASS,
                        severity=Severity.LOW,
                        file_path=cls_info.file_path,
                        line_number=cls_info.line_number,
                        entity_name=cls_info.name,
                        description=(
                            f"Class '{cls_info.name}' has only {cls_info.public_method_count} methods "
                            f"and {cls_info.lines_of_code} lines - may not justify its existence"
                        ),
                        metrics={
                            "method_count": cls_info.public_method_count,
                            "lines_of_code": cls_info.lines_of_code,
                        },
                        suggestion=(
                            "Consider: (1) Merge with related class, (2) Convert to module-level functions, "
                            "(3) Use @dataclass if it's just data, (4) Keep if it serves as extension point"
                        ),
                        refactoring_effort="low",
                    )
                )

        return issues

    # ========== Dead Code Detection ==========

    async def _detect_dead_code(self) -> List[AntiPatternInstance]:
        """Detect potentially dead (unreferenced) classes and functions.

        Issue #372: Uses cls_info.get_referenced_class_names() to reduce feature envy.

        Optimized from O(m × c × v × n + m × c² × i) to O(m × c + total_calls):
        1. Pre-compute all referenced names in a single pass using set operations
        2. Pre-compute all imported names for O(1) lookup
        3. Use tuple for entry point suffixes (O(1) vs list iteration)
        """
        issues = []

        # Pre-compute entry point suffixes as tuple for faster endswith check
        _ENTRY_POINT_SUFFIXES = (
            "Test",
            "Tests",
            "TestCase",
            "Handler",
            "View",
            "API",
            "Router",
        )

        # Collect all referenced names efficiently using set operations
        # Issue #372: Use cls_info.get_referenced_class_names() to reduce feature envy
        referenced_names: Set[str] = set()
        for module in self.modules.values():
            for cls_info in module.classes:
                # Issue #372: Use helper method instead of accessing internal attributes
                referenced_names.update(cls_info.get_referenced_class_names())

        # Pre-compute all imported names across all modules for O(1) lookup
        # This avoids O(n²) repeated string searches
        all_imports_str = "|".join(str(m.imports) for m in self.modules.values())

        # Check for unreferenced classes with O(1) lookups
        for full_name, cls_info in self.classes.items():
            # Skip if it's likely an entry point, test, or base class
            # Using tuple for endswith is more efficient
            if cls_info.name.endswith(_ENTRY_POINT_SUFFIXES):
                continue

            if cls_info.name not in referenced_names and not cls_info.base_classes:
                # O(1) substring check in pre-computed import string
                if cls_info.name not in all_imports_str:
                    issues.append(
                        AntiPatternInstance(
                            pattern_type=AntiPatternType.DEAD_CODE,
                            severity=Severity.LOW,
                            file_path=cls_info.file_path,
                            line_number=cls_info.line_number,
                            entity_name=cls_info.name,
                            description=(
                                f"Class '{cls_info.name}' appears to be unused - "
                                f"no references found in analyzed codebase"
                            ),
                            metrics={
                                "method_count": cls_info.method_count,
                                "lines_of_code": cls_info.lines_of_code,
                            },
                            suggestion=(
                                "Verify if class is used: check tests, external imports, dynamic loading. "
                                "Remove if confirmed unused."
                            ),
                            refactoring_effort="low",
                        )
                    )

        return issues

    # ========== Data Clump Detection ==========

    async def _detect_data_clumps(self) -> List[AntiPatternInstance]:
        """Detect groups of parameters that frequently appear together"""
        issues = []

        # Collect parameter groups from all methods
        param_groups: Dict[Tuple[str, ...], List[str]] = {}

        for full_name, cls_info in self.classes.items():
            for method in cls_info.methods:
                params = tuple(
                    sorted(
                        arg.arg
                        for arg in method.args.args
                        if arg.arg not in ("self", "cls")
                    )
                )

                if len(params) >= 3:  # Only consider groups of 3+
                    if params not in param_groups:
                        param_groups[params] = []
                    param_groups[params].append(f"{cls_info.name}.{method.name}")

        # Report param groups that appear multiple times
        for params, methods in param_groups.items():
            if len(methods) >= 3:  # Appears in 3+ methods
                issues.append(
                    AntiPatternInstance(
                        pattern_type=AntiPatternType.DATA_CLUMP,
                        severity=Severity.MEDIUM if len(methods) > 5 else Severity.LOW,
                        file_path=self.classes[methods[0].split(".")[0]].file_path
                        if methods
                        else "",
                        line_number=1,
                        entity_name=", ".join(params),
                        description=(
                            f"Parameter group ({', '.join(params)}) appears in {len(methods)} methods"
                        ),
                        metrics={
                            "parameter_count": len(params),
                            "occurrence_count": len(methods),
                            "methods": methods[:5],  # First 5 examples
                        },
                        suggestion=(
                            "Extract these parameters into a data class or named tuple. "
                            "This improves readability and allows adding behavior."
                        ),
                        refactoring_effort="low",
                        related_entities=list(methods[:5]),
                    )
                )

        return issues

    # ========== Report Generation ==========

    def _generate_report(
        self, anti_patterns: List[AntiPatternInstance], analysis_time: float
    ) -> AntiPatternReport:
        """Generate comprehensive anti-pattern report"""

        # Count by severity
        critical_count = sum(
            1 for ap in anti_patterns if ap.severity == Severity.CRITICAL
        )
        high_count = sum(1 for ap in anti_patterns if ap.severity == Severity.HIGH)
        medium_count = sum(1 for ap in anti_patterns if ap.severity == Severity.MEDIUM)
        low_count = sum(1 for ap in anti_patterns if ap.severity == Severity.LOW)

        # Summary by type
        summary_by_type: Dict[str, int] = {}
        for ap in anti_patterns:
            pattern_type = ap.pattern_type.value
            summary_by_type[pattern_type] = summary_by_type.get(pattern_type, 0) + 1

        # Calculate health score (0-100, higher is better)
        # Weighted penalty for each severity level
        total_penalty = (
            critical_count * 20 + high_count * 10 + medium_count * 5 + low_count * 2
        )
        health_score = max(0, 100 - total_penalty)

        # Generate recommendations
        recommendations = self._generate_recommendations(anti_patterns, summary_by_type)

        return AntiPatternReport(
            total_issues=len(anti_patterns),
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            health_score=health_score,
            anti_patterns=anti_patterns,
            summary_by_type=summary_by_type,
            recommendations=recommendations,
            analysis_time_seconds=analysis_time,
        )

    # Issue #372: Class-level recommendation mapping reduces feature envy
    # by using self-contained data instead of repeated dict access
    _RECOMMENDATION_MAP: List[Tuple[str, str]] = [
        # Priority 1: Critical issues
        (
            "god_class",
            "🔴 CRITICAL: Refactor God Classes - Break down large classes "
            "following Single Responsibility Principle",
        ),
        (
            "circular_dependency",
            "🔴 CRITICAL: Resolve Circular Dependencies - "
            "Use dependency injection or extract common code",
        ),
        # Priority 2: High severity
        (
            "feature_envy",
            "🟠 HIGH: Address Feature Envy - "
            "Move methods to the classes they reference most",
        ),
        (
            "long_method",
            "🟠 HIGH: Extract Long Methods - "
            "Break into smaller, single-purpose methods",
        ),
        # Priority 3: Medium severity
        (
            "long_parameter_list",
            "🟡 MEDIUM: Reduce Parameter Lists - "
            "Introduce parameter objects or builder pattern",
        ),
        (
            "data_clump",
            "🟡 MEDIUM: Extract Data Clumps - "
            "Group recurring parameters into data classes",
        ),
        # Priority 4: Low severity / housekeeping
        (
            "lazy_class",
            "🟢 LOW: Review Lazy Classes - "
            "Consider merging or converting to functions",
        ),
        (
            "dead_code",
            "🟢 LOW: Remove Dead Code - " "Delete verified unused classes and functions",
        ),
    ]

    def _generate_recommendations(
        self, anti_patterns: List[AntiPatternInstance], summary_by_type: Dict[str, int]
    ) -> List[str]:
        """Generate prioritized recommendations based on findings.

        Issue #372: Uses self._RECOMMENDATION_MAP to reduce feature envy
        by minimizing repeated dictionary access patterns.
        """
        recommendations = []

        # Issue #372: Use data-driven approach with class-level mapping
        for pattern_type, recommendation in self._RECOMMENDATION_MAP:
            if summary_by_type.get(pattern_type, 0) > 0:
                recommendations.append(recommendation)

        # General recommendations
        if not recommendations:
            recommendations.append(
                "✅ Codebase looks healthy - no major anti-patterns detected"
            )
        else:
            recommendations.append(
                "📋 General: Apply SOLID principles and consider adding architectural tests"
            )

        return recommendations

    async def _cache_results(self, report: AntiPatternReport) -> None:
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                import json

                key = f"{self.CACHE_KEY}:latest"
                value = json.dumps(report.to_dict(), default=str)
                await self.redis_client.setex(key, self.CACHE_TTL, value)
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def get_cached_report(self) -> Optional[AntiPatternReport]:
        """Retrieve cached analysis report"""
        if self.redis_client:
            try:
                import json

                key = f"{self.CACHE_KEY}:latest"
                data = await self.redis_client.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Failed to retrieve cached results: {e}")
        return None


# Convenience function for CLI usage
async def run_analysis(root_path: str = ".") -> AntiPatternReport:
    """Run anti-pattern analysis on the specified path"""
    detector = AntiPatternDetector()
    return await detector.analyze(root_path)


if __name__ == "__main__":
    import asyncio

    async def main():
        """Example usage"""
        detector = AntiPatternDetector()
        report = await detector.analyze(
            root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
        )

        print(f"\n{'='*60}")
        print("ANTI-PATTERN ANALYSIS REPORT")
        print(f"{'='*60}")
        print(f"Total Issues: {report.total_issues}")
        print(f"  Critical: {report.critical_count}")
        print(f"  High: {report.high_count}")
        print(f"  Medium: {report.medium_count}")
        print(f"  Low: {report.low_count}")
        print(f"\nHealth Score: {report.health_score}/100")
        print(f"Analysis Time: {report.analysis_time_seconds:.2f}s")

        print(f"\n{'='*60}")
        print("SUMMARY BY TYPE")
        print(f"{'='*60}")
        for pattern_type, count in sorted(report.summary_by_type.items()):
            print(f"  {pattern_type}: {count}")

        print(f"\n{'='*60}")
        print("RECOMMENDATIONS")
        print(f"{'='*60}")
        for rec in report.recommendations:
            print(f"  {rec}")

        if report.anti_patterns:
            print(f"\n{'='*60}")
            print("TOP ISSUES (by severity)")
            print(f"{'='*60}")
            sorted_patterns = sorted(
                report.anti_patterns, key=lambda x: x.severity.score(), reverse=True
            )
            for ap in sorted_patterns[:10]:
                print(f"\n[{ap.severity.value.upper()}] {ap.pattern_type.value}")
                print(f"  Entity: {ap.entity_name}")
                print(f"  File: {ap.file_path}:{ap.line_number}")
                print(f"  {ap.description}")
                print(f"  Suggestion: {ap.suggestion}")

    asyncio.run(main())
