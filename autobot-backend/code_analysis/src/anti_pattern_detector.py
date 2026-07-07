# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import Severity  # #7253: consolidated onto canonical (#6689)

# Anti-pattern severity → 0-100 integer score. Kept as a module-level helper
# rather than an enum method so the canonical `Severity` enum stays clean
# (canonical `to_score()` returns 0.0–0.9 floats, a different scale).
_ANTI_PATTERN_SCORES: Dict[Severity, int] = {
    Severity.CRITICAL: 100,
    Severity.HIGH: 75,
    Severity.MEDIUM: 50,
    Severity.LOW: 25,
}

# Minimum occurrences of a pattern_type to be included in the systemic rollup.
_SYSTEMIC_THRESHOLD = 3


def anti_pattern_score(severity: Severity) -> int:
    """Numeric anti-pattern score for `severity` (higher = worse, 0-100 scale)."""
    return _ANTI_PATTERN_SCORES[severity]


def _build_systemic_rollup(
    sorted_patterns: "List[Any]",
    summary_by_type: Dict[str, int],
) -> "List[Dict[str, Any]]":
    """Return systemic pattern entries for types with count >= _SYSTEMIC_THRESHOLD.

    Each entry is {pattern_type, count, top_severity} where top_severity is the
    highest-scoring severity seen for that type.  Result is sorted by count desc
    so callers get "god_class ×14" style summaries first (#11171).
    """
    top_severity: Dict[str, int] = {}
    for ap in sorted_patterns:
        pt = ap.pattern_type.value
        score = anti_pattern_score(ap.severity)
        if score > top_severity.get(pt, 0):
            top_severity[pt] = score

    result = [
        {"pattern_type": pt, "count": cnt, "top_severity_score": top_severity.get(pt, 0)}
        for pt, cnt in summary_by_type.items()
        if cnt >= _SYSTEMIC_THRESHOLD
    ]
    result.sort(key=lambda e: e["count"], reverse=True)
    return result


# Initialize configuration
logger = get_logger(__name__)

# Issue #380: Module-level tuple for complexity calculation
_COMPLEXITY_BRANCH_TYPES = (ast.If, ast.While, ast.For, ast.ExceptHandler)

