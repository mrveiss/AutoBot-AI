# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Architectural Pattern Recognition System (Issue #238)

Identifies architectural patterns like MVC, Repository, Factory, Observer,
and AutoBot-specific patterns in the codebase.

Key Features:
- Pattern template matching
- Structural analysis
- Pattern consistency checking
- Architecture visualization (Mermaid diagrams)
- AutoBot-specific pattern detection
"""

import ast
import asyncio
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# Issue #380: Module-level tuple for function definition AST nodes
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


# =============================================================================
# Enums and Constants
# =============================================================================


class PatternType(str, Enum):
    """Types of architectural patterns."""

    # Creational Patterns
    FACTORY = "factory"
    ABSTRACT_FACTORY = "abstract_factory"
    SINGLETON = "singleton"
    BUILDER = "builder"
    PROTOTYPE = "prototype"

    # Structural Patterns
    ADAPTER = "adapter"
    BRIDGE = "bridge"
    COMPOSITE = "composite"
    DECORATOR = "decorator"
    FACADE = "facade"
    PROXY = "proxy"

    # Behavioral Patterns
    OBSERVER = "observer"
    STRATEGY = "strategy"
    COMMAND = "command"
    STATE = "state"
    TEMPLATE_METHOD = "template_method"
    CHAIN_OF_RESPONSIBILITY = "chain_of_responsibility"

    # Architectural Patterns
    MVC = "mvc"
    MVP = "mvp"
    MVVM = "mvvm"
    REPOSITORY = "repository"
    SERVICE_LAYER = "service_layer"
    DEPENDENCY_INJECTION = "dependency_injection"

    # AutoBot-Specific
    AUTOBOT_ROUTER = "autobot_router"
    AUTOBOT_SERVICE = "autobot_service"
    AUTOBOT_MANAGER = "autobot_manager"
    AUTOBOT_HANDLER = "autobot_handler"
    REDIS_CACHING = "redis_caching"
    MCP_TOOL = "mcp_tool"


# Module-level constants for O(1) lookups (Issue #326)
NAMING_CONSISTENCY_PATTERN_TYPES = {PatternType.REPOSITORY, PatternType.SERVICE_LAYER, PatternType.FACTORY}
CLASS_SUFFIX_INDICATORS = {"Repository", "Repo", "Service", "Factory"}


class ConsistencyLevel(str, Enum):
    """Levels of pattern consistency."""

    CONSISTENT = "consistent"
    MOSTLY_CONSISTENT = "mostly_consistent"
    INCONSISTENT = "inconsistent"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Severity of pattern violations."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Pattern indicators for detection
PATTERN_INDICATORS = {
    PatternType.FACTORY: {
        "class_suffixes": ["Factory", "Creator", "Builder"],
        "method_patterns": [r"create_\w+", r"make_\w+", r"build_\w+"],
        "return_patterns": ["return cls(", "return self._class("],
    },
    PatternType.SINGLETON: {
        "class_patterns": ["_instance", "_lock"],
        "method_patterns": [r"get_instance", r"getInstance"],
        "decorators": ["@singleton"],
    },
    PatternType.REPOSITORY: {
        "class_suffixes": ["Repository", "Repo", "DAO"],
        "method_patterns": [
            r"find_by_\w+",
            r"get_all",
            r"save",
            r"delete",
            r"update",
        ],
        "base_classes": ["BaseRepository", "Repository"],
    },
    PatternType.SERVICE_LAYER: {
        "class_suffixes": ["Service", "Svc"],
        "method_patterns": [r"process_\w+", r"handle_\w+", r"execute_\w+"],
        "imports": ["repository", "Repository"],
    },
    PatternType.OBSERVER: {
        "class_suffixes": ["Observer", "Listener", "Subscriber", "Handler"],
        "method_patterns": [r"notify", r"subscribe", r"unsubscribe", r"on_\w+"],
        "attributes": ["_observers", "_subscribers", "_listeners"],
    },
    PatternType.STRATEGY: {
        "class_suffixes": ["Strategy", "Policy"],
        "base_classes": ["ABC", "Protocol"],
        "method_patterns": [r"execute", r"apply", r"run"],
    },
    PatternType.DECORATOR: {
        "patterns": ["@", "wrapper", "wrapped"],
        "function_patterns": [r"def \w+\(func"],
        "return_patterns": ["return wrapper", "return inner"],
    },
    PatternType.ADAPTER: {
        "class_suffixes": ["Adapter", "Wrapper"],
        "init_patterns": ["self._adaptee", "self._wrapped"],
    },
    PatternType.FACADE: {
        "class_suffixes": ["Facade", "Manager", "Gateway"],
        "imports_multiple": True,
        "simplifies_interface": True,
    },
    PatternType.COMMAND: {
        "class_suffixes": ["Command", "Action", "Task"],
        "method_patterns": [r"execute", r"undo", r"redo"],
        "base_classes": ["Command", "BaseCommand"],
    },
    PatternType.STATE: {
        "class_suffixes": ["State"],
        "method_patterns": [r"handle", r"enter", r"exit"],
        "context_patterns": ["self._state", "self.state"],
    },
    PatternType.MVC: {
        "components": ["model", "view", "controller"],
        "directory_patterns": ["models/", "views/", "controllers/"],
    },
    PatternType.DEPENDENCY_INJECTION: {
        "init_patterns": [r"def __init__\(self,\s*\w+:\s*\w+"],
        "decorators": ["@inject", "@Inject"],
        "frameworks": ["dependency_injector", "fastapi.Depends"],
    },
    # AutoBot-specific patterns
    PatternType.AUTOBOT_ROUTER: {
        "imports": ["from fastapi import APIRouter"],
        "patterns": ["router = APIRouter()", "@router."],
        "file_location": "backend/api/",
    },
    PatternType.AUTOBOT_SERVICE: {
        "class_suffixes": ["Service", "Engine", "Processor"],
        "file_location": "backend/services/",
        "patterns": ["async def", "await"],
    },
    PatternType.AUTOBOT_MANAGER: {
        "class_suffixes": ["Manager"],
        "patterns": ["_instance", "get_", "async def"],
        "singleton_like": True,
    },
    PatternType.REDIS_CACHING: {
        "imports": ["redis", "get_redis_client", "aioredis"],
        "patterns": [r"\.get\(", r"\.set\(", r"\.hget\(", r"\.hset\("],
        "decorators": ["@cached", "@cache"],
    },
    PatternType.MCP_TOOL: {
        "imports": ["mcp"],
        "decorators": ["@mcp.tool", "@tool"],
        "patterns": ["MCP", "tool_"],
    },
}


# =============================================================================
# Data Models
# =============================================================================


class PatternMatch(BaseModel):
    """A detected pattern match."""

    pattern_type: PatternType
    file_path: str
    class_name: Optional[str] = None
    function_name: Optional[str] = None
    line_number: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    indicators_found: List[str]
    code_snippet: Optional[str] = None


class PatternConsistency(BaseModel):
    """Pattern consistency analysis."""

    pattern_type: PatternType
    consistency_level: ConsistencyLevel
    total_instances: int
    consistent_instances: int
    violations: List[Dict[str, Any]]
    recommendations: List[str]


class ArchitectureLayer(BaseModel):
    """An architectural layer in the system."""

    name: str
    description: str
    components: List[str]
    dependencies: List[str]
    patterns_used: List[PatternType]


class ArchitectureReport(BaseModel):
    """Complete architecture analysis report."""

    timestamp: datetime
    total_files_analyzed: int
    patterns_detected: Dict[str, int]
    pattern_matches: List[PatternMatch]
    consistency_analysis: List[PatternConsistency]
    layers: List[ArchitectureLayer]
    recommendations: List[str]
    mermaid_diagram: str


class AnalysisRequest(BaseModel):
    """Request for architecture analysis."""

    paths: List[str] = Field(
        default_factory=lambda: ["backend/", "src/"],
        description="Paths to analyze",
    )
    patterns_to_detect: Optional[List[PatternType]] = Field(
        None, description="Specific patterns to look for"
    )
    include_autobot_patterns: bool = Field(
        True, description="Include AutoBot-specific patterns"
    )
    generate_diagram: bool = Field(True, description="Generate Mermaid diagram")


# =============================================================================
# Pattern Templates
# =============================================================================


@dataclass
class PatternTemplate:
    """Template for pattern detection."""

    pattern_type: PatternType
    description: str
    class_indicators: List[str] = field(default_factory=list)
    method_indicators: List[str] = field(default_factory=list)
    import_indicators: List[str] = field(default_factory=list)
    code_patterns: List[str] = field(default_factory=list)
    required_score: float = 0.5


PATTERN_TEMPLATES = {
    PatternType.FACTORY: PatternTemplate(
        pattern_type=PatternType.FACTORY,
        description="Creates objects without specifying exact class",
        class_indicators=["Factory", "Creator", "Builder"],
        method_indicators=["create", "make", "build", "new_"],
        code_patterns=[r"return\s+\w+\(", r"cls\("],
        required_score=0.4,
    ),
    PatternType.SINGLETON: PatternTemplate(
        pattern_type=PatternType.SINGLETON,
        description="Ensures only one instance exists",
        class_indicators=["_instance", "_lock"],
        method_indicators=["get_instance", "instance"],
        code_patterns=[
            r"if\s+\w+\._instance\s+is\s+None",
            r"cls\._instance\s*=",
        ],
        required_score=0.5,
    ),
    PatternType.REPOSITORY: PatternTemplate(
        pattern_type=PatternType.REPOSITORY,
        description="Abstracts data persistence layer",
        class_indicators=["Repository", "Repo", "DAO", "Store"],
        method_indicators=["find", "get", "save", "delete", "update", "add"],
        import_indicators=["database", "db", "redis", "sql"],
        required_score=0.4,
    ),
    PatternType.SERVICE_LAYER: PatternTemplate(
        pattern_type=PatternType.SERVICE_LAYER,
        description="Business logic layer",
        class_indicators=["Service", "UseCase", "Interactor"],
        method_indicators=["process", "handle", "execute", "run"],
        required_score=0.4,
    ),
    PatternType.OBSERVER: PatternTemplate(
        pattern_type=PatternType.OBSERVER,
        description="Notifies dependents of state changes",
        class_indicators=["Observer", "Listener", "Subscriber", "Publisher"],
        method_indicators=["notify", "subscribe", "unsubscribe", "on_", "emit"],
        code_patterns=[r"for\s+\w+\s+in\s+self\._\w+s:", r"\.notify\("],
        required_score=0.4,
    ),
    PatternType.STRATEGY: PatternTemplate(
        pattern_type=PatternType.STRATEGY,
        description="Defines family of interchangeable algorithms",
        class_indicators=["Strategy", "Policy", "Algorithm"],
        method_indicators=["execute", "apply", "compute"],
        import_indicators=["ABC", "abstractmethod", "Protocol"],
        required_score=0.5,
    ),
    PatternType.COMMAND: PatternTemplate(
        pattern_type=PatternType.COMMAND,
        description="Encapsulates request as object",
        class_indicators=["Command", "Action", "Task", "Job"],
        method_indicators=["execute", "undo", "redo", "run"],
        required_score=0.4,
    ),
    PatternType.ADAPTER: PatternTemplate(
        pattern_type=PatternType.ADAPTER,
        description="Converts interface to another",
        class_indicators=["Adapter", "Wrapper", "Bridge"],
        code_patterns=[r"self\._\w+\.\w+\(", r"self\.wrapped"],
        required_score=0.5,
    ),
    PatternType.FACADE: PatternTemplate(
        pattern_type=PatternType.FACADE,
        description="Provides simplified interface",
        class_indicators=["Facade", "Manager", "Gateway", "Client"],
        method_indicators=["simple_", "easy_"],
        required_score=0.4,
    ),
    PatternType.DECORATOR: PatternTemplate(
        pattern_type=PatternType.DECORATOR,
        description="Adds behavior dynamically",
        code_patterns=[
            r"def\s+\w+\(func\)",
            r"@functools\.wraps",
            r"return\s+wrapper",
        ],
        required_score=0.5,
    ),
    PatternType.DEPENDENCY_INJECTION: PatternTemplate(
        pattern_type=PatternType.DEPENDENCY_INJECTION,
        description="Injects dependencies via constructor",
        import_indicators=["Depends", "inject", "dependency_injector"],
        code_patterns=[
            r"def\s+__init__\(self,\s*\w+:\s*\w+",
            r"Depends\(",
        ],
        required_score=0.4,
    ),
    PatternType.AUTOBOT_ROUTER: PatternTemplate(
        pattern_type=PatternType.AUTOBOT_ROUTER,
        description="FastAPI router pattern used in AutoBot",
        import_indicators=["APIRouter", "fastapi"],
        code_patterns=[r"router\s*=\s*APIRouter\(", r"@router\.\w+\("],
        required_score=0.6,
    ),
    PatternType.AUTOBOT_SERVICE: PatternTemplate(
        pattern_type=PatternType.AUTOBOT_SERVICE,
        description="Async service pattern in AutoBot",
        class_indicators=["Service", "Engine", "Processor", "Worker"],
        method_indicators=["async def", "await"],
        code_patterns=[r"async\s+def\s+\w+", r"await\s+self\."],
        required_score=0.4,
    ),
    PatternType.AUTOBOT_MANAGER: PatternTemplate(
        pattern_type=PatternType.AUTOBOT_MANAGER,
        description="Singleton-like manager pattern",
        class_indicators=["Manager"],
        code_patterns=[
            r"_\w+:\s*Optional\[\w+\]\s*=\s*None",
            r"def\s+get_\w+\(",
        ],
        required_score=0.5,
    ),
    PatternType.REDIS_CACHING: PatternTemplate(
        pattern_type=PatternType.REDIS_CACHING,
        description="Redis caching strategy pattern",
        import_indicators=["redis", "get_redis_client", "aioredis"],
        code_patterns=[
            r"await\s+\w+\.get\(",
            r"await\s+\w+\.set\(",
            r"\.hget\(",
            r"\.hset\(",
        ],
        required_score=0.4,
    ),
    PatternType.MCP_TOOL: PatternTemplate(
        pattern_type=PatternType.MCP_TOOL,
        description="MCP tool definition pattern",
        import_indicators=["mcp"],
        code_patterns=[r"@\w+\.tool", r"tool_name\s*="],
        required_score=0.5,
    ),
}


# =============================================================================
# Architecture Analyzer
# =============================================================================


@dataclass
class FileAnalysis:
    """Analysis result for a single file."""

    file_path: str
    classes: List[Dict[str, Any]] = field(default_factory=list)
    functions: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    patterns_found: List[PatternMatch] = field(default_factory=list)


class ArchitectureAnalyzer:
    """
    Analyzes codebase architecture and detects patterns.

    Performs:
    - AST-based structural analysis
    - Pattern template matching
    - Consistency checking
    - Architecture visualization
    """

    def __init__(self, base_path: str = "/home/kali/Desktop/AutoBot"):
        """Initialize architecture analyzer with base path."""
        self.base_path = Path(base_path)
        self.file_analyses: Dict[str, FileAnalysis] = {}
        self.pattern_matches: List[PatternMatch] = []
        self.layers: List[ArchitectureLayer] = []

    def _determine_target_patterns(
        self, patterns_to_detect: Optional[List[PatternType]], include_autobot: bool
    ) -> List[PatternType]:
        """Determine which patterns to detect (Issue #398: extracted)."""
        if patterns_to_detect:
            return patterns_to_detect

        target_patterns = list(PatternType)
        if not include_autobot:
            autobot_patterns = {
                PatternType.AUTOBOT_ROUTER, PatternType.AUTOBOT_SERVICE,
                PatternType.AUTOBOT_MANAGER, PatternType.REDIS_CACHING, PatternType.MCP_TOOL,
            }
            target_patterns = [p for p in target_patterns if p not in autobot_patterns]
        return target_patterns

    async def _analyze_all_files(
        self, python_files: List[str], target_patterns: List[PatternType]
    ) -> None:
        """Analyze all files in parallel (Issue #398: extracted)."""
        if not python_files:
            return

        analyses = await asyncio.gather(
            *[self._analyze_file(fp, target_patterns) for fp in python_files],
            return_exceptions=True
        )

        for file_path, analysis in zip(python_files, analyses):
            if isinstance(analysis, Exception):
                logger.debug("Failed to analyze %s: %s", file_path, analysis)
            elif analysis:
                self.file_analyses[file_path] = analysis

    def _aggregate_pattern_matches(self) -> tuple:
        """Aggregate pattern matches and count (Issue #398: extracted)."""
        all_matches = []
        for analysis in self.file_analyses.values():
            all_matches.extend(analysis.patterns_found)

        pattern_counts: Dict[str, int] = defaultdict(int)
        for match in all_matches:
            pattern_counts[match.pattern_type.value] += 1

        return all_matches, pattern_counts

    async def analyze(
        self, paths: List[str], patterns_to_detect: Optional[List[PatternType]] = None,
        include_autobot_patterns: bool = True,
    ) -> ArchitectureReport:
        """Analyze architecture of specified paths (Issue #398: refactored)."""
        start_time = datetime.now()
        self.pattern_matches = []
        self.file_analyses = {}

        target_patterns = self._determine_target_patterns(patterns_to_detect, include_autobot_patterns)
        python_files = await self._collect_python_files(paths)
        logger.info("Analyzing %d Python files", len(python_files))

        await self._analyze_all_files(python_files, target_patterns)
        all_matches, pattern_counts = self._aggregate_pattern_matches()

        # Issue #619: Parallelize independent analyses
        consistency_results, layers = await asyncio.gather(
            self._check_consistency(all_matches),
            self._detect_layers(),
        )
        self.layers = layers
        recommendations = self._generate_recommendations(all_matches, consistency_results)
        mermaid_diagram = self._generate_mermaid_diagram()

        return ArchitectureReport(
            timestamp=start_time,
            total_files_analyzed=len(python_files),
            patterns_detected=dict(pattern_counts),
            pattern_matches=all_matches[:100],
            consistency_analysis=consistency_results,
            layers=self.layers,
            recommendations=recommendations,
            mermaid_diagram=mermaid_diagram,
        )

    def _should_skip_python_file(self, py_file: Path) -> bool:
        """Check if a Python file should be skipped from analysis. (Issue #315 - extracted)"""
        if "__pycache__" in str(py_file):
            return True
        if "test_" in py_file.name or "_test.py" in py_file.name:
            return True
        return False

    def _collect_files_from_directory(self, dir_path: Path) -> List[str]:
        """Collect Python files from a directory. (Issue #315 - extracted)"""
        files = []
        for py_file in dir_path.rglob("*.py"):
            if not self._should_skip_python_file(py_file):
                files.append(str(py_file))
        return files

    async def _collect_python_files(self, paths: List[str]) -> List[str]:
        """Collect all Python files from specified paths."""
        python_files = []

        for path_str in paths:
            path = self.base_path / path_str
            # Issue #358 - avoid blocking
            if not await asyncio.to_thread(path.exists):
                continue

            # Issue #358 - avoid blocking
            is_file = await asyncio.to_thread(path.is_file)
            is_dir = await asyncio.to_thread(path.is_dir) if not is_file else False

            if is_file and path.suffix == ".py":
                python_files.append(str(path))
            elif is_dir:
                # _collect_files_from_directory is sync, run in thread
                files = await asyncio.to_thread(
                    self._collect_files_from_directory, path
                )
                python_files.extend(files)

        return python_files

    def _extract_imports_from_node(self, node: ast.AST, imports: List[str]) -> None:
        """
        Extract import information from an AST node.

        (Issue #315 - extracted from _analyze_file to reduce nesting)
        """
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
                for alias in node.names:
                    imports.append(f"{node.module}.{alias.name}")

    def _extract_attributes_from_assign(self, item: ast.Assign) -> List[str]:
        """Extract attribute names from an assignment node. (Issue #315 - extracted)"""
        attrs = []
        for target in item.targets:
            if isinstance(target, ast.Name):
                attrs.append(target.id)
        return attrs

    def _extract_class_info(self, node: ast.ClassDef) -> Dict[str, Any]:
        """
        Extract class information from a ClassDef node.

        (Issue #315 - extracted from _analyze_file to reduce nesting)
        """
        class_info = {
            "name": node.name,
            "line": node.lineno,
            "bases": [self._get_base_name(base) for base in node.bases],
            "methods": [],
            "attributes": [],
            "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
        }

        for item in node.body:
            if isinstance(item, _FUNCTION_DEF_TYPES):  # Issue #380
                class_info["methods"].append(item.name)
            elif isinstance(item, ast.Assign):
                class_info["attributes"].extend(self._extract_attributes_from_assign(item))

        return class_info

    def _extract_functions_from_tree(self, tree: ast.AST) -> list:
        """Extract top-level functions from AST (Issue #398: extracted)."""
        funcs = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append({
                    "name": node.name, "line": node.lineno,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
                })
        return funcs

    def _detect_patterns_in_analysis(self, analysis: "FileAnalysis", content: str, target_patterns: list) -> None:
        """Detect patterns and add to analysis (Issue #398: extracted)."""
        for pattern_type in target_patterns:
            if pattern_type in PATTERN_TEMPLATES:
                matches = self._match_pattern(analysis, content, PATTERN_TEMPLATES[pattern_type])
                analysis.patterns_found.extend(matches)

    async def _analyze_file(
        self, file_path: str, target_patterns: List[PatternType]
    ) -> Optional[FileAnalysis]:
        """Analyze a single Python file (Issue #398: refactored)."""
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = await f.read()
        except (OSError, Exception):
            return None

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        analysis = FileAnalysis(file_path=file_path)
        for node in ast.walk(tree):
            self._extract_imports_from_node(node, analysis.imports)
            if isinstance(node, ast.ClassDef):
                analysis.classes.append(self._extract_class_info(node))
        analysis.functions = self._extract_functions_from_tree(tree)
        self._detect_patterns_in_analysis(analysis, content, target_patterns)
        return analysis

    def _get_base_name(self, node: ast.expr) -> str:
        """Get name of a base class."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return "Unknown"

    def _get_decorator_name(self, node: ast.expr) -> str:
        """Get name of a decorator."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return "Unknown"

    def _check_import_indicators(
        self,
        imports: List[str],
        import_indicators: List[str],
        indicators: List[str],
        score_per_match: float = 0.1,
        first_match_only: bool = True,
    ) -> float:
        """
        Check imports against pattern indicators and accumulate score.

        Issue #281: Extracted helper to reduce repetition in _match_pattern.

        Args:
            imports: List of imports from file analysis
            import_indicators: List of indicator strings to match
            indicators: List to append found indicators (mutated)
            score_per_match: Score to add per matching import
            first_match_only: If True, only count first indicator match per import

        Returns:
            Score delta from matching imports
        """
        score = 0.0
        for imp in imports:
            for indicator in import_indicators:
                if indicator.lower() in imp.lower():
                    score += score_per_match
                    indicators.append(f"import:{imp}")
                    if first_match_only:
                        break
        return score

    def _check_code_patterns(
        self,
        content: str,
        code_patterns: List[str],
        indicators: List[str],
        score_per_match: float = 0.1,
    ) -> float:
        """
        Check content against code patterns and accumulate score.

        Issue #281: Extracted helper to reduce repetition in _match_pattern.

        Args:
            content: Source code content to search
            code_patterns: List of regex patterns to match
            indicators: List to append found indicators (mutated)
            score_per_match: Score to add per pattern match

        Returns:
            Score delta from matching patterns
        """
        score = 0.0
        for pattern in code_patterns:
            if re.search(pattern, content):
                score += score_per_match
                indicators.append(f"code_pattern:{pattern[:30]}")
        return score

    def _score_class_indicators(
        self, class_info: Dict[str, Any], template: PatternTemplate
    ) -> tuple:
        """Score class name, methods, and base classes (Issue #398: extracted)."""
        score = 0.0
        indicators = []

        for indicator in template.class_indicators:
            if indicator in class_info["name"]:
                score += 0.3
                indicators.append(f"class_name:{indicator}")

        for method in class_info["methods"]:
            for indicator in template.method_indicators:
                if re.search(indicator, method, re.IGNORECASE):
                    score += 0.15
                    indicators.append(f"method:{method}")
                    break

        for base in class_info["bases"]:
            for indicator in template.class_indicators:
                if indicator in base:
                    score += 0.2
                    indicators.append(f"base_class:{base}")

        return score, indicators

    def _build_class_match(
        self, template: PatternTemplate, analysis: FileAnalysis,
        class_info: Dict[str, Any], score: float, indicators: List[str],
        lines: List[str],
    ) -> PatternMatch:
        """Build PatternMatch for class-level match (Issue #398: extracted).

        Issue #508: Optimized O(n³) → O(n²) by accepting pre-split lines
        instead of splitting content on each call.
        """
        start_line = max(0, class_info["line"] - 1)
        end_line = min(len(lines), class_info["line"] + 5)
        snippet = "\n".join(lines[start_line:end_line])

        return PatternMatch(
            pattern_type=template.pattern_type,
            file_path=analysis.file_path,
            class_name=class_info["name"],
            line_number=class_info["line"],
            confidence=min(1.0, score),
            indicators_found=indicators[:10],
            code_snippet=snippet[:500],
        )

    def _match_module_level_patterns(
        self, template: PatternTemplate, analysis: FileAnalysis, content: str,
    ) -> Optional[PatternMatch]:
        """Match module-level patterns (Issue #398: extracted)."""
        if analysis.classes or not template.code_patterns:
            return None

        score = 0.0
        indicators = []

        for pattern in template.code_patterns:
            matches_found = re.findall(pattern, content)
            if matches_found:
                score += 0.3 * len(matches_found)
                indicators.append(f"pattern:{pattern[:30]}")

        score += self._check_import_indicators(
            analysis.imports, template.import_indicators, indicators,
            score_per_match=0.2, first_match_only=False,
        )

        if score >= template.required_score:
            return PatternMatch(
                pattern_type=template.pattern_type,
                file_path=analysis.file_path,
                line_number=1,
                confidence=min(1.0, score),
                indicators_found=indicators[:10],
            )
        return None

    def _match_pattern(
        self, analysis: FileAnalysis, content: str, template: PatternTemplate,
    ) -> List[PatternMatch]:
        """Match a pattern template against file analysis (Issue #398: refactored).

        Issue #508: Optimized O(n³) → O(n²) by caching content.split() result.
        """
        matches = []
        # Issue #508: Cache split lines - O(n) once instead of O(n) per class
        lines = content.split("\n")

        for class_info in analysis.classes:
            score, indicators = self._score_class_indicators(class_info, template)
            score += self._check_code_patterns(content, template.code_patterns, indicators)
            score += self._check_import_indicators(
                analysis.imports, template.import_indicators, indicators
            )

            if score >= template.required_score:
                matches.append(self._build_class_match(
                    template, analysis, class_info, score, indicators, lines
                ))

        module_match = self._match_module_level_patterns(template, analysis, content)
        if module_match:
            matches.append(module_match)

        return matches

    def _check_naming_consistency(
        self,
        pattern_type: PatternType,
        pattern_matches: List[PatternMatch],
    ) -> Dict[str, Any]:
        """
        Check naming consistency for a pattern type.

        (Issue #315 - extracted from _check_consistency to reduce nesting)

        Returns:
            Dict with 'violations' and 'consistent_count' keys
        """
        violations = []
        consistent_count = 0

        if pattern_type not in NAMING_CONSISTENCY_PATTERN_TYPES:
            return {"violations": violations, "consistent_count": consistent_count}

        # Check suffix consistency
        suffixes = set()
        for m in pattern_matches:
            if m.class_name:
                for suffix in CLASS_SUFFIX_INDICATORS:
                    if m.class_name.endswith(suffix):
                        suffixes.add(suffix)
                        break

        if len(suffixes) > 1:
            violations.append(
                {
                    "type": "naming_inconsistency",
                    "description": f"Multiple naming conventions: {suffixes}",
                    "severity": Severity.LOW.value,
                }
            )
        else:
            consistent_count = len(pattern_matches)

        return {"violations": violations, "consistent_count": consistent_count}

    def _process_layer_definition(
        self, layer_def: Dict[str, Any]
    ) -> Optional[ArchitectureLayer]:
        """
        Process a layer definition and extract components.

        (Issue #315 - extracted from _detect_layers to reduce nesting)

        Returns:
            ArchitectureLayer if components found, None otherwise
        """
        components = []
        dependencies = []
        patterns_used = []

        # Find files matching layer patterns
        for file_path, analysis in self.file_analyses.items():
            if not self._file_matches_layer(file_path, layer_def["path_patterns"]):
                continue

            # Add classes as components
            for cls in analysis.classes:
                components.append(cls["name"])

            # Track patterns
            for match in analysis.patterns_found:
                if match.pattern_type not in patterns_used:
                    patterns_used.append(match.pattern_type)

            # Track dependencies from imports
            for imp in analysis.imports:
                if "." in imp:
                    dep_module = imp.split(".")[0]
                    if dep_module not in dependencies:
                        dependencies.append(dep_module)

        if not components:
            return None

        return ArchitectureLayer(
            name=layer_def["name"],
            description=layer_def["description"],
            components=components[:20],  # Limit for readability
            dependencies=dependencies[:10],
            patterns_used=patterns_used[:5],
        )

    def _file_matches_layer(
        self, file_path: str, path_patterns: List[str]
    ) -> bool:
        """
        Check if a file path matches any of the layer's path patterns.

        (Issue #315 - extracted from _process_layer_definition to reduce nesting)
        """
        for path_pattern in path_patterns:
            if path_pattern in file_path:
                return True
        return False

    def _build_low_confidence_violation(self, low_confidence: list) -> dict:
        """Build low confidence violation dict (Issue #398: extracted)."""
        return {
            "type": "low_confidence_matches",
            "description": f"{len(low_confidence)} matches with low confidence",
            "files": [m.file_path for m in low_confidence[:5]],
            "severity": Severity.INFO.value,
        }

    def _determine_consistency_level(self, violations: list, match_count: int) -> tuple:
        """Determine consistency level from violations (Issue #398: extracted)."""
        ratio = len(violations) / max(1, match_count)
        if ratio == 0:
            return ConsistencyLevel.CONSISTENT, match_count
        if ratio < 0.3:
            return ConsistencyLevel.MOSTLY_CONSISTENT, int(match_count * 0.7)
        return ConsistencyLevel.INCONSISTENT, int(match_count * 0.3)

    def _build_recommendations(self, pattern_type: PatternType, violations: list) -> list:
        """Build recommendations list (Issue #398: extracted)."""
        if not violations:
            return []
        recs = [f"Review {pattern_type.value} implementations for consistency"]
        if any(v["type"] == "naming_inconsistency" for v in violations):
            recs.append("Standardize naming convention across all implementations")
        return recs

    async def _check_consistency(self, matches: List[PatternMatch]) -> List[PatternConsistency]:
        """Check consistency of pattern implementations (Issue #398: refactored)."""
        by_pattern: Dict[PatternType, List[PatternMatch]] = defaultdict(list)
        for match in matches:
            by_pattern[match.pattern_type].append(match)

        results = []
        for pattern_type, pattern_matches in by_pattern.items():
            if len(pattern_matches) < 2:
                continue

            naming_result = self._check_naming_consistency(pattern_type, pattern_matches)
            violations = list(naming_result["violations"])
            low_confidence = [m for m in pattern_matches if m.confidence < 0.5]
            if low_confidence:
                violations.append(self._build_low_confidence_violation(low_confidence))

            level, consistent_count = self._determine_consistency_level(violations, len(pattern_matches))
            results.append(PatternConsistency(
                pattern_type=pattern_type, consistency_level=level,
                total_instances=len(pattern_matches), consistent_instances=consistent_count,
                violations=violations, recommendations=self._build_recommendations(pattern_type, violations),
            ))
        return results

    async def _detect_layers(self) -> List[ArchitectureLayer]:
        """Detect architectural layers from file organization."""
        layers = []

        # Define common layers and their indicators
        layer_definitions = [
            {
                "name": "API Layer",
                "description": "HTTP endpoints and request handling",
                "path_patterns": ["backend/api/", "api/"],
                "patterns": [PatternType.AUTOBOT_ROUTER],
            },
            {
                "name": "Service Layer",
                "description": "Business logic and orchestration",
                "path_patterns": ["backend/services/", "services/", "src/services/"],
                "patterns": [PatternType.SERVICE_LAYER, PatternType.AUTOBOT_SERVICE],
            },
            {
                "name": "Data Layer",
                "description": "Data access and persistence",
                "path_patterns": ["backend/data/", "repositories/", "src/utils/redis"],
                "patterns": [PatternType.REPOSITORY, PatternType.REDIS_CACHING],
            },
            {
                "name": "Core/Domain",
                "description": "Core business entities and logic",
                "path_patterns": ["backend/core/", "src/core/", "domain/"],
                "patterns": [PatternType.FACTORY, PatternType.STRATEGY],
            },
            {
                "name": "Infrastructure",
                "description": "External services and utilities",
                "path_patterns": ["src/utils/", "backend/initialization/"],
                "patterns": [PatternType.ADAPTER, PatternType.FACADE],
            },
        ]

        for layer_def in layer_definitions:
            layer = self._process_layer_definition(layer_def)
            if layer:
                layers.append(layer)

        return layers

    def _generate_recommendations(
        self,
        matches: List[PatternMatch],
        consistency: List[PatternConsistency],
    ) -> List[str]:
        """Generate architecture improvement recommendations."""
        recommendations = []

        # Check for missing patterns
        pattern_counts = defaultdict(int)
        for match in matches:
            pattern_counts[match.pattern_type] += 1

        # Recommend Repository pattern if not found
        if pattern_counts[PatternType.REPOSITORY] == 0:
            recommendations.append(
                "Consider using Repository pattern to abstract data access"
            )

        # Recommend Service Layer if business logic is in API
        if pattern_counts[PatternType.AUTOBOT_ROUTER] > 10 and pattern_counts[
            PatternType.SERVICE_LAYER
        ] < 5:
            recommendations.append(
                "Extract business logic from routers into Service layer"
            )

        # Check for singleton overuse
        if pattern_counts[PatternType.SINGLETON] > 10:
            recommendations.append(
                "High singleton usage detected - consider Dependency Injection"
            )

        # Add consistency-based recommendations
        for c in consistency:
            if c.consistency_level == ConsistencyLevel.INCONSISTENT:
                recommendations.append(
                    f"Improve consistency of {c.pattern_type.value} implementations"
                )

        # AutoBot-specific recommendations
        if pattern_counts[PatternType.REDIS_CACHING] > 0 and pattern_counts[
            PatternType.REDIS_CACHING
        ] < 5:
            recommendations.append(
                "Consider expanding Redis caching to more operations"
            )

        return recommendations[:10]

    def _generate_mermaid_diagram(self) -> str:
        """Generate Mermaid diagram of architecture."""
        lines = ["graph TD"]
        lines.append("    %% AutoBot Architecture Diagram")
        lines.append("")

        # Add layers as subgraphs
        for layer in self.layers:
            safe_name = layer.name.replace(" ", "_").replace("/", "_")
            lines.append(f"    subgraph {safe_name}[{layer.name}]")

            for i, component in enumerate(layer.components[:5]):
                comp_id = f"{safe_name}_{i}"
                lines.append(f"        {comp_id}[{component}]")

            lines.append("    end")
            lines.append("")

        # Add inter-layer dependencies
        if len(self.layers) >= 2:
            lines.append("    %% Layer Dependencies")
            for i in range(len(self.layers) - 1):
                layer1 = self.layers[i].name.replace(" ", "_").replace("/", "_")
                layer2 = self.layers[i + 1].name.replace(" ", "_").replace("/", "_")
                lines.append(f"    {layer1} --> {layer2}")

        # Add pattern annotations
        lines.append("")
        lines.append("    %% Patterns Detected")

        pattern_counts = defaultdict(int)
        for analysis in self.file_analyses.values():
            for match in analysis.patterns_found:
                pattern_counts[match.pattern_type.value] += 1

        for pattern, count in sorted(
            pattern_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]:
            lines.append(f"    %% {pattern}: {count} instances")

        return "\n".join(lines)


# =============================================================================
# Global Instance
# =============================================================================

_analyzer: Optional[ArchitectureAnalyzer] = None
_analyzer_lock = asyncio.Lock()


async def get_analyzer() -> ArchitectureAnalyzer:
    """Get or create the global architecture analyzer."""
    global _analyzer

    if _analyzer is None:
        async with _analyzer_lock:
            if _analyzer is None:
                _analyzer = ArchitectureAnalyzer()

    return _analyzer


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/analyze", summary="Analyze codebase architecture")
async def analyze_architecture(request: AnalysisRequest) -> ArchitectureReport:
    """
    Perform comprehensive architecture analysis.

    Detects patterns, checks consistency, and generates visualization.
    """
    analyzer = await get_analyzer()
    return await analyzer.analyze(
        paths=request.paths,
        patterns_to_detect=request.patterns_to_detect,
        include_autobot_patterns=request.include_autobot_patterns,
    )


@router.get("/patterns", summary="List available pattern types")
async def list_pattern_types() -> Dict[str, Any]:
    """List all detectable pattern types with descriptions."""
    patterns = {}
    for pattern_type in PatternType:
        template = PATTERN_TEMPLATES.get(pattern_type)
        patterns[pattern_type.value] = {
            "name": pattern_type.value.replace("_", " ").title(),
            "description": template.description if template else "No description",
            "indicators": {
                "class": template.class_indicators if template else [],
                "method": template.method_indicators if template else [],
            },
        }
    return {"patterns": patterns, "total": len(patterns)}


@router.get("/quick-scan", summary="Quick architecture scan")
async def quick_scan(
    path: str = Query("backend/api/", description="Path to scan"),
) -> Dict[str, Any]:
    """Perform quick scan of a specific path."""
    analyzer = await get_analyzer()
    report = await analyzer.analyze(
        paths=[path],
        patterns_to_detect=[
            PatternType.AUTOBOT_ROUTER,
            PatternType.SERVICE_LAYER,
            PatternType.REPOSITORY,
            PatternType.SINGLETON,
            PatternType.FACTORY,
        ],
        include_autobot_patterns=True,
    )

    return {
        "path": path,
        "files_analyzed": report.total_files_analyzed,
        "patterns_found": report.patterns_detected,
        "top_patterns": sorted(
            report.patterns_detected.items(), key=lambda x: x[1], reverse=True
        )[:5],
    }


@router.get("/layers", summary="Get architecture layers")
async def get_layers() -> Dict[str, Any]:
    """Get detected architecture layers."""
    analyzer = await get_analyzer()

    # Run analysis if not done
    if not analyzer.layers:
        await analyzer.analyze(
            paths=["backend/", "src/"],
            include_autobot_patterns=True,
        )

    return {
        "layers": [layer.model_dump() for layer in analyzer.layers],
        "total": len(analyzer.layers),
    }


@router.get("/diagram", summary="Generate architecture diagram")
async def get_diagram(
    format: str = Query("mermaid", description="Diagram format"),
) -> Dict[str, Any]:
    """Generate architecture diagram in Mermaid format."""
    analyzer = await get_analyzer()

    # Run analysis if not done
    if not analyzer.file_analyses:
        await analyzer.analyze(
            paths=["backend/", "src/"],
            include_autobot_patterns=True,
        )

    return {
        "format": format,
        "diagram": analyzer._generate_mermaid_diagram(),
    }


@router.get("/consistency", summary="Check pattern consistency")
async def check_consistency(
    pattern: Optional[PatternType] = Query(None, description="Specific pattern"),
) -> Dict[str, Any]:
    """Check consistency of pattern implementations."""
    analyzer = await get_analyzer()

    # Run analysis
    report = await analyzer.analyze(
        paths=["backend/", "src/"],
        patterns_to_detect=[pattern] if pattern else None,
        include_autobot_patterns=True,
    )

    consistency = report.consistency_analysis
    if pattern:
        consistency = [c for c in consistency if c.pattern_type == pattern]

    return {
        "consistency_results": [c.model_dump() for c in consistency],
        "total_checked": len(consistency),
    }


@router.get("/health", summary="Health check")
async def health_check() -> Dict[str, Any]:
    """Check the health of the architecture analyzer."""
    return {
        "status": "healthy",
        "available_patterns": len(PatternType),
        "templates_loaded": len(PATTERN_TEMPLATES),
    }
