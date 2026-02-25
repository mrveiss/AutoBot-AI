# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Environment Variable Analyzer using Redis and NPU acceleration
Analyzes codebase for hardcoded values that should be environment variables
"""

import ast
import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Issue #542: Handle imports for both standalone execution and backend import
# When imported from backend, project root is in sys.path
# When running standalone, we need to add it manually
_project_root = (
    Path(__file__).resolve().parents[3]
)  # tools/code-analysis-suite/src -> project root
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from autobot_shared.redis_client import get_redis_client
    from config import UnifiedConfig

    _REDIS_AVAILABLE = True
    _CONFIG_AVAILABLE = True
except ImportError:
    # Fallback for when running without project context
    get_redis_client = None
    UnifiedConfig = None
    _REDIS_AVAILABLE = False
    _CONFIG_AVAILABLE = False

# Issue #642: SSOT mapping integration
try:
    from config.ssot_mappings import (
        SSOTMapping,
        generate_ssot_coverage_report,
        get_mapping_for_value,
        validate_against_ssot,
    )

    _SSOT_MAPPINGS_AVAILABLE = True
except ImportError:
    _SSOT_MAPPINGS_AVAILABLE = False
    get_mapping_for_value = None
    validate_against_ssot = None
    generate_ssot_coverage_report = None
    SSOTMapping = None


# Initialize unified config (with fallback)
config = UnifiedConfig() if _CONFIG_AVAILABLE else None
logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for literal value AST types
_LITERAL_VALUE_TYPES = (ast.Str, ast.Num)

# Issue #380: Module-level tuple for config file extensions
_CONFIG_FILE_EXTENSIONS = (
    ".log",
    ".db",
    ".json",
    ".yaml",
    ".yml",
    ".conf",
    ".cfg",
    ".ini",
)

# Issue #380: Module-level tuples for URL protocol prefixes
_URL_PROTOCOL_PREFIXES = (
    "http://",
    "https://",
    "ws://",
    "wss://",
    "ftp://",
    "redis://",
    "postgresql://",
    "mysql://",
)
_WEB_PROTOCOL_PREFIXES = ("http://", "https://", "ws://", "wss://")
_DATABASE_PROTOCOL_PREFIXES = ("postgresql://", "mysql://", "redis://", "mongodb://")

# Issue #632: Directories to skip during analysis (aligned with shell script)
_SKIP_DIRECTORIES = (
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "tests",
    "test",
    "testing",
    "benchmark",
    "benchmarks",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "htmlcov",
    "dist",
    "build",
    "egg-info",
    ".eggs",
    "migrations",
    "fixtures",
    "mocks",
    "stubs",
    "templates",
    "static",
    "assets",
    "archive",
    "__tests__",  # Issue #632: Added from shell script
)

# Issue #632: File patterns to skip (aligned with shell script)
_SKIP_FILE_PATTERNS = (
    # Test files
    "test_",
    "_test.py",
    "_tests.py",
    ".test.ts",
    "conftest.py",
    # Config and setup files
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "__init__.py",  # Usually just imports
    # Mock/fixture files
    "_fixture",
    "_mock",
    "_stub",
    # Benchmark files
    "benchmark_",
    "_benchmark.py",
    # Issue #632: Additional patterns from shell script
    "constants",
    "config",
    ".env",
    ".example",
    "CLAUDE.md",
    "HARDCODING_PREVENTION.md",
    "SSOT_CONFIG_GUIDE.md",
    "ssot_config.py",
    "ssot-config.ts",
    "ssot_mappings.py",
    "network_constants.py",
    "security_constants.py",
    "detect-hardcoded-values.sh",  # Don't scan the detection script itself
)

# Issue #630: Context patterns that indicate non-configurable numeric values
_NON_CONFIG_NUMERIC_CONTEXTS = (
    # Loop and iteration patterns
    "range(",  # Loop counters
    "enumerate(",  # Iteration
    "for ",  # For loops
    "while ",  # While loops
    # Math operations
    "min(",  # Math operations
    "max(",  # Math operations
    "len(",  # Length operations
    "abs(",  # Math
    "sum(",  # Math
    "round(",  # Math
    "floor(",  # Math
    "ceil(",  # Math
    "pow(",  # Math
    "divmod(",  # Math
    # Array/slice operations
    "slice(",  # Indexing
    "[",  # Array indexing
    "]:",  # Slice notation
    # Arithmetic operators
    "% ",  # Modulo operation
    "%=",  # Modulo assignment
    "+ 1",  # Increment pattern
    "- 1",  # Decrement pattern
    "+=",  # Compound assignment
    "-=",  # Compound assignment
    "*=",  # Compound assignment
    "/=",  # Compound assignment
    "//=",  # Floor division assignment
    "**",  # Power
    # Buffer/sizing patterns
    "chunk_size",  # Buffer/chunk sizing
    "batch_size",  # Batch processing
    "buffer_size",  # Buffer sizing
    "page_size",  # Pagination
    "step",  # Iteration steps
    "offset",  # Pagination offset
    "indent",  # Formatting
    "width",  # Dimensions
    "height",  # Dimensions
    "padding",  # Spacing
    "margin",  # Spacing
    # Issue #630: Function parameters and type hints
    ": int =",  # Type-hinted default parameters
    ": float =",  # Type-hinted default parameters
    "= Query(",  # FastAPI query parameters
    "= Path(",  # FastAPI path parameters
    "= Body(",  # FastAPI body parameters
    "= Field(",  # Pydantic field defaults
    # HTTP and status codes
    ".status",  # HTTP status checks
    "status_code",  # HTTP status code
    "status ==",  # Status comparison
    "status !=",  # Status comparison
    # Version and comparison patterns
    "version_info",  # Python version checks
    "VERSION",  # Version constants
    "__version__",  # Package versions
    # Comparison operators with literals
    " < (",  # Tuple comparisons
    " > (",  # Tuple comparisons
    " <= ",  # Less than or equal
    " >= ",  # Greater than or equal
    " == ",  # Equality check
    " != ",  # Inequality check
    # Common non-config variable patterns
    "days_back",  # Time range parameters
    "limit:",  # Parameter limits
    "limit =",  # Variable limits (not config)
    "count =",  # Counting variables
    "index =",  # Index variables
    "level =",  # Level indicators
    "priority",  # Priority values
    "severity",  # Severity levels
    # Security/crypto parameters (fixed values, not configurable)
    "gensalt(",  # bcrypt salt rounds
    "token_urlsafe(",  # Token length
    "token_bytes(",  # Token length
    "token_hex(",  # Token length
    "secrets.",  # Secrets module calls
    "hashlib.",  # Hash functions
    "hmac.",  # HMAC functions
    "urandom(",  # Random bytes
    # Embedding/ML dimensions (architecture constants)
    "embedding_dim",  # Model dimensions
    "hidden_size",  # Model dimensions
    "num_layers",  # Model architecture
    "num_heads",  # Attention heads
    "vocab_size",  # Vocabulary size
)

# Issue #630: Path patterns that are NOT configurable (API routes, URL patterns)
_NON_CONFIG_PATH_PATTERNS = (
    "@router.",  # FastAPI/Flask route decorators
    "@app.",  # Flask/FastAPI app decorators
    "path(",  # FastAPI path parameter
    "prefix=",  # Router prefix
    "include_router",  # Router includes
    "add_api_route",  # Route registration
    "APIRouter",  # Router definition
    "WebSocket(",  # WebSocket routes
)

# Issue #630: Variable name patterns that indicate non-configurable values
_NON_CONFIG_VARIABLE_NAMES = (
    "chunk_size",
    "batch_size",
    "buffer_size",
    "page_size",
    "step",
    "offset",
    "indent",
    "width",
    "height",
    "padding",
    "margin",
    "count",
    "index",
    "size",
    "length",
    "capacity",
    "threshold",
    "level",
    "retry",
    "retries",
    "attempt",
    "attempts",
)


@dataclass
class HardcodedValue:
    """Represents a hardcoded value in the codebase"""

    file_path: str
    line_number: int
    variable_name: Optional[str]
    value: str
    value_type: str  # path, url, port, key, etc.
    context: str  # surrounding code context
    severity: str  # high, medium, low
    suggestion: str  # suggested environment variable name
    current_usage: str  # how it's currently used


@dataclass
class ConfigRecommendation:
    """Configuration recommendation for environment variables"""

    env_var_name: str
    default_value: str
    description: str
    category: str  # database, api, security, paths, etc.
    affected_files: List[str]
    priority: str  # high, medium, low


class EnvironmentAnalyzer:
    """Analyzes code for hardcoded values that should be configurable"""

    def __init__(self, redis_client=None):
        # Issue #542: Handle case where Redis is not available
        if redis_client is not None:
            self.redis_client = redis_client
        elif _REDIS_AVAILABLE and get_redis_client is not None:
            self.redis_client = get_redis_client(async_client=True)
        else:
            self.redis_client = None
            logger.info(
                "Redis not available - caching disabled for EnvironmentAnalyzer"
            )
        self.config = config

        # Caching keys
        self.HARDCODED_KEY = "env_analysis:hardcoded:{}"
        self.RECOMMENDATIONS_KEY = "env_analysis:recommendations"

        # Issue #632: Patterns to detect hardcoded values (focus on actionable items)
        # Aligned with shell script's priority on security-relevant patterns
        self.patterns = {
            # HIGH priority: Security-relevant patterns
            "database_urls": [
                r'["\'](?:postgresql|mysql|sqlite|mongodb)://[^"\']+["\']',
                r'["\'](?:redis://)[^"\']+["\']',
            ],
            "api_keys": [
                # Only specific API key prefixes, not generic long strings
                r'["\'](?:sk-|pk_|rk_|api_|API_|Bearer\s+)[A-Za-z0-9_-]+["\']',
            ],
            "urls": [
                # HTTP/WebSocket URLs (not example domains - filtered later)
                r'["\']https?://[^"\']+["\']',
                r'["\']wss?://[^"\']+["\']',
            ],
            # MEDIUM priority: Network config
            "hostnames": [
                r'["\']localhost["\']',
                r'["\']127\.0\.0\.1["\']',
                r'["\']0\.0\.0\.0["\']',
                # Issue #632: Add VM IP patterns from shell script
                r'["\']172\.16\.168\.\d+["\']',
            ],
            "ports": [
                # Only common service ports (not generic numbers)
                r"\b(80|443|8000|8001|8080|8443|3000|5000|5173|6379|5432|27017|11434)\b",
            ],
            # LOW priority: Optional externalization
            "file_paths": [
                # Only config file paths (with at least one directory)
                r'["\'](/[^"\']+/[^"\']+\.(?:log|db|json|yaml|yml|conf|cfg|ini))["\']',
            ],
        }

        # Issue #510: Precompile and combine patterns per category at init time
        # Reduces per-file work from O(categories * patterns) to O(categories)
        self._compiled_patterns = {}
        for category, pattern_list in self.patterns.items():
            combined = "|".join(f"({p})" for p in pattern_list)
            self._compiled_patterns[category] = re.compile(combined)

        logger.info("Environment Analyzer initialized")

    async def analyze_codebase(
        self, root_path: str = ".", patterns: List[str] = None
    ) -> Dict[str, Any]:
        """Analyze entire codebase for hardcoded values"""

        start_time = time.time()
        patterns = patterns or ["**/*.py"]

        # Clear previous analysis cache
        await self._clear_cache()

        logger.info(f"Scanning for hardcoded values in {root_path}")
        hardcoded_values = await self._scan_for_hardcoded_values(root_path, patterns)
        logger.info(f"Found {len(hardcoded_values)} potential hardcoded values")

        # Categorize and prioritize findings
        logger.info("Categorizing and prioritizing findings")
        categorized = await self._categorize_values(hardcoded_values)

        # Generate configuration recommendations
        logger.info("Generating configuration recommendations")
        recommendations = await self._generate_recommendations(categorized)

        # Calculate impact metrics
        metrics = self._calculate_env_metrics(hardcoded_values, recommendations)

        analysis_time = time.time() - start_time

        # Serialize hardcoded values (includes SSOT mapping - Issue #642)
        serialized_values = [
            self._serialize_hardcoded_value(v) for v in hardcoded_values
        ]

        results = {
            "total_hardcoded_values": len(hardcoded_values),
            "categories": {cat: len(vals) for cat, vals in categorized.items()},
            "high_priority_count": len(
                [v for v in hardcoded_values if v.severity == "high"]
            ),
            "recommendations_count": len(recommendations),
            "analysis_time_seconds": analysis_time,
            "hardcoded_details": serialized_values,
            "configuration_recommendations": [
                self._serialize_recommendation(r) for r in recommendations
            ],
            "metrics": metrics,
        }

        # Issue #642: Add SSOT coverage report if mappings are available
        if _SSOT_MAPPINGS_AVAILABLE and generate_ssot_coverage_report:
            results["ssot_coverage"] = generate_ssot_coverage_report(serialized_values)
            cov = results["ssot_coverage"]
            logger.info(
                "SSOT coverage: %s%% compliant, " "%d violations have SSOT equivalents",
                cov["ssot_compliance_pct"],
                cov["with_ssot_equivalent"],
            )

        # Cache results
        await self._cache_results(results)

        logger.info(f"Environment analysis complete in {analysis_time:.2f}s")
        return results

    async def _scan_for_hardcoded_values(
        self, root_path: str, patterns: List[str]
    ) -> List[HardcodedValue]:
        """Scan files for hardcoded values (Issue #340 - refactored)"""
        hardcoded_values = []
        root = Path(root_path)

        for pattern in patterns:
            for file_path in root.glob(pattern):
                await self._process_file_for_values(file_path, hardcoded_values)

        return hardcoded_values

    async def _process_file_for_values(
        self, file_path: Path, hardcoded_values: List[HardcodedValue]
    ) -> None:
        """Process a single file for hardcoded values (Issue #340 - extracted)"""
        if not file_path.is_file() or self._should_skip_file(file_path):
            return

        try:
            values = await self._scan_file_for_hardcoded_values(str(file_path))
            hardcoded_values.extend(values)
        except Exception as e:
            logger.warning(f"Failed to scan {file_path}: {e}")

    def _should_skip_file(self, file_path: Path) -> bool:
        """Issue #632: Check if file should be skipped (aligned with shell script)"""
        path_str = str(file_path)
        file_name = file_path.name

        # Check directory-based exclusions
        path_parts = path_str.lower().split("/")
        for skip_dir in _SKIP_DIRECTORIES:
            if skip_dir in path_parts:
                return True

        # Check file pattern exclusions (exact or substring match)
        for pattern in _SKIP_FILE_PATTERNS:
            if pattern in file_name.lower():
                return True

        # Skip compiled Python files
        if file_name.endswith(".pyc"):
            return True

        # Issue #632: Skip markdown documentation files
        if file_name.endswith(".md"):
            return True

        return False

    async def _scan_file_for_hardcoded_values(
        self, file_path: str
    ) -> List[HardcodedValue]:
        """Scan a single file for hardcoded values"""

        hardcoded_values = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            # Parse AST for better context
            try:
                tree = ast.parse(content, filename=file_path)
                hardcoded_values.extend(
                    await self._scan_ast_for_hardcoded_values(file_path, tree, lines)
                )
            except SyntaxError:
                # Fallback to regex scanning for non-Python files or syntax errors
                pass

            # Regex-based scanning
            hardcoded_values.extend(
                await self._regex_scan_file(file_path, content, lines)
            )

        except Exception as e:
            logger.error(f"Error scanning {file_path}: {e}")

        return hardcoded_values

    async def _scan_ast_for_hardcoded_values(
        self, file_path: str, tree: ast.AST, lines: List[str]
    ) -> List[HardcodedValue]:
        """Issue #632: Scan AST for hardcoded values (docstring + line-level filtering)"""
        hardcoded_values = []

        # Issue #632: Collect all docstring line numbers to filter them out
        docstring_lines = self._get_docstring_lines(tree)

        for node in ast.walk(tree):
            # Issue #632: Skip nodes on docstring lines
            if hasattr(node, "lineno") and node.lineno in docstring_lines:
                continue

            # Issue #632: Skip nodes on lines with config access patterns
            if hasattr(node, "lineno") and node.lineno <= len(lines):
                line = lines[node.lineno - 1]
                if self._is_config_access_line(line):
                    continue

            hv = self._extract_hardcoded_from_node(node, file_path, lines)
            if hv:
                hardcoded_values.append(hv)

        return hardcoded_values

    def _get_docstring_lines(self, tree: ast.AST) -> set:
        """Issue #630: Identify all lines that are part of docstrings.

        Docstrings are:
        - Module-level string literals as first statement
        - Function/method-level string literals as first statement in body
        - Class-level string literals as first statement in body
        """
        docstring_lines = set()

        # Check module docstring
        if tree.body and isinstance(tree.body[0], ast.Expr):
            expr_value = tree.body[0].value
            if isinstance(expr_value, (ast.Str, ast.Constant)):
                node = tree.body[0]
                start = node.lineno
                end = getattr(node, "end_lineno", start) or start
                for line in range(start, end + 1):
                    docstring_lines.add(line)

        # Walk tree for function and class definitions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.body and isinstance(node.body[0], ast.Expr):
                    expr_value = node.body[0].value
                    # Check for string constant (docstring)
                    is_docstring = isinstance(expr_value, ast.Str) or (
                        isinstance(expr_value, ast.Constant)
                        and isinstance(expr_value.value, str)
                    )
                    if is_docstring:
                        doc_node = node.body[0]
                        start = doc_node.lineno
                        end = getattr(doc_node, "end_lineno", start) or start
                        for line in range(start, end + 1):
                            docstring_lines.add(line)

        return docstring_lines

    def _is_config_access_line(self, line: str) -> bool:
        """Issue #632: Check if line uses config access (aligned with shell script).

        Skip lines that:
        - Access environment variables (os.getenv, config.get, CONFIG[)
        - Use NetworkConstants or similar config objects
        - Are comments (# or //)
        - Contain SVG path data
        """
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            return True

        # Skip config access patterns (from shell script line 199, 238, 279)
        config_patterns = (
            "os.getenv",
            "config.",
            "getenv",
            "CONFIG[",
            "NetworkConstants",
            "AUTOBOT_",
        )
        for pattern in config_patterns:
            if pattern in line:
                return True

        # Skip SVG path data (from shell script line 204)
        svg_patterns = ("<path", 'd="M', 'd="m', "fill-rule", "clip-rule")
        for pattern in svg_patterns:
            if pattern in line:
                return True

        return False

    def _extract_hardcoded_from_node(
        self, node: ast.AST, file_path: str, lines: List[str]
    ) -> Optional[HardcodedValue]:
        """Extract hardcoded value from AST node (Issue #340 - extracted)"""
        # String literals
        if isinstance(node, ast.Str):
            return self._extract_from_str_node(node, file_path, lines)
        # Numeric constants
        if isinstance(node, ast.Num):
            return self._extract_from_num_node(node, file_path, lines)
        # Assignment nodes
        if isinstance(node, ast.Assign):
            return self._extract_from_assign_node(node, file_path, lines)
        return None

    def _extract_from_str_node(
        self, node: ast.Str, file_path: str, lines: List[str]
    ) -> Optional[HardcodedValue]:
        """Extract from string literal node (Issue #340 - extracted)"""
        value = node.s
        if not self._is_potentially_configurable(value):
            return None
        return self._create_hardcoded_value(file_path, node.lineno, None, value, lines)

    def _extract_from_num_node(
        self, node: ast.Num, file_path: str, lines: List[str]
    ) -> Optional[HardcodedValue]:
        """Extract from numeric node (Issue #340 - extracted, Issue #630 - context filtering)"""
        value = str(node.n)
        if not self._is_numeric_config_candidate(value):
            return None

        # Issue #630: Check context to filter out non-configurable numerics
        if node.lineno <= len(lines):
            line_context = lines[node.lineno - 1]
            if self._is_non_config_numeric_context(line_context):
                return None

        return self._create_hardcoded_value(file_path, node.lineno, None, value, lines)

    def _is_non_config_numeric_context(self, line: str) -> bool:
        """Issue #632: Check if line has non-configurable numerics (aligned with shell).

        Filters out (from shell script line 242):
        - Array slicing: [:5], data[1:10]
        - Docker user mapping: "1000:1000"
        - OWASP IDs: A01:2021
        - Loop counters: range(30)
        - Math operations: x + 1, x * 2
        - Compound assignments: x += 1
        """
        # Shell script patterns (line 242)
        if any(p in line for p in ["[:", '"[0-9]+:[0-9]+"', "A[0-9]{2}:[0-9]{4}"]):
            return True

        # Extended patterns from _NON_CONFIG_NUMERIC_CONTEXTS
        for pattern in _NON_CONFIG_NUMERIC_CONTEXTS:
            if pattern in line:
                return True
        return False

    def _extract_from_assign_node(
        self, node: ast.Assign, file_path: str, lines: List[str]
    ) -> Optional[HardcodedValue]:
        """Extract from assignment node (Issue #340 - extracted)"""
        for target in node.targets:
            hv = self._try_extract_named_value(
                target, node.value, file_path, node.lineno, lines
            )
            if hv:
                return hv
        return None

    def _try_extract_named_value(
        self,
        target: ast.AST,
        value_node: ast.AST,
        file_path: str,
        lineno: int,
        lines: List[str],
    ) -> Optional[HardcodedValue]:
        """Try to extract a named hardcoded value (Issue #340 - extracted)"""
        if not isinstance(target, ast.Name):
            return None
        if not isinstance(value_node, _LITERAL_VALUE_TYPES):  # Issue #380
            return None

        var_name = target.id
        value = value_node.s if isinstance(value_node, ast.Str) else str(value_node.n)

        is_config = self._is_potentially_configurable(
            value
        ) or self._is_numeric_config_candidate(value)
        if not is_config:
            return None

        return self._create_hardcoded_value(file_path, lineno, var_name, value, lines)

    @staticmethod
    def _extract_match_value(match: "re.Match") -> Optional[str]:
        """Return the first non-None captured group, or the full match.

        Issue #1183: Extracted from _regex_scan_file() to reduce function length.
        """
        if match.groups():
            for g in match.groups():
                if g is not None:
                    return g
        return match.group(0)

    async def _regex_scan_file(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[HardcodedValue]:
        """Issue #632: Scan file using regex with smart filtering (aligned with shell script).

        Applies:
        - Docstring filtering (Issue #630)
        - Config access line filtering (Issue #632)
        - Comment filtering (Issue #632)
        - SVG path filtering (Issue #632)
        """

        hardcoded_values = []

        # Pre-compute docstring line ranges to filter regex matches
        docstring_lines = set()
        try:
            tree = ast.parse(content, filename=file_path)
            docstring_lines = self._get_docstring_lines(tree)
        except SyntaxError:
            pass  # If we can't parse, proceed without docstring filtering

        # Use precompiled combined patterns
        for category, compiled in self._compiled_patterns.items():
            for match in compiled.finditer(content):
                line_num = content[: match.start()].count("\n") + 1

                # Issue #632: Skip matches inside docstrings
                if line_num in docstring_lines:
                    continue

                # Issue #632: Skip matches on config access lines
                if line_num <= len(lines):
                    line = lines[line_num - 1]
                    if self._is_config_access_line(line):
                        continue

                # Issue #1183: Delegate to extracted helper
                value = self._extract_match_value(match)

                # Skip None or empty values
                if not value:
                    continue

                # Skip values that look like docstring content
                if "\n" in value or value.startswith(("    ", "\t", '"""', "'''")):
                    continue

                # Skip if already found by AST scanning
                if not any(
                    hv.line_number == line_num and hv.value == value
                    for hv in hardcoded_values
                ):
                    hardcoded_values.append(
                        self._create_hardcoded_value(
                            file_path, line_num, None, value, lines, category
                        )
                    )

        return hardcoded_values

    def _create_hardcoded_value(
        self,
        file_path: str,
        line_num: int,
        var_name: Optional[str],
        value: str,
        lines: List[str],
        category: Optional[str] = None,
    ) -> HardcodedValue:
        """Create a HardcodedValue object with analysis"""

        # Get context (line and surrounding lines)
        context_start = max(0, line_num - 2)
        context_end = min(len(lines), line_num + 1)
        context = "\n".join(lines[context_start:context_end])

        # Determine value type and severity
        value_type, severity = self._classify_value(value, category, context)

        # Generate suggestion for environment variable name
        suggestion = self._suggest_env_var_name(var_name, value, value_type, file_path)

        # Determine current usage
        current_usage = lines[line_num - 1].strip() if line_num <= len(lines) else ""

        return HardcodedValue(
            file_path=file_path,
            line_number=line_num,
            variable_name=var_name,
            value=value,
            value_type=value_type,
            context=context,
            severity=severity,
            suggestion=suggestion,
            current_usage=current_usage,
        )

    def _is_potentially_configurable(self, value: str, context: str = "") -> bool:
        """Issue #632: Check if string is configurable (aligned with shell script)"""

        # Guard against None values
        if value is None or len(value) < 3:
            return False

        # Early filtering
        if self._is_non_configurable_string(value):
            return False

        # Skip strings that look like code/documentation
        if "\n" in value or value.startswith(
            ("    ", "\t", "#", "//", "/*", '"""', "'''")
        ):
            return False

        # Skip very long strings (likely templates/docs, not config)
        if len(value) > 200:
            return False

        # Skip API route paths (FastAPI/Flask decorators)
        if value.startswith("/") and self._is_api_route_context(value, context):
            return False

        # Issue #632: Focus on actionable configuration patterns
        example_domains = ("example.com", "example.org", "example.net", "autobot.local")
        config_indicators = [
            # Network config (HIGH priority)
            value.startswith(_DATABASE_PROTOCOL_PREFIXES),
            value.startswith(_WEB_PROTOCOL_PREFIXES)
            and not any(d in value for d in example_domains),
            value in ["localhost", "127.0.0.1", "0.0.0.0"],  # nosec B104
            # VM IPs (from shell script)
            value.startswith("172.16.168."),
            # Security (HIGH priority)
            value.startswith(
                ("sk-", "pk_", "rk_", "api_", "API_", "Bearer ", "token_")
            ),
            # File paths (MEDIUM priority - must be config files)
            (
                value.startswith("/")
                and value.endswith(_CONFIG_FILE_EXTENSIONS)
                and "/" in value[1:]
            ),
        ]

        return any(config_indicators)

    def _is_non_configurable_string(self, value: str) -> bool:
        """Issue #632: Check if string is a common non-configurable value.

        Helper for _is_potentially_configurable (Issue #632).
        """
        # Common non-configurable strings to skip
        skip_values = {
            # HTTP methods
            "get",
            "post",
            "put",
            "delete",
            "patch",
            "head",
            "options",
            # Boolean-like
            "true",
            "false",
            "yes",
            "no",
            "none",
            "null",
            # Common status/state strings
            "success",
            "error",
            "warning",
            "info",
            "debug",
            "pending",
            "active",
            "inactive",
            "completed",
            "failed",
            # Common type annotations
            "str",
            "int",
            "float",
            "bool",
            "list",
            "dict",
            "tuple",
            "set",
            "string",
            "integer",
            "number",
            "boolean",
            "array",
            "object",
            # Common method names/keywords
            "init",
            "self",
            "cls",
            "args",
            "kwargs",
        }
        if value.lower() in skip_values:
            return True

        # Skip example domains (from shell script line 339)
        example_domains = ("example.com", "example.org", "example.net", "autobot.local")
        for domain in example_domains:
            if domain in value.lower():
                return True

        return False

    def _is_api_route_context(self, value: str, context: str) -> bool:
        """Issue #630: Check if a path value is an API route decorator.

        API routes like @router.post("/enhanced") should not be flagged as
        configurable paths - they are part of the API contract.
        """
        # Check if context contains API route patterns
        for pattern in _NON_CONFIG_PATH_PATTERNS:
            if pattern in context:
                return True

        # Also check for common route decorator patterns directly
        if context.strip().startswith(("@router.", "@app.", "@api.")):
            return True

        # Check for single-segment paths (likely routes, not file paths)
        # e.g., "/enhanced" vs "/home/user/data"
        if value.startswith("/") and value.count("/") == 1:
            # Single segment like "/api" or "/health" - likely a route
            return True

        return False

    def _is_numeric_config_candidate(self, value: str) -> bool:
        """Check if a numeric value is a configuration candidate"""
        try:
            num = int(value)
            # Common port numbers, timeouts, limits
            config_numbers = [
                num in range(1024, 65536),  # Port range
                num
                in [
                    80,
                    443,
                    8000,
                    8001,
                    8080,
                    8443,
                    3000,
                    5000,
                    6379,
                    5432,
                    27017,
                ],  # Common ports
                num in range(1, 3600),  # Timeout seconds (1 sec to 1 hour)
                num in range(10, 10000),  # Common limits
            ]
            return any(config_numbers)
        except ValueError:
            return False

    def _classify_value(
        self, value: str, category: Optional[str], context: str
    ) -> Tuple[str, str]:
        """Issue #632: Classify value and severity (aligned with shell script priorities)"""

        # Guard against None values
        if value is None:
            return category or "string", "low"

        # HIGH severity: Security and infrastructure (from shell script SSOT violations)
        # Database URLs
        if value.startswith(_DATABASE_PROTOCOL_PREFIXES):
            return "database_url", "high"

        # API keys and credentials
        if any(
            pattern in value.lower()
            for pattern in ["key", "token", "password", "secret"]
        ):
            return "security", "high"
        if value.startswith(("sk-", "pk_", "rk_", "api_", "API_", "Bearer ")):
            return "security", "high"

        # VM IPs (from shell script SSOT_VM_IPS)
        if value.startswith("172.16.168."):
            return "hostname", "high"

        # Service ports (from shell script SSOT_PORTS)
        if value.isdigit():
            return self._classify_numeric_value(int(value))

        # MEDIUM severity: URLs and hostnames (not example domains)
        return self._classify_non_numeric_value(value, category, _WEB_PROTOCOL_PREFIXES)

    def _classify_numeric_value(self, num: int) -> Tuple[str, str]:
        """Classify numeric values by severity.

        Helper for _classify_value (#632).
        """
        high_ports = {
            80,
            443,
            8000,
            8001,
            8080,
            8443,
            3000,
            5000,
            5173,
            6379,
            5432,
            27017,
            11434,
        }
        if num in high_ports:
            return "port", "high"
        if 1024 <= num < 65536:
            return "port", "medium"
        if 1 <= num < 3600:
            return "timeout", "medium"
        return "numeric", "low"

    def _classify_non_numeric_value(
        self, value: str, category: Optional[str], web_prefixes: tuple
    ) -> Tuple[str, str]:
        """Classify non-numeric string values by severity.

        Helper for _classify_value (#632).
        """
        if value.startswith(web_prefixes):
            example_domains = ("example.com", "example.org", "example.net")
            if any(d in value.lower() for d in example_domains):
                return "url", "low"
            return "url", "medium"

        if value in ["localhost", "127.0.0.1", "0.0.0.0"]:  # nosec B104
            return "hostname", "medium"

        if value.startswith("/") or value.startswith("./"):
            return "path", "low"

        if value.endswith(_CONFIG_FILE_EXTENSIONS):
            return "config_file", "low"

        return category or "string", "low"

    def _suggest_env_var_name(
        self, var_name: Optional[str], value: str, value_type: str, file_path: str
    ) -> str:
        """Suggest an environment variable name"""

        # Use existing variable name as base if available
        if var_name:
            base = var_name.upper()
        else:
            # Extract from file path and value type
            file_stem = Path(file_path).stem.upper()
            base = f"{file_stem}_{value_type.upper()}"

        # Add prefix based on category
        prefixes = {
            "database_url": "DATABASE_URL",
            "url": "API_URL",
            "path": "DATA_PATH",
            "hostname": "HOST",
            "port": "PORT",
            "timeout": "TIMEOUT",
            "security": "SECRET_KEY",
        }

        if value_type in prefixes:
            return prefixes[value_type]

        # Clean up the suggested name
        suggestion = re.sub(r"[^A-Z0-9_]", "_", base)
        suggestion = re.sub(r"_+", "_", suggestion)
        suggestion = suggestion.strip("_")

        return (
            f"AUTOBOT_{suggestion}"
            if not suggestion.startswith("AUTOBOT_")
            else suggestion
        )

    async def _categorize_values(
        self, hardcoded_values: List[HardcodedValue]
    ) -> Dict[str, List[HardcodedValue]]:
        """Categorize hardcoded values by type"""

        categories = {}
        for value in hardcoded_values:
            if value.value_type not in categories:
                categories[value.value_type] = []
            categories[value.value_type].append(value)

        return categories

    async def _generate_recommendations(
        self, categorized: Dict[str, List[HardcodedValue]]
    ) -> List[ConfigRecommendation]:
        """Generate configuration recommendations"""

        recommendations = []

        for category, values in categorized.items():
            # Group by suggested environment variable name
            env_var_groups = {}
            for value in values:
                if value.suggestion not in env_var_groups:
                    env_var_groups[value.suggestion] = []
                env_var_groups[value.suggestion].append(value)

            # Create recommendations
            for env_var_name, group_values in env_var_groups.items():
                if (
                    len(group_values) >= 1
                ):  # Only recommend if used in multiple places or high severity
                    most_common_value = max(
                        set(v.value for v in group_values),
                        key=lambda x: sum(1 for v in group_values if v.value == x),
                    )

                    severity = max(
                        group_values,
                        key=lambda x: ["low", "medium", "high"].index(x.severity),
                    ).severity

                    recommendation = ConfigRecommendation(
                        env_var_name=env_var_name,
                        default_value=most_common_value,
                        description=f"Configurable {category} value",
                        category=self._map_to_config_category(category),
                        affected_files=list(set(v.file_path for v in group_values)),
                        priority=severity,
                    )
                    recommendations.append(recommendation)

        return recommendations

    def _map_to_config_category(self, value_type: str) -> str:
        """Map value type to configuration category"""
        mapping = {
            "database_url": "database",
            "url": "api",
            "hostname": "network",
            "port": "network",
            "path": "filesystem",
            "config_file": "filesystem",
            "timeout": "performance",
            "numeric": "performance",
            "security": "security",
        }
        return mapping.get(value_type, "general")

    def _calculate_env_metrics(
        self,
        hardcoded_values: List[HardcodedValue],
        recommendations: List[ConfigRecommendation],
    ) -> Dict[str, Any]:
        """Calculate environment analysis metrics"""

        severity_counts = {
            "high": len([v for v in hardcoded_values if v.severity == "high"]),
            "medium": len([v for v in hardcoded_values if v.severity == "medium"]),
            "low": len([v for v in hardcoded_values if v.severity == "low"]),
        }

        category_counts = {}
        for value in hardcoded_values:
            category = self._map_to_config_category(value.value_type)
            category_counts[category] = category_counts.get(category, 0) + 1

        file_counts = len(set(v.file_path for v in hardcoded_values))

        return {
            "severity_breakdown": severity_counts,
            "category_breakdown": category_counts,
            "files_affected": file_counts,
            "potential_config_savings": len(recommendations),
            "security_issues": severity_counts["high"],
            "configuration_complexity": len(category_counts),
        }

    def _serialize_hardcoded_value(self, value: HardcodedValue) -> Dict[str, Any]:
        """Serialize hardcoded value for output with SSOT mapping (Issue #642)"""
        result = {
            "file": value.file_path,
            "line": value.line_number,
            "variable_name": value.variable_name,
            "value": value.value,
            "type": value.value_type,
            "severity": value.severity,
            "suggested_env_var": value.suggestion,
            "context": value.context,
            "current_usage": value.current_usage,
        }

        # Issue #642: Add SSOT mapping if available
        if _SSOT_MAPPINGS_AVAILABLE and get_mapping_for_value:
            mapping = get_mapping_for_value(value.value)
            if mapping:
                result["ssot_mapping"] = {
                    "has_ssot_equivalent": True,
                    "python_config": mapping.python_config,
                    "typescript_config": mapping.typescript_config,
                    "env_var": mapping.env_var,
                    "description": mapping.description,
                    "category": mapping.category.value,
                    "ssot_severity": mapping.severity,
                    "status": "NOT_USING_SSOT",
                }
                # Upgrade severity if SSOT equivalent exists
                if mapping.severity == "high" and value.severity != "high":
                    result["severity"] = "high"
            else:
                result["ssot_mapping"] = {
                    "has_ssot_equivalent": False,
                    "status": "NO_SSOT_MAPPING",
                }

        return result

    def _serialize_recommendation(self, rec: ConfigRecommendation) -> Dict[str, Any]:
        """Serialize configuration recommendation for output"""
        return {
            "env_var_name": rec.env_var_name,
            "default_value": rec.default_value,
            "description": rec.description,
            "category": rec.category,
            "affected_files": rec.affected_files,
            "priority": rec.priority,
        }

    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                key = self.RECOMMENDATIONS_KEY
                value = json.dumps(results, default=str)
                await self.redis_client.setex(key, 3600, value)  # 1 hour TTL
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")

    async def _clear_cache(self):
        """Clear analysis cache"""
        if self.redis_client:
            try:
                # Clear all analysis keys
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match="env_analysis:*", count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")

    async def get_cached_results(self) -> Optional[Dict[str, Any]]:
        """Get cached analysis results"""
        if self.redis_client:
            try:
                value = await self.redis_client.get(self.RECOMMENDATIONS_KEY)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning(f"Failed to get cached results: {e}")
        return None

    # =========================================================================
    # Issue #633: LLM-based Filtering for False Positive Reduction
    # =========================================================================

    async def llm_filter_hardcoded(
        self,
        hardcoded_values: List[HardcodedValue],
        model: str = "llama3.2:1b",
        batch_size: int = 100,
        priority_filter: Optional[str] = None,
    ) -> List[HardcodedValue]:
        """Use LLM to filter false positives. Issue #633."""
        import os

        ollama_host = os.getenv("AUTOBOT_OLLAMA_HOST", "localhost")
        ollama_port = os.getenv("AUTOBOT_OLLAMA_PORT", "11434")
        ollama_url = f"http://{ollama_host}:{ollama_port}/api/generate"

        candidates = self._select_llm_candidates(hardcoded_values, priority_filter)
        if not candidates:
            logger.info("No candidates to filter with LLM")
            return []

        logger.info(
            f"LLM filtering {len(candidates)} candidates "
            f"with {model} (batch_size={batch_size})"
        )

        if not await self._check_ollama_health(ollama_host, ollama_port):
            return candidates

        filtered = await self._process_llm_batches(
            candidates, ollama_url, model, batch_size
        )
        self._log_llm_reduction(len(candidates), len(filtered))
        return filtered

    def _select_llm_candidates(
        self,
        hardcoded_values: List[HardcodedValue],
        priority_filter: Optional[str],
    ) -> List[HardcodedValue]:
        """Select candidates for LLM filtering.

        Helper for llm_filter_hardcoded (#633).
        """
        if priority_filter:
            return [v for v in hardcoded_values if v.severity == priority_filter]
        return hardcoded_values

    async def _check_ollama_health(self, host: str, port: str) -> bool:
        """Check if Ollama service is available.

        Helper for llm_filter_hardcoded (#633).
        """
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{host}:{port}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Ollama not available, " "returning unfiltered results"
                        )
                        return False
        except Exception as e:
            logger.warning(
                f"Ollama health check failed: {e}, " "returning unfiltered results"
            )
            return False
        return True

    async def _process_llm_batches(
        self,
        candidates: List[HardcodedValue],
        ollama_url: str,
        model: str,
        batch_size: int,
    ) -> List[HardcodedValue]:
        """Process candidates through LLM in batches.

        Helper for llm_filter_hardcoded (#633).
        """
        filtered_results = []
        total = (len(candidates) + batch_size - 1) // batch_size

        for batch_idx in range(total):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(candidates))
            batch = candidates[start:end]
            prompt = self._build_llm_filter_prompt(batch)

            try:
                true_indices = await self._call_ollama_filter(
                    ollama_url, model, prompt, session=None
                )
                for idx in true_indices:
                    if 0 <= idx < len(batch):
                        filtered_results.append(batch[idx])
                logger.debug(
                    f"Batch {batch_idx + 1}/{total}: "
                    f"{len(true_indices)}/{len(batch)} confirmed"
                )
            except Exception as e:
                logger.error(f"LLM filter batch {batch_idx + 1} failed: {e}")
                filtered_results.extend(batch)

        return filtered_results

    def _log_llm_reduction(self, original: int, filtered: int) -> None:
        """Log LLM filtering reduction statistics.

        Helper for llm_filter_hardcoded (#633).
        """
        pct = (1 - filtered / original) * 100 if original else 0
        logger.info(
            f"LLM filtering complete: {original} → {filtered} "
            f"({pct:.1f}% reduction)"
        )

    def _build_llm_filter_prompt(self, batch: List[HardcodedValue]) -> str:
        """
        Build LLM prompt for filtering a batch of hardcoded value candidates.

        Issue #633: Simple yes/no classification prompt optimized for small models.

        Args:
            batch: List of HardcodedValue candidates to evaluate

        Returns:
            Formatted prompt string
        """
        items_text = []
        for idx, item in enumerate(batch, 1):
            # Truncate context to save tokens
            context = item.context[:100] if item.context else ""
            context = context.replace("\n", " ").strip()

            items_text.append(
                f"{idx}. {item.file_path}:{item.line_number} - "
                f'"{item.value}" [{item.value_type}] '
                f"Context: {context}"
            )

        items_block = chr(10).join(items_text)
        prompt = (
            "You are analyzing code for hardcoded values "
            "that should be environment variables.\n\n"
            "For each item, determine if it's a TRUE "
            "hardcoded value (should be an env var) "
            "or a FALSE positive.\n\n"
            "TRUE examples (real issues):\n"
            '- IP addresses: "172.16.168.23"\n'
            '- Hostnames: "localhost", "redis-server.local"\n'
            "- Ports: 6379, 8080, 5432 - service ports\n"
            '- URLs: "http://api.example.com/v1"\n'
            '- API keys: "sk-abc123..."\n'
            '- Database URLs: "postgresql://user:pass@host/db"\n'
            '- File paths: "/etc/myapp/config.yaml"\n\n'
            "FALSE positive examples (NOT real issues):\n"
            "- Docstrings/comments describing code\n"
            '- API route paths: "/api/users", "/health"\n'
            '- Log messages: "Processing complete"\n'
            '- Error messages: "Connection failed"\n'
            "- Test data: mock values in test files\n"
            "- Template strings for formatting\n"
            '- Version strings: "1.0.0", "v2"\n'
            '- HTTP methods: "GET", "POST"\n\n'
            f"Items to evaluate:\n{items_block}\n\n"
            "Respond with ONLY the line numbers of TRUE "
            "issues (real hardcoded values that need "
            "env vars), comma-separated.\n"
            'If no items are true issues, respond "NONE".\n'
            "Example response: 1, 3, 7, 12\n"
        )
        return prompt

    async def _call_ollama_filter(
        self,
        url: str,
        model: str,
        prompt: str,
        session: Optional[Any] = None,
    ) -> List[int]:
        """
        Call Ollama API for filtering and parse response.

        Issue #633: Handles Ollama generate API response.

        Args:
            url: Ollama generate endpoint URL
            model: Model name to use
            prompt: The filter prompt
            session: Optional aiohttp session (creates new if None)

        Returns:
            List of 1-indexed line numbers that are true issues
        """
        import aiohttp

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temp for consistent classification
                "num_predict": 200,  # Short response expected
            },
        }

        should_close = session is None
        if session is None:
            session = aiohttp.ClientSession()

        try:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")

                result = await response.json()
                response_text = result.get("response", "").strip()

                return self._parse_llm_filter_response(response_text)

        finally:
            if should_close:
                await session.close()

    def _parse_llm_filter_response(self, response_text: str) -> List[int]:
        """
        Parse LLM response to extract line numbers of true issues.

        Issue #633: Robust parsing of comma-separated numbers.

        Args:
            response_text: Raw LLM response text

        Returns:
            List of 0-indexed positions (converted from 1-indexed line numbers)
        """
        if not response_text or response_text.upper().strip() == "NONE":
            return []

        indices = []
        # Clean up response - handle various formats
        cleaned = response_text.replace("\n", ",").replace(";", ",")

        for part in cleaned.split(","):
            part = part.strip()
            # Extract just the number from strings like "1." or "Item 1"
            match = re.search(r"\d+", part)
            if match:
                try:
                    # Convert 1-indexed to 0-indexed
                    idx = int(match.group()) - 1
                    if idx >= 0:
                        indices.append(idx)
                except ValueError:
                    continue

        return indices

    async def analyze_codebase_with_llm_filter(
        self,
        root_path: str = ".",
        patterns: List[str] = None,
        llm_model: str = "llama3.2:1b",
        filter_priority: Optional[str] = "high",
    ) -> Dict[str, Any]:
        """Analyze codebase with LLM filtering. Issue #633."""
        results = await self.analyze_codebase(root_path, patterns)
        original_count = results.get("total_hardcoded_values", 0)

        if original_count == 0:
            results["llm_filtering"] = self._build_llm_metadata(
                llm_model, 0, 0, filter_priority
            )
            return results

        hardcoded_values = self._deserialize_hardcoded_details(
            results.get("hardcoded_details", [])
        )
        filtered_values = await self.llm_filter_hardcoded(
            hardcoded_values,
            model=llm_model,
            priority_filter=filter_priority,
        )

        self._apply_filtered_results(
            results, filtered_values, original_count, llm_model, filter_priority
        )
        return results

    def _deserialize_hardcoded_details(
        self, details: List[Dict[str, Any]]
    ) -> List[HardcodedValue]:
        """Reconstruct HardcodedValue objects from serialized data.

        Helper for analyze_codebase_with_llm_filter (#633).
        """
        return [
            HardcodedValue(
                file_path=d.get("file", ""),
                line_number=d.get("line", 0),
                variable_name=d.get("variable_name"),
                value=d.get("value", ""),
                value_type=d.get("type", ""),
                context=d.get("context", ""),
                severity=d.get("severity", "low"),
                suggestion=d.get("suggested_env_var", ""),
                current_usage=d.get("current_usage", ""),
            )
            for d in details
        ]

    def _apply_filtered_results(
        self,
        results: Dict[str, Any],
        filtered_values: List[HardcodedValue],
        original_count: int,
        llm_model: str,
        filter_priority: Optional[str],
    ) -> None:
        """Update results dict with LLM-filtered data.

        Helper for analyze_codebase_with_llm_filter (#633).
        """
        filtered_details = [self._serialize_hardcoded_value(v) for v in filtered_values]
        results["hardcoded_details"] = filtered_details
        results["total_hardcoded_values"] = len(filtered_values)
        results["high_priority_count"] = len(
            [v for v in filtered_values if v.severity == "high"]
        )
        results["categories"] = {}
        for v in filtered_values:
            cat = v.value_type
            results["categories"][cat] = results["categories"].get(cat, 0) + 1
        results["llm_filtering"] = self._build_llm_metadata(
            llm_model, original_count, len(filtered_values), filter_priority
        )
        pct = (1 - len(filtered_values) / original_count) * 100 if original_count else 0
        logger.info(
            f"LLM-filtered: {original_count} → "
            f"{len(filtered_values)} ({pct:.1f}% reduction)"
        )

    def _build_llm_metadata(
        self,
        model: str,
        original: int,
        filtered: int,
        priority: Optional[str],
    ) -> Dict[str, Any]:
        """Build LLM filtering metadata dict.

        Helper for analyze_codebase_with_llm_filter (#633).
        """
        pct = (1 - filtered / original) * 100 if original else 0
        return {
            "enabled": True,
            "model": model,
            "original_count": original,
            "filtered_count": filtered,
            "reduction_percent": round(pct, 1),
            "filter_priority": priority,
        }