# Issue #1183: Module-level defaults extracted from analyze() to reduce function length
_DEFAULT_EXCLUDE_PATTERNS = [
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

# Issue #1183: Entry-point suffixes extracted from _detect_dead_code() to reduce function length
_ENTRY_POINT_SUFFIXES = (
    "Test",
    "Tests",
    "TestCase",
    "Handler",
    "View",
    "API",
    "Router",
)


# Issue #6748: Vue <script setup> composable-opportunity detector regexes
_VUE_SCRIPT_SETUP_RE = re.compile(r"<script\b[^>]*\bsetup\b[^>]*>", re.IGNORECASE)
_VUE_SCRIPT_END_RE = re.compile(r"</script\s*>", re.IGNORECASE)
_VUE_COMP_CALL_RE = re.compile(
    r"(?:const|let|var)\s+\w+\s*(?::[^=]+)?\s*=\s*"
    r"(ref|reactive|computed|watch(?:Effect)?|on(?:Mounted|Unmounted|BeforeMount|Created))"
    r"(<[^>]*>)?\s*\(",
)
_COMPOSABLE_THRESHOLD = 5
_COMPOSABLE_EXCL_DIRS = frozenset({"composables", "node_modules", ".git", "__pycache__"})


def _extract_script_setup(content: str) -> str | None:
    """Return the text inside <script setup> … </script>, or None if absent."""
    m_start = _VUE_SCRIPT_SETUP_RE.search(content)
    if m_start is None:
        return None
    m_end = _VUE_SCRIPT_END_RE.search(content, m_start.end())
    if m_end is None:
        return None
    return content[m_start.end() : m_end.start()]


# Issue #6758: AST cache to avoid re-parsing files in cross-file finalize pass
# Cache key: (file_path, mtime) -> AST. This prevents double-parsing when both
# per-file and cross-file rules analyze the same file.
_AST_CACHE: Dict[Tuple[str, float], ast.AST] = {}
_AST_CACHE_MAX_SIZE = 10000  # Prevent unbounded memory growth


def get_or_parse_ast(file_path: str, content: str) -> ast.AST:
    """Get cached AST or parse and cache it (Issue #6758).

    Avoids re-parsing the same file when both per-file and cross-file
    rules need the AST. Uses file mtime as cache key component to detect
    file changes.

    Args:
        file_path: Path to the Python file
        content: File content (already read by caller)

    Returns:
        Parsed AST for the file
    """
    try:
        mtime = Path(file_path).stat().st_mtime
    except (OSError, FileNotFoundError):
        # If we can't stat the file, just parse and don't cache
        return ast.parse(content, filename=file_path)

    key = (file_path, mtime)

    # Return cached result if available
    if key in _AST_CACHE:
        return _AST_CACHE[key]

    # Parse and cache (with size limit to prevent memory leaks)
    if len(_AST_CACHE) >= _AST_CACHE_MAX_SIZE:
        # Clear cache when it reaches max size (simple strategy: purge all)
        # This ensures the cache doesn't grow unbounded on very large codebases
        _AST_CACHE.clear()

    tree = ast.parse(content, filename=file_path)
    _AST_CACHE[key] = tree
    return tree


def clear_ast_cache() -> None:
    """Clear the AST cache (Issue #6758).

    Call this at the start of a new scan run to avoid stale cached ASTs
    from previous analyses.
    """
    _AST_CACHE.clear()


class AntiPatternType(Enum):
    """Types of anti-patterns detected.

    Canonical SSOT (GH#6757): merged from code_analysis/src (per-file rules)
    and code_intelligence/anti_pattern_detection (cross-file/naming rules).
    Both modules previously kept diverged copies of this enum.
    """

    # --- Structural bloaters ---
    GOD_CLASS = "god_class"
    LONG_METHOD = "long_method"
    LONG_PARAMETER_LIST = "long_parameter_list"
    LARGE_FILE = "large_file"
    DEEP_NESTING = "deep_nesting"
    # DATA_CLUMP / DATA_CLUMPS: canonical name is DATA_CLUMP ("data_clump");
    # legacy code_intelligence used DATA_CLUMPS — kept as alias for migration.
    DATA_CLUMP = "data_clump"
    DATA_CLUMPS = "data_clumps"  # legacy alias from code_intelligence (GH#6757)
    PRIMITIVE_OBSESSION = "primitive_obsession"

    # --- Couplers ---
    FEATURE_ENVY = "feature_envy"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    SHOTGUN_SURGERY = "shotgun_surgery"
    MESSAGE_CHAINS = "message_chains"
    INAPPROPRIATE_INTIMACY = "inappropriate_intimacy"

    # --- Dispensables ---
    SPECULATIVE_GENERALITY = "speculative_generality"
    DEAD_CODE = "dead_code"
    LAZY_CLASS = "lazy_class"
    REFUSED_BEQUEST = "refused_bequest"
    # DUPLICATE_ABSTRACTION: legacy name from code_intelligence; canonical is
    # DUPLICATE_CLASS_SHAPE (added in #6684).
    DUPLICATE_CLASS_SHAPE = "duplicate_class_shape"
    DUPLICATE_ABSTRACTION = "duplicate_abstraction"  # legacy alias (GH#6757)
    DUPLICATE_ENUM = "duplicate_enum"

    # --- Naming issues (from code_intelligence NamingDetector) ---
    INCONSISTENT_NAMING = "inconsistent_naming"
    SINGLE_LETTER_VARIABLE = "single_letter_variable"
    MAGIC_NUMBER = "magic_number"

    # --- Code clarity ---
    COMPLEX_CONDITIONAL = "complex_conditional"
    MISSING_DOCSTRING = "missing_docstring"

    # --- LSP violations (Issue #6661) ---
    LSP_SIGNATURE_INCOMPATIBLE = "lsp_signature_incompatible"
    LSP_EXCEPTION_CONTRACT_CHANGED = "lsp_exception_contract_changed"

    # --- Architecture-level (Issue #6871, #6748) ---
    UNWIRED_TRACKER = "unwired_tracker"
    COMPOSABLE_OPPORTUNITY = "composable_opportunity"


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
            "severity_score": anti_pattern_score(self.severity),
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
    methods: List[ast.AST]  # ast.FunctionDef | ast.AsyncFunctionDef (#6661)
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
    # #11171: systemic rollup — pattern types with count >= _SYSTEMIC_THRESHOLD,
    # sorted by count desc.  Each entry: {pattern_type, count, top_severity}.
    systemic_patterns: List[Dict[str, Any]] = field(default_factory=list)

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
            "systemic_patterns": self.systemic_patterns,
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
    GOD_CLASS_LINE_THRESHOLD = 500  # alias for api.code_intelligence compat
    LONG_METHOD_THRESHOLD = 50
    LONG_PARAM_LIST_THRESHOLD = 5
    LONG_PARAMETER_THRESHOLD = 5  # alias for api.code_intelligence compat
    LARGE_FILE_THRESHOLD = 1000  # alias for api.code_intelligence compat
    DEEP_NESTING_THRESHOLD = 4  # alias for api.code_intelligence compat
    MESSAGE_CHAIN_THRESHOLD = 4  # alias for api.code_intelligence compat
    COMPLEX_CONDITIONAL_THRESHOLD = 3  # alias for api.code_intelligence compat
    MAGIC_NUMBER_THRESHOLD = 3  # alias for api.code_intelligence compat
    FEATURE_ENVY_THRESHOLD = 3
    LAZY_CLASS_METHOD_THRESHOLD = 2
    LAZY_CLASS_LOC_THRESHOLD = 20

    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        # #6733: removed `self.config = config` — referenced an undefined name
        # and was never read elsewhere in the module. Direct AntiPatternDetector()
        # instantiation now works in any context.

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
        start_time = time.time()

        # Issue #6758: Clear AST cache at start of new scan run
        clear_ast_cache()

        # #6734: use `is None` sentinel instead of `or` idiom — explicit
        # `exclude_patterns=[]` should disable exclusion, not silently
        # apply the defaults (the `or` form treated empty list as falsy).
        if patterns is None:
            patterns = ["**/*.py"]
        if exclude_patterns is None:
            # Issue #1183: Use module-level constant
            exclude_patterns = _DEFAULT_EXCLUDE_PATTERNS

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
        # Issue #6661: Liskov Substitution Principle violations
        anti_patterns.extend(await self._detect_lsp_violations())
        # Issue #6684: consolidation opportunities (missing-inheritance siblings to LSP)
        anti_patterns.extend(await self._detect_duplicate_enums())
        anti_patterns.extend(await self._detect_duplicate_class_shapes())
        # Issue #6871: modules with zero production callers (closed tracker, unwired code)
        anti_patterns.extend(await self._detect_unwired_trackers(root_path))
        # Issue #6748: repeated Vue reactive boilerplate that should be a composable
        anti_patterns.extend(await self._detect_composable_opportunities(root_path))

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

    async def analyze_cross_file_only(
        self,
        root_path: str = ".",
        patterns: List[str] = None,
        exclude_patterns: List[str] = None,
    ) -> List[AntiPatternInstance]:
        """Run only the cross-file rules (#6747).

        The four rules added by #6661 (LSP) and #6684 (consolidation) need
        a whole-codebase class index, but the production per-file
        ``AntiPatternDetector.analyze_file()`` in
        ``code_intelligence/anti_pattern_detector.py`` doesn't build one.
        This method does the parse pass once and runs ONLY the cross-file
        rules — letting the scanner finalize step surface them through
        ``/codebase/problems`` without re-running the per-file rules
        already covered by the production analyzer.

        Returns:
            List of AntiPatternInstance for ChromaDB persistence.
        """
        # Issue #6758: Clear AST cache at start of new scan run
        clear_ast_cache()

        # Default-arg handling: same `is None` discipline as analyze() (#6734)
        if patterns is None:
            patterns = ["**/*.py"]
        if exclude_patterns is None:
            exclude_patterns = _DEFAULT_EXCLUDE_PATTERNS

        await self._parse_codebase(root_path, patterns, exclude_patterns)

        results: List[AntiPatternInstance] = []
        results.extend(await self._detect_lsp_violations())
        results.extend(await self._detect_duplicate_enums())
        results.extend(await self._detect_duplicate_class_shapes())
        # Issue #6871: include unwired-tracker findings in the cross-file pass
        results.extend(await self._detect_unwired_trackers(root_path))
        # Issue #6748: repeated Vue reactive boilerplate
        results.extend(await self._detect_composable_opportunities(root_path))
        return results

    async def _parse_codebase(self, root_path: str, patterns: List[str], exclude_patterns: List[str]) -> None:
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
                if file_path.is_file() and not self._should_skip(file_path, exclude_set):
                    try:
                        module_info = await self._parse_file(str(file_path))
                        if module_info:
                            self.modules[module_info.name] = module_info
                            for cls_info in module_info.classes:
                                self.classes[f"{module_info.name}.{cls_info.name}"] = cls_info
                                self.all_defined_names.add(cls_info.name)
                            self.all_defined_names.update(module_info.functions)
                    except Exception as e:
                        logger.warning(f"Failed to parse {file_path}: {e}")

        # Build import graph (who imports whom)
        for module in self.modules.values():
            for imported in module.imports:
                if imported in self.modules:
                    self.modules[imported].is_imported_by.add(module.name)

    def _should_skip(self, file_path: Path, exclude_patterns: "frozenset[str] | List[str]") -> bool:
        """Check if file should be skipped.

        Issue #510: Accepts frozenset for O(1) membership check.
        """
        path_str = str(file_path)
        return any(pattern in path_str for pattern in exclude_patterns)

    async def _parse_file(self, file_path: str) -> ModuleInfo | None:
        """Parse a single Python file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Issue #6758: Use cache to avoid re-parsing in cross-file pass
            tree = get_or_parse_ast(file_path, content)
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
            functions = [node.name for node in ast.iter_child_nodes(tree) if isinstance(node, ast.FunctionDef)]

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

    @staticmethod
    def _extract_method_call_data(
        methods: List[ast.AST],  # ast.FunctionDef | ast.AsyncFunctionDef (#6661),
    ) -> Tuple[Dict[str, List[str]], Dict[str, int]]:
        """Extract method calls and external references from a list of AST methods.

        Issue #1183: Extracted from _analyze_class() to reduce function length.
        """
        method_calls: Dict[str, List[str]] = {}
        external_references: Dict[str, int] = {}
        for method in methods:
            calls = []
            for child in ast.walk(method):
                if isinstance(child, ast.Attribute):
                    if isinstance(child.value, ast.Name):
                        if child.value.id == "self":
                            calls.append(f"self.{child.attr}")
                        else:
                            ref_name = child.value.id
                            external_references[ref_name] = external_references.get(ref_name, 0) + 1
                            calls.append(f"{ref_name}.{child.attr}")
            method_calls[method.name] = calls
        return method_calls, external_references

    def _analyze_class(self, node: ast.ClassDef, file_path: str, content: str) -> ClassInfo | None:
        """Analyze a class definition"""
        try:
            # Extract methods (#6661: include AsyncFunctionDef so the LSP
            # detector can catch sync/async signature mismatches between
            # parent and child overrides — previously async methods were
            # silently skipped by every existing detector too).
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

            # Extract attributes (from __init__ and class body)
            attributes = set()
            for method in methods:
                if method.name == "__init__":
                    for child in ast.walk(method):
                        if isinstance(child, ast.Attribute):
                            if isinstance(child.value, ast.Name) and child.value.id == "self":
                                attributes.add(child.attr)

            # Extract base classes
            base_classes = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_classes.append(base.id)
                elif isinstance(base, ast.Attribute):
                    base_classes.append(base.attr)

            # Issue #1183: Delegate to extracted helper to reduce function length
            method_calls, external_references = self._extract_method_call_data(methods)

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
            score += min(30, (cls_info.method_count - self.GOD_CLASS_METHOD_THRESHOLD) * 2)

        # Attribute count score - Issue #372: use property
        if cls_info.attribute_count > self.GOD_CLASS_ATTR_THRESHOLD:
            score += min(20, (cls_info.attribute_count - self.GOD_CLASS_ATTR_THRESHOLD) * 2)

        # Lines of code score
        if cls_info.lines_of_code > self.GOD_CLASS_LOC_THRESHOLD:
            score += min(30, (cls_info.lines_of_code - self.GOD_CLASS_LOC_THRESHOLD) // 50)

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
            suggestions.append("Group related attributes into data classes or value objects")

        if cls_info.complexity > 50:
            suggestions.append("Extract complex logic into strategy or command patterns")

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
                            severity=(Severity.MEDIUM if external_refs < 10 else Severity.HIGH),
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

    def _analyze_feature_envy(self, method: ast.FunctionDef, cls_info: ClassInfo) -> Tuple[str, int, int] | None:
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
            dep_graph[module.name] = set(imp for imp in module.imports if imp in self.modules)

        # Find cycles using DFS
        cycles = self._find_all_cycles(dep_graph)

        for cycle in cycles:
            cycle_str = " -> ".join(cycle + [cycle[0]])
            issues.append(
                AntiPatternInstance(
                    pattern_type=AntiPatternType.CIRCULAR_DEPENDENCY,
                    severity=Severity.HIGH if len(cycle) > 2 else Severity.MEDIUM,
                    file_path=(self.modules[cycle[0]].file_path if cycle[0] in self.modules else ""),
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
                            severity=(Severity.MEDIUM if param_count < 8 else Severity.HIGH),
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
                params = tuple(sorted(arg.arg for arg in method.args.args if arg.arg not in ("self", "cls")))

                if len(params) >= 3:  # Only consider groups of 3+
                    if params not in param_groups:
                        param_groups[params] = []
                    param_groups[params].append(f"{cls_info.name}.{method.name}")

        # Report param groups that appear multiple times
        for params, methods in param_groups.items():
            if len(methods) >= 3:  # Appears in 3+ methods
                _cls_name = methods[0].split(".")[0] if methods else ""
                _cls = next((v for v in self.classes.values() if v.name == _cls_name), None)
                issues.append(
                    AntiPatternInstance(
                        pattern_type=AntiPatternType.DATA_CLUMP,
                        severity=Severity.MEDIUM if len(methods) > 5 else Severity.LOW,
                        file_path=(_cls.file_path if _cls else ""),
                        line_number=1,
                        entity_name=", ".join(params),
                        description=(f"Parameter group ({', '.join(params)}) appears in {len(methods)} methods"),
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

    # ========== Liskov Substitution Principle Detection (Issue #6661) ==========

    # Names that look like ABC/Protocol stubs in the parent — children adding
    # behavior on top of these is the *purpose*, not an LSP violation.
    _ABSTRACT_PARENT_NAMES = frozenset({"ABC", "ABCMeta", "Protocol", "RuntimeProtocol"})
    _MIXIN_SUFFIXES = ("Mixin", "Protocol", "ABC")

    def _is_async_method(self, method: ast.AST) -> bool:
        """True when the method is declared `async def`."""
        return isinstance(method, ast.AsyncFunctionDef)

    def _required_positional_count(self, method: ast.AST) -> int:
        """Count positional args without defaults (excluding ``self``/``cls``)."""
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return 0
        args = method.args.args
        # Strip the bound argument (self/cls) if present
        if args and args[0].arg in ("self", "cls"):
            args = args[1:]
        defaults = method.args.defaults or []
        return max(0, len(args) - len(defaults))

    def _total_positional_count(self, method: ast.AST) -> int:
        """Count total positional slots — required + with-default — excluding
        ``self``/``cls``. A child can WIDEN preconditions by adding defaults,
        which is correct LSP; the comparison that matters is whether the child
        accepts as many positional slots as the parent requires (#6755)."""
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return 0
        args = method.args.args
        if args and args[0].arg in ("self", "cls"):
            args = args[1:]
        return len(args)

    @staticmethod
    def _is_docstring_stmt(stmt: ast.stmt) -> bool:
        """True when the statement is a bare string literal (function docstring)."""
        return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)

    @staticmethod
    def _is_stub_statement(stmt: ast.stmt) -> bool:
        """True when the statement is a stub form: ``pass`` / ``...`` /
        ``raise NotImplementedError``."""
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            if stmt.value.value is Ellipsis or stmt.value.value is None:
                return True
        if isinstance(stmt, ast.Raise):
            exc = stmt.exc
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                return True
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                if exc.func.id == "NotImplementedError":
                    return True
        return False

    def _is_abstract_or_stub(self, method: ast.AST) -> bool:
        """Parent overrides should be skipped if the parent body is an
        abstract / Protocol stub — children must add behavior.

        Recognized stub bodies (a leading docstring is allowed and ignored):
          * ``pass``
          * ``...``  (Ellipsis as expression statement)
          * ``raise NotImplementedError`` / ``raise NotImplementedError(...)``
          * docstring-only body
          * docstring + any of the above
        """
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return True
        # @abstractmethod / @abc.abstractmethod
        for dec in method.decorator_list:
            name = ""
            if isinstance(dec, ast.Name):
                name = dec.id
            elif isinstance(dec, ast.Attribute):
                name = dec.attr
            if "abstract" in name.lower():
                return True
        body = method.body
        if not body:
            return True

        # Strip an optional leading docstring; the remaining body must be
        # either empty (docstring-only) or a single stub statement.
        non_doc_body = body[1:] if self._is_docstring_stmt(body[0]) else list(body)
        if not non_doc_body:
            return True  # docstring-only stub
        if len(non_doc_body) == 1 and self._is_stub_statement(non_doc_body[0]):
            return True
        return False

    def _is_skippable_class(self, cls_info: ClassInfo) -> bool:
        """Mixins / Protocols / pure ABCs are not subject to LSP overrides."""
        if any(cls_info.name.endswith(suf) for suf in self._MIXIN_SUFFIXES):
            return True
        if cls_info.has_base_class(*self._ABSTRACT_PARENT_NAMES):
            return True
        return False

    def _exception_types_raised(self, method: ast.AST) -> Set[str]:
        """Static set of exception type names ``raise``d directly in body."""
        names: Set[str] = set()
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return names
        for node in ast.walk(method):
            if isinstance(node, ast.Raise) and node.exc is not None:
                exc = node.exc
                if isinstance(exc, ast.Name):
                    names.add(exc.id)
                elif isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                    names.add(exc.func.id)
                elif isinstance(exc, ast.Call) and isinstance(exc.func, ast.Attribute):
                    names.add(exc.func.attr)
        return names

    def _docstring_mentions_raises(self, method: ast.AST, exc_name: str) -> bool:
        """Best-effort: parent's docstring documents the exception type."""
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        doc = ast.get_docstring(method) or ""
        return exc_name in doc

    def _find_parent_method(self, parent: ClassInfo, name: str) -> ast.AST | None:
        for m in parent.methods:
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == name:
                return m
        return None

    def _resolve_parent(self, child: ClassInfo) -> ClassInfo | None:
        """Look up the FIRST in-codebase parent class. Returns None when
        the parent is external (stdlib/library) — those are out of scope."""
        for base_name in child.base_classes:
            for full_name, info in self.classes.items():
                if info.name == base_name:
                    return info
        return None

    async def _detect_lsp_violations(self) -> List[AntiPatternInstance]:
        """Detect Liskov Substitution Principle violations across class
        hierarchies. Two high-confidence rules (Issue #6661):

        * ``LSP_SIGNATURE_INCOMPATIBLE`` — sync/async mismatch between an
          override and its parent, or required-param removal.
        * ``LSP_EXCEPTION_CONTRACT_CHANGED`` — the override raises an
          exception type that the parent neither raises nor mentions in
          its docstring's Raises clause.

        Excludes ABC/Protocol stubs, ``@abstractmethod`` parents, and
        Mixin/Protocol classes — adding behavior to those is the *point*
        of inheritance, not a contract break.
        """
        issues: List[AntiPatternInstance] = []

        for full_name, child in self.classes.items():
            if self._is_skippable_class(child):
                continue
            parent = self._resolve_parent(child)
            if parent is None or self._is_skippable_class(parent):
                continue

            for child_method in child.methods:
                if not isinstance(child_method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                parent_method = self._find_parent_method(parent, child_method.name)
                if parent_method is None:
                    continue
                if self._is_abstract_or_stub(parent_method):
                    continue

                # --- Signature: sync/async mismatch ---
                if self._is_async_method(child_method) != self._is_async_method(parent_method):
                    issues.append(
                        AntiPatternInstance(
                            pattern_type=AntiPatternType.LSP_SIGNATURE_INCOMPATIBLE,
                            severity=Severity.HIGH,
                            file_path=child.file_path,
                            line_number=child_method.lineno,
                            entity_name=f"{child.name}.{child_method.name}",
                            description=(
                                f"Override of {parent.name}.{child_method.name} changes "
                                f"sync/async: parent is "
                                f"{'async' if self._is_async_method(parent_method) else 'sync'}, "
                                f"child is "
                                f"{'async' if self._is_async_method(child_method) else 'sync'}. "
                                "Polymorphic callers will silently get an unawaited coroutine "
                                "(or fail to await) depending on which subclass they hold."
                            ),
                            metrics={
                                "parent_class": parent.name,
                                "parent_file": parent.file_path,
                                "parent_async": self._is_async_method(parent_method),
                                "child_async": self._is_async_method(child_method),
                            },
                            suggestion=(
                                "Unify the signature: if any subclass needs I/O, promote "
                                "the parent contract to ``async def``; the in-process "
                                "implementations can simply ``return value`` inside the "
                                "coroutine. See #6659 for a worked example."
                            ),
                            refactoring_effort="low",
                            related_entities=[parent.name, parent.file_path],
                        )
                    )

                # --- Signature: child rejects positional args parent accepts ---
                # LSP correctness: a child override can WIDEN preconditions
                # (accept more inputs via defaults) but must NOT NARROW them.
                # The original bug class (#6660) was a child with `def __init__(self):`
                # under a parent with `def __init__(self, agent_type, ...):` —
                # `cls(agent_type)` crashes on the child because it has no slot
                # for that positional. The check is: count the child's TOTAL
                # positional slots (required + optional with defaults), and
                # compare against the parent's REQUIRED count. If the child
                # has fewer slots than the parent requires, factory calls
                # against the parent's required-positional surface will fail.
                child_total_positional = self._total_positional_count(child_method)
                parent_required = self._required_positional_count(parent_method)
                if child_total_positional < parent_required:
                    issues.append(
                        AntiPatternInstance(
                            pattern_type=AntiPatternType.LSP_SIGNATURE_INCOMPATIBLE,
                            severity=Severity.HIGH,
                            file_path=child.file_path,
                            line_number=child_method.lineno,
                            entity_name=f"{child.name}.{child_method.name}",
                            description=(
                                f"Override of {parent.name}.{child_method.name} drops required positional params: "
                                f"accepts {child_total_positional} positional args but the parent "
                                f"requires {parent_required}. A factory call like "
                                "``cls(arg1, arg2)`` against the parent contract will "
                                "crash with TypeError on this subclass."
                            ),
                            metrics={
                                "parent_class": parent.name,
                                "parent_file": parent.file_path,
                                "parent_required_args": parent_required,
                                "child_total_positional_args": child_total_positional,
                            },
                            suggestion=(
                                "Restore the parent's positional params with sensible "
                                "defaults so factory callers keep working. See #6660 for "
                                "a worked example with __init__."
                            ),
                            refactoring_effort="low",
                            related_entities=[parent.name, parent.file_path],
                        )
                    )

                # --- Exception contract: child raises type parent doesn't ---
                child_excs = self._exception_types_raised(child_method)
                parent_excs = self._exception_types_raised(parent_method)
                new_excs = child_excs - parent_excs
                # Filter out exceptions the parent's docstring documents
                undocumented = {e for e in new_excs if not self._docstring_mentions_raises(parent_method, e)}
                if undocumented:
                    issues.append(
                        AntiPatternInstance(
                            pattern_type=AntiPatternType.LSP_EXCEPTION_CONTRACT_CHANGED,
                            severity=Severity.HIGH,
                            file_path=child.file_path,
                            line_number=child_method.lineno,
                            entity_name=f"{child.name}.{child_method.name}",
                            description=(
                                f"Override of {parent.name}.{child_method.name} raises "
                                f"{sorted(undocumented)} which the parent neither raises "
                                "nor documents in its Raises clause. Polymorphic callers "
                                "against the parent contract have no reason to catch these."
                            ),
                            metrics={
                                "parent_class": parent.name,
                                "parent_file": parent.file_path,
                                "new_exceptions": sorted(undocumented),
                            },
                            suggestion=(
                                "Either return an error value matching the parent's return "
                                "contract, or promote the new exception into the parent's "
                                "documented Raises clause and propagate it through every "
                                "sibling subclass. See #6658 for a worked example."
                            ),
                            refactoring_effort="medium",
                            related_entities=[parent.name, parent.file_path],
                        )
                    )

        return issues

    # ========== Consolidation Opportunity Detection (Issue #6684) ==========

    _ENUM_BASE_NAMES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "ReprEnum"})
    # Class-shape rule: skip patterns where shared method names is by design
    _SHAPE_SKIP_BASE_NAMES = frozenset(
        {
            "BaseModel",  # Pydantic — sharing field names is fine
            "Enum",
            "IntEnum",
            "StrEnum",
            "Exception",
            "BaseException",
            "TypedDict",
            "NamedTuple",
        }
    )
    # #6780: lowered from 5 → 2 so small identical-shape boilerplate clusters
    # are detected.  Classes with fewer than _SHAPE_MIN_METHODS_STRICT methods
    # use a strict Jaccard threshold of 1.0 (exact match) to avoid false
    # positives for FastAPI endpoint classes that share a few method names by
    # design.  The relaxed threshold applies only above _SHAPE_MIN_METHODS_STRICT.
    _SHAPE_MIN_METHODS = 2
    _SHAPE_MIN_METHODS_STRICT = 5
    _SHAPE_JACCARD_THRESHOLD = 0.7
    # #6755 round 3: bumped from 0.7 to 0.85 to suppress priority-scale
    # FPs. Enums like ``SandboxSecurityLevel`` (high/low/medium),
    # ``WorkflowPriority`` (high/low/normal/urgent), ``KnowledgePriority``
    # (critical/high/low/medium) share value strings but describe
    # semantically distinct scales — not duplicates. At 0.85, only
    # near-identical value sets get flagged. Combined with #7501's
    # parent-child / Protocol-impl exclusions, autobot-backend
    # ``duplicate_enum`` findings dropped 432 → 3 → 0.
    _ENUM_JACCARD_THRESHOLD = 0.85
    _ENUM_MIN_VALUES = 3

    def _is_enum_class(self, cls_info: ClassInfo) -> bool:
        """True when the class inherits from an Enum-family base."""
        return any(b in self._ENUM_BASE_NAMES for b in cls_info.base_classes)

    def _enum_value_set(self, cls_info: ClassInfo) -> Set[str]:
        """Extract the set of enum *value* string literals from a class body.

        Uses cached AST from per-file pass (Issue #6758) to avoid re-parsing.
        Falls back to attribute names when values are not string literals —
        that still gives a useful overlap signal.
        """
        try:
            with open(cls_info.file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Issue #6758: Use cache to avoid re-parsing in cross-file pass
            tree = get_or_parse_ast(cls_info.file_path, content)
        except Exception:
            return set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != cls_info.name:
                continue
            values: Set[str] = set()
            for stmt in node.body:
                target_name: str | None = None
                value_node: ast.AST | None = None
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    tgt = stmt.targets[0]
                    if isinstance(tgt, ast.Name):
                        target_name = tgt.id
                    value_node = stmt.value
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    target_name = stmt.target.id
                    value_node = stmt.value
                if target_name is None or target_name.startswith("_"):
                    continue
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    values.add(value_node.value.lower())
                else:
                    # Fall back to the attribute name (lowered) — gives a
                    # useful signal for `auto()` enums and ints alike.
                    values.add(target_name.lower())
            return values
        return set()

    @staticmethod
    def _jaccard(a: Set[str], b: Set[str]) -> float:
        union = a | b
        if not union:
            return 0.0
        return len(a & b) / len(union)

    def _shares_base_class(self, a: ClassInfo, b: ClassInfo) -> bool:
        """True when a and b share at least one base class (already related)."""
        if not a.base_classes or not b.base_classes:
            return False
        return bool(set(a.base_classes) & set(b.base_classes))

    @staticmethod
    def _is_parent_child_pair(a: ClassInfo, b: ClassInfo) -> bool:
        """#7501: True when one class inherits from the other.

        AST-resolution is local-only — we match by simple class name
        against the other's ``base_classes`` list. That catches the
        common direct-inheritance case (``class Child(Parent):``)
        which is the bulk of the false positives in #6755.

        Indirect inheritance (Parent → Mid → Child) and bases imported
        under an alias are not caught here; those need cross-file
        symbol resolution beyond what ``ClassInfo`` records today.
        """
        return a.name in b.base_classes or b.name in a.base_classes

    @staticmethod
    def _is_protocol_impl_pair(a: ClassInfo, b: ClassInfo) -> bool:
        """#7501: True when one of the pair is a ``typing.Protocol``.

        ``Protocol`` is structural-by-design — any class with matching
        method names is intended to satisfy it (PEP 544). Flagging this
        as ``duplicate_class_shape`` produces false positives (e.g.
        ``ITaskStorage`` Protocol vs ``TaskStorage`` impl in #6755).

        We match "Protocol" anywhere in either class's base_classes
        list, which covers both the bare ``Protocol`` and the common
        ``Protocol[T]`` parametrised form (parser drops the subscript
        and records the bare name).
        """
        return "Protocol" in a.base_classes or "Protocol" in b.base_classes

    async def _detect_duplicate_enums(self) -> List[AntiPatternInstance]:
        """Cluster enum classes whose value sets overlap above threshold.

        Issue #6684: AutoBot's ``constants/status_enums.py`` is the canonical
        home for status values, but many modules redeclare overlapping enums
        (StepStatus, TaskStatus, PhasePromotionStatus, ...).  This detector
        flags any pair of enum classes whose value sets have Jaccard
        similarity >= 0.7 with at least 3 shared values.
        """
        issues: List[AntiPatternInstance] = []

        enum_data: List[Tuple[str, ClassInfo, Set[str]]] = []
        for full_name, cls_info in self.classes.items():
            if not self._is_enum_class(cls_info):
                continue
            values = self._enum_value_set(cls_info)
            if len(values) >= self._ENUM_MIN_VALUES:
                enum_data.append((full_name, cls_info, values))

        # O(n^2) over enums only — n is small in practice (~50 in this repo).
        seen_pairs: Set[Tuple[str, str]] = set()
        for i, (full_a, cls_a, vals_a) in enumerate(enum_data):
            for full_b, cls_b, vals_b in enum_data[i + 1 :]:
                # Skip if one inherits from the other (already canonical-vs-extension)
                if cls_a.name in cls_b.base_classes or cls_b.name in cls_a.base_classes:
                    continue
                similarity = self._jaccard(vals_a, vals_b)
                if similarity < self._ENUM_JACCARD_THRESHOLD:
                    continue
                shared = sorted(vals_a & vals_b)
                pair_key = tuple(sorted([full_a, full_b]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                issues.append(
                    AntiPatternInstance(
                        pattern_type=AntiPatternType.DUPLICATE_ENUM,
                        severity=Severity.MEDIUM,
                        file_path=cls_a.file_path,
                        line_number=cls_a.line_number,
                        entity_name=cls_a.name,
                        description=(
                            f"Enum '{cls_a.name}' overlaps {len(vals_a & vals_b)}/"
                            f"{len(vals_a | vals_b)} values with '{cls_b.name}' in "
                            f"{cls_b.file_path} (Jaccard={similarity:.2f}). "
                            f"Shared values: {shared[:5]}"
                            f"{' (truncated)' if len(shared) > 5 else ''}."
                        ),
                        metrics={
                            "other_enum": cls_b.name,
                            "other_file": cls_b.file_path,
                            "jaccard_similarity": round(similarity, 3),
                            "shared_value_count": len(vals_a & vals_b),
                            "union_size": len(vals_a | vals_b),
                            "shared_values": shared,
                        },
                        suggestion=(
                            "Consolidate into a single canonical enum (see "
                            "constants/status_enums.py for the existing pattern). "
                            "Importing the canonical enum eliminates value drift "
                            "and makes cross-module status comparisons type-safe."
                        ),
                        refactoring_effort="medium",
                        related_entities=[cls_b.name, cls_b.file_path],
                    )
                )

        return issues

    async def _detect_duplicate_class_shapes(self) -> List[AntiPatternInstance]:
        """Flag class pairs that share method-name sets above threshold but
        DO NOT share a base class.  Indicates a missing extracted base /
        Mixin / Protocol that should formalise the shared contract.

        Excludes Pydantic models, exceptions, NamedTuples, TypedDicts —
        these all naturally share method names by design.
        """
        issues: List[AntiPatternInstance] = []

        candidates: List[Tuple[str, ClassInfo, Set[str]]] = []
        for full_name, cls_info in self.classes.items():
            # Skip enums and exception trees — different rules apply
            if self._is_enum_class(cls_info):
                continue
            if cls_info.has_base_class(*self._SHAPE_SKIP_BASE_NAMES):
                continue
            method_names = {
                m.name
                for m in cls_info.methods
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_")
            }
            if len(method_names) < self._SHAPE_MIN_METHODS:
                continue
            candidates.append((full_name, cls_info, method_names))

        seen_pairs: Set[Tuple[str, str]] = set()
        for i, (full_a, cls_a, names_a) in enumerate(candidates):
            for full_b, cls_b, names_b in candidates[i + 1 :]:
                if self._shares_base_class(cls_a, cls_b):
                    continue
                # #7501: skip parent ↔ child inheritance pairs. Subclass
                # method-name overlap with parent is by construction
                # (override), not a missing-base-class smell.
                if self._is_parent_child_pair(cls_a, cls_b):
                    continue
                # #7501: skip Protocol + structural-impl pairs. ``Protocol``
                # is designed to be satisfied by structural matching (PEP 544);
                # an impl class sharing the Protocol's method names is the
                # intended relationship, not a duplicate.
                if self._is_protocol_impl_pair(cls_a, cls_b):
                    continue
                # #6780: small classes (below strict threshold) require exact
                # match (Jaccard=1.0) to suppress FastAPI-handler false positives.
                threshold = (
                    self._SHAPE_JACCARD_THRESHOLD
                    if max(len(names_a), len(names_b)) >= self._SHAPE_MIN_METHODS_STRICT
                    else 1.0
                )
                similarity = self._jaccard(names_a, names_b)
                if similarity < threshold:
                    continue
                shared = sorted(names_a & names_b)
                pair_key = tuple(sorted([full_a, full_b]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                issues.append(
                    AntiPatternInstance(
                        pattern_type=AntiPatternType.DUPLICATE_CLASS_SHAPE,
                        severity=Severity.LOW,
                        file_path=cls_a.file_path,
                        line_number=cls_a.line_number,
                        entity_name=cls_a.name,
                        description=(
                            f"Class '{cls_a.name}' shares {len(names_a & names_b)}/"
                            f"{len(names_a | names_b)} public method names with "
                            f"'{cls_b.name}' in {cls_b.file_path} "
                            f"(Jaccard={similarity:.2f}) but they do NOT share a "
                            f"base class.  Suggests a missing extracted base / "
                            f"Mixin / Protocol.  Shared methods: {shared[:5]}"
                            f"{' (truncated)' if len(shared) > 5 else ''}."
                        ),
                        metrics={
                            "other_class": cls_b.name,
                            "other_file": cls_b.file_path,
                            "jaccard_similarity": round(similarity, 3),
                            "shared_method_count": len(names_a & names_b),
                            "union_size": len(names_a | names_b),
                            "shared_methods": shared,
                        },
                        suggestion=(
                            "Extract a shared base class (Template Method) or a "
                            "Protocol describing the common interface.  See "
                            "BaseIntegration → SlackIntegration / JiraIntegration "
                            "for the canonical pattern in this repo."
                        ),
                        refactoring_effort="medium",
                        related_entities=[cls_b.name, cls_b.file_path],
                    )
                )

        return issues

    # ========== Unwired Tracker Detection (Issue #6871) ==========

    # Regex matching issue/tracker references in file headers (first N lines).
    # Mirrors the ISSUE_REF_RE in pipeline-scripts/audit_unwired_trackers.py
    # but scoped to the most common forms for simplicity.
    _ISSUE_REF_RE = re.compile(
        r"(?:^|\W)(?:Issue|Closes|Fixes|Resolves|See|Related|Tracking)\s+#(\d+)\b"
        r"|(?:^|\s)#(\d+):"
        r"|\(#(\d+)\)"
        r"|\[#(\d+)\]"
        r"|/issues/(\d+)\b",
        re.MULTILINE,
    )

    # Ambiguous module stems — skipped to avoid false positives (mirrors audit script).
    _AMBIGUOUS_STEMS = frozenset(
        {
            "__init__",
            "types",
            "utils",
            "common",
            "base",
            "config",
            "constants",
            "helpers",
            "main",
            "index",
        }
    )

    # Number of lines from the top of each file to scan for issue references.
    _TRACKER_SCAN_LINES = 40

    def _extract_issue_refs(self, file_path: Path) -> List[int]:
        """Return list of issue numbers found in the first _TRACKER_SCAN_LINES of the file."""
        try:
            with file_path.open("r", encoding="utf-8") as f:
                head = "".join(line for _, line in zip(range(self._TRACKER_SCAN_LINES), f))
        except (OSError, UnicodeDecodeError):
            return []
        refs: List[int] = []
        for m in self._ISSUE_REF_RE.finditer(head):
            n = m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(5)
            if n:
                refs.append(int(n))
        # Dedupe while preserving order
        return list(dict.fromkeys(refs))

    async def _detect_unwired_trackers(self, root_path: str = ".") -> List[AntiPatternInstance]:
        """Detect Python modules whose header cites an issue tracker but has
        zero production callers (Issue #6871 — Tier 4 of #6836).

        A module is flagged when:
        - Its first _TRACKER_SCAN_LINES contain an Issue #N reference, AND
        - Its stem is not in _AMBIGUOUS_STEMS, AND
        - No other non-test Python module in root_path imports it.

        Severity is LOW: the module may still be valid scaffolding. The finding
        guides human review rather than demanding immediate deletion.
        """
        issues: List[AntiPatternInstance] = []
        root = Path(root_path)
        if not root.exists():
            return issues

        # Collect all Python source files (non-test) under root_path.
        py_files: List[Path] = []
        for f in root.rglob("*.py"):
            path_str = str(f)
            if any(pat in path_str for pat in _DEFAULT_EXCLUDE_PATTERNS):
                continue
            py_files.append(f)

        # Separate candidates (files with issue refs) from the full corpus.
        # We build a lookup: stem → set of files that import it (by stem name).
        stem_to_importers: dict = {}
        for f in py_files:
            stem = f.stem
            if stem in self._AMBIGUOUS_STEMS:
                continue
            if stem not in stem_to_importers:
                stem_to_importers[stem] = set()

        # Single pass: parse each file for its imports to build the caller index.
        for f in py_files:
            try:
                content = f.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(f))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_stem = alias.name.split(".")[-1]
                        if imported_stem in stem_to_importers:
                            stem_to_importers[imported_stem].add(str(f))
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_stem = node.module.split(".")[-1]
                    if imported_stem in stem_to_importers:
                        stem_to_importers[imported_stem].add(str(f))
                    # also check names imported from the module
                    for alias in node.names:
                        name_stem = alias.name
                        if name_stem in stem_to_importers:
                            stem_to_importers[name_stem].add(str(f))

        # Identify candidate files with issue refs AND zero external callers.
        for f in py_files:
            stem = f.stem
            if stem in self._AMBIGUOUS_STEMS:
                continue
            refs = self._extract_issue_refs(f)
            if not refs:
                continue
            callers = stem_to_importers.get(stem, set())
            # Remove self-reference
            callers = {c for c in callers if c != str(f)}
            if callers:
                continue  # has at least one production caller

            issues.append(
                AntiPatternInstance(
                    pattern_type=AntiPatternType.UNWIRED_TRACKER,
                    severity=Severity.LOW,
                    file_path=str(f),
                    line_number=1,
                    entity_name=stem,
                    description=(
                        f"Module '{stem}' cites tracker #{refs[0]} in its header "
                        f"but has 0 production callers in the analyzed codebase. "
                        f"The associated tracker may have been closed prematurely."
                    ),
                    metrics={
                        "tracker_number": refs[0],
                        "all_tracker_refs": refs,
                        "production_callers": 0,
                    },
                    suggestion=(
                        "Either wire this module into a production code path, "
                        f"reopen tracker #{refs[0]} if the integration was unfinished, "
                        "or document the deliberate deferral with a comment."
                    ),
                    refactoring_effort="low",
                )
            )

        logger.info("[#6871] Unwired-tracker scan: %d findings in %s", len(issues), root_path)
        return issues

    # ========== COMPOSABLE_OPPORTUNITY detector (#6748) ==========

    async def _detect_composable_opportunities(self, root_path: str = ".") -> List[AntiPatternInstance]:
        """Cluster Vue components that repeat the same reactive boilerplate.

        Walks autobot-frontend/src/components/**/*.vue, extracts each
        <script setup> block, normalises the composition-API calls into a
        frozenset signature, and flags any signature that appears in
        _COMPOSABLE_THRESHOLD or more distinct component files.
        """
        frontend_root = self._find_vue_components_root(root_path)
        if frontend_root is None:
            return []

        sig_to_files: Dict[str, List[str]] = {}
        for vue_file in sorted(frontend_root.rglob("*.vue")):
            if any(part in _COMPOSABLE_EXCL_DIRS for part in vue_file.parts):
                continue
            sig = self._vue_file_signature(vue_file)
            if not sig:
                continue
            sig_key = "|".join(sorted(sig))
            sig_to_files.setdefault(sig_key, []).append(str(vue_file))

        results: List[AntiPatternInstance] = []
        for sig_key, files in sig_to_files.items():
            if len(files) < _COMPOSABLE_THRESHOLD:
                continue
            sig = frozenset(sig_key.split("|"))
            name = self._suggest_composable_name(sig)
            results.append(
                AntiPatternInstance(
                    pattern_type=AntiPatternType.COMPOSABLE_OPPORTUNITY,
                    severity=Severity.LOW,
                    file_path=files[0],
                    line_number=1,
                    entity_name=name,
                    description=(
                        f"{len(files)} components share the same reactive boilerplate "
                        f"({sig_key[:80]}). Extract to {name}()."
                    ),
                    metrics={
                        "component_count": len(files),
                        "files": files[:10],
                        "pattern_hash": sig_key,
                    },
                    suggestion=(
                        f"Create `composables/{name}.ts` and replace the repeated "
                        f"reactive block with a single import."
                    ),
                    refactoring_effort="low",
                    related_entities=files[:10],
                )
            )

        logger.info("[#6748] Composable-opportunity scan: %d findings", len(results))
        return results

    @staticmethod
    def _find_vue_components_root(root_path: str) -> Path | None:
        """Walk up from root_path to find autobot-frontend/src/components/."""
        p = Path(root_path).resolve()
        for _ in range(6):
            candidate = p / "autobot-frontend" / "src" / "components"
            if candidate.is_dir():
                return candidate
            p = p.parent
        return None

    @staticmethod
    def _vue_file_signature(vue_file: Path) -> frozenset[str]:
        """Return normalised frozenset of composition-API calls in vue_file's <script setup>."""
        try:
            content = vue_file.read_text(encoding="utf-8")
        except OSError:
            return frozenset()
        script = _extract_script_setup(content)
        if script is None:
            return frozenset()
        calls: Set[str] = set()
        for m in _VUE_COMP_CALL_RE.finditer(script):
            api = m.group(1)
            raw_generic = (m.group(2) or "").strip("<> ")
            # Replace | with _or_ so the |-joined sig_key can be safely split
            generic = raw_generic.replace(" ", "").replace("|", "_or_").lower()
            calls.add(f"{api}_{generic}" if generic else api)
        return frozenset(calls)

    @staticmethod
    def _suggest_composable_name(sig: frozenset[str]) -> str:
        """Heuristically derive a composable name from its signature."""
        normalised = {s.lower() for s in sig}
        # loading + error pattern
        if any("string" in s and "null" in s for s in normalised) and any(
            s in ("ref", "ref_bool", "ref_false", "ref_true", "ref_boolean") for s in normalised
        ):
            return "useLoadingState"
        ref_count = sum(1 for s in normalised if s.startswith("ref"))
        if ref_count >= 2:
            return "useSharedState"
        if any("watch" in s for s in normalised):
            return "useReactiveWatcher"
        return "useSharedPattern"

    # ========== Report Generation ==========

    def _generate_report(self, anti_patterns: List[AntiPatternInstance], analysis_time: float) -> AntiPatternReport:
        """Generate comprehensive anti-pattern report.

        Findings are ranked by prevalence × severity so a pattern_type that
        appears many times across the codebase rises above a single one-off
        finding of nominally higher severity (#11171).
        """
        # Count by severity
        critical_count = sum(1 for ap in anti_patterns if ap.severity == Severity.CRITICAL)
        high_count = sum(1 for ap in anti_patterns if ap.severity == Severity.HIGH)
        medium_count = sum(1 for ap in anti_patterns if ap.severity == Severity.MEDIUM)
        low_count = sum(1 for ap in anti_patterns if ap.severity == Severity.LOW)

        # Summary by type
        summary_by_type: Dict[str, int] = {}
        for ap in anti_patterns:
            pattern_type = ap.pattern_type.value
            summary_by_type[pattern_type] = summary_by_type.get(pattern_type, 0) + 1

        # #11171: rank each finding by freq(pattern_type) × severity_score.
        # Stable secondary sort on severity_score keeps same-rank entries ordered
        # by their individual severity (highest first).
        sorted_patterns = sorted(
            anti_patterns,
            key=lambda x: (
                summary_by_type[x.pattern_type.value] * anti_pattern_score(x.severity),
                anti_pattern_score(x.severity),
            ),
            reverse=True,
        )

        # #11171: systemic rollup — types exceeding _SYSTEMIC_THRESHOLD occurrences.
        systemic_patterns = _build_systemic_rollup(sorted_patterns, summary_by_type)

        # Calculate health score (0-100, higher is better)
        total_penalty = critical_count * 20 + high_count * 10 + medium_count * 5 + low_count * 2
        health_score = max(0, 100 - total_penalty)

        recommendations = self._generate_recommendations(anti_patterns, summary_by_type)

        return AntiPatternReport(
            total_issues=len(anti_patterns),
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            health_score=health_score,
            anti_patterns=sorted_patterns,
            summary_by_type=summary_by_type,
            recommendations=recommendations,
            analysis_time_seconds=analysis_time,
            systemic_patterns=systemic_patterns,
        )

    # Issue #372: Class-level recommendation mapping reduces feature envy
    # by using self-contained data instead of repeated dict access
    _RECOMMENDATION_MAP: List[Tuple[str, str]] = [
        # Priority 1: Critical issues
        (
            "god_class",
            "🔴 CRITICAL: Refactor God Classes - Break down large classes " "following Single Responsibility Principle",
        ),
        (
            "circular_dependency",
            "🔴 CRITICAL: Resolve Circular Dependencies - " "Use dependency injection or extract common code",
        ),
        # Priority 2: High severity
        (
            "feature_envy",
            "🟠 HIGH: Address Feature Envy - " "Move methods to the classes they reference most",
        ),
        (
            "long_method",
            "🟠 HIGH: Extract Long Methods - " "Break into smaller, single-purpose methods",
        ),
        # Priority 3: Medium severity
        (
            "long_parameter_list",
            "🟡 MEDIUM: Reduce Parameter Lists - " "Introduce parameter objects or builder pattern",
        ),
        (
            "data_clump",
            "🟡 MEDIUM: Extract Data Clumps - " "Group recurring parameters into data classes",
        ),
        # Priority 4: Low severity / housekeeping
        (
            "lazy_class",
            "🟢 LOW: Review Lazy Classes - " "Consider merging or converting to functions",
        ),
        (
            "dead_code",
            "🟢 LOW: Remove Dead Code - " "Delete verified unused classes and functions",
        ),
        # Issue #6871: unwired tracker modules
        (
            "unwired_tracker",
            "🟢 LOW: Wire or document tracker-closed modules with zero production callers",
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
            recommendations.append("✅ Codebase looks healthy - no major anti-patterns detected")
        else:
            recommendations.append("📋 General: Apply SOLID principles and consider adding architectural tests")

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

    async def get_cached_report(self) -> AntiPatternReport | None:
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

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """Per-file analysis compatibility shim (#6757).

        Runs the per-file detectors (god_class, feature_envy, long_method,
        long_parameter_list, lazy_class) on a single file without the
        cross-file rules that require a whole-codebase index.

        Returns a dict compatible with the legacy ``code_intelligence``
        per-file analyzer shape expected by callers in ``analyzers.py`` and
        ``code_evolution_miner.py``.
        """
        import asyncio

        async def _inner() -> List[AntiPatternInstance]:
            clear_ast_cache()
            detector = AntiPatternDetector()
            module_info = await detector._parse_file(file_path)
            if not module_info:
                return []
            detector.modules = {module_info.name: module_info}
            detector.classes = {f"{module_info.name}.{cls.name}": cls for cls in module_info.classes}
            detector.all_defined_names = {cls.name for cls in module_info.classes}
            detector.all_defined_names.update(module_info.functions)

            patterns: List[AntiPatternInstance] = []
            patterns.extend(await detector._detect_god_classes())
            patterns.extend(await detector._detect_feature_envy())
            patterns.extend(await detector._detect_long_methods())
            patterns.extend(await detector._detect_long_parameter_lists())
            patterns.extend(await detector._detect_lazy_classes())
            return patterns

        try:
            loop = asyncio.new_event_loop()
            try:
                patterns = loop.run_until_complete(_inner())
            finally:
                loop.close()
        except Exception as exc:
            logger.error("analyze_file error for %s: %s", file_path, exc)
            patterns = []

        summary: Dict[str, int] = {}
        for p in patterns:
            k = p.pattern_type.value
            summary[k] = summary.get(k, 0) + 1

        return {
            "file_path": file_path,
            "anti_patterns": [p.to_dict() for p in patterns],
            "summary": summary,
        }


# Convenience function for CLI usage
async def run_analysis(root_path: str = ".") -> AntiPatternReport:
    """Run anti-pattern analysis on the specified path"""
    detector = AntiPatternDetector()
    return await detector.analyze(root_path)


if __name__ == "__main__":
    pass

    async def main():
        """Example usage"""
        detector = AntiPatternDetector()
        report = await detector.analyze(root_path=".", patterns=["src/**/*.py", "backend/**/*.py"])

        print(f"\n{'='*60}")  # noqa: print
        print("ANTI-PATTERN ANALYSIS REPORT")  # noqa: print
        print(f"{'='*60}")  # noqa: print
        print(f"Total Issues: {report.total_issues}")  # noqa: print
        print(f"  Critical: {report.critical_count}")  # noqa: print
        print(f"  High: {report.high_count}")  # noqa: print
        print(f"  Medium: {report.medium_count}")  # noqa: print
        print(f"  Low: {report.low_count}")  # noqa: print
        print(f"\nHealth Score: {report.health_score}/100")  # noqa: print
        print(f"Analysis Time: {report.analysis_time_seconds:.2f}s")  # noqa: print

        print(f"\n{'='*60}")  # noqa: print
        print("SUMMARY BY TYPE")  # noqa: print
        print(f"{'='*60}")  # noqa: print
        for pattern_type, count in sorted(report.summary_by_type.items()):
            print(f"  {pattern_type}: {count}")  # noqa: print

        print(f"\n{'='*60}")  # noqa: print
        print("RECOMMENDATIONS")  # noqa: print
        print(f"{'='*60}")  # noqa: print
        for rec in report.recommendations:
            print(f"  {rec}")  # noqa: print

        if report.anti_patterns:
            print(f"\n{'='*60}")  # noqa: print
            print("TOP ISSUES (by severity)")  # noqa: print
            print(f"{'='*60}")  # noqa: print
            sorted_patterns = sorted(report.anti_patterns, key=lambda x: anti_pattern_score(x.severity), reverse=True)
            for ap in sorted_patterns[:10]:
                print(f"\n[{ap.severity.value.upper()}] {ap.pattern_type.value}")  # noqa: print
                print(f"  Entity: {ap.entity_name}")  # noqa: print
                print(f"  File: {ap.file_path}:{ap.line_number}")  # noqa: print
                print(f"  {ap.description}")  # noqa: print
                print(f"  Suggestion: {ap.suggestion}")  # noqa: print

    run_or_schedule(main())