async def main():
    """Example usage of environment analyzer"""

    analyzer = EnvironmentAnalyzer()

    # Analyze the codebase
    results = await analyzer.analyze_codebase(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    # Log summary
    logger.info("=== Environment Variable Analysis Results ===")
    logger.info("Total hardcoded values: %d", results["total_hardcoded_values"])
    logger.info("High priority issues: %d", results["high_priority_count"])
    logger.info("Recommendations: %d", results["recommendations_count"])
    logger.info("Analysis time: %.2fs", results["analysis_time_seconds"])

    logger.info("=== Categories ===")
    for category, count in results["categories"].items():
        logger.info("%s: %d", category, count)

    logger.info("=== Top Configuration Recommendations ===")
    recommendations = results["configuration_recommendations"]
    high_priority = [r for r in recommendations if r["priority"] == "high"]

    for i, rec in enumerate(high_priority[:5], 1):
        logger.info("%d. %s (%s priority)", i, rec["env_var_name"], rec["priority"])
        logger.info("   Category: %s", rec["category"])
        logger.info("   Default: %s", rec["default_value"])
        logger.info("   Description: %s", rec["description"])
        logger.info("   Files affected: %d", len(rec["affected_files"]))

    logger.info("=== Metrics ===")
    metrics = results["metrics"]
    logger.info("Security issues: %d", metrics["security_issues"])
    logger.info("Files affected: %d", metrics["files_affected"])
    logger.info("Configuration complexity: %s", metrics["configuration_complexity"])


if __name__ == "__main__":
    asyncio.run(main())
