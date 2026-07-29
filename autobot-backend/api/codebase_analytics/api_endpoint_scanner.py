# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API Endpoint Scanner for codebase analytics (Issue #527)

Scans backend Python files for FastAPI route decorators and
frontend TypeScript/Vue files for API calls.
"""

import ast
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set

from autobot_shared.logging_manager import get_logger

from .endpoints.shared import resolve_project_root
from .models import (
    APIEndpointAnalysis,
    APIEndpointItem,
    EndpointMismatchItem,
    EndpointUsageItem,
    FrontendAPICallItem,
)

logger = get_logger(__name__)


# =============================================================================
# Pre-compiled Regex Patterns for Performance (Issue #527)
# =============================================================================

# Backend patterns for FastAPI route decorators
_ROUTER_DECORATOR_RE = re.compile(
    r'@(?:router|app)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
    re.IGNORECASE,
)

# Pattern for router variable names to detect prefix
_ROUTER_INCLUDE_RE = re.compile(r'include_router\s*\([^,]+,\s*prefix\s*=\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE)

# Pattern for router prefix in APIRouter() initialization
_APIROUTER_PREFIX_RE = re.compile(r'APIRouter\s*\([^)]*prefix\s*=\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE)

# Frontend patterns for API calls
_API_CALL_PATTERNS = [
    # api.get('/path'), api.post('/path'), etc.
    re.compile(
        r'(?:api|axios|http|client|service)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[\'"`]([^\'"` ]+)[\'"`]',
        re.IGNORECASE,
    ),
    # fetch('/api/...') with method
    re.compile(
        r'fetch\s*\(\s*[\'"`]([^\'"` ]+)[\'"`]\s*,\s*\{[^}]*method:\s*[\'"`](GET|POST|PUT|DELETE|PATCH)[\'"`]',
        re.IGNORECASE,
    ),
    # fetch('/api/...') without method (defaults to GET)
    re.compile(r'fetch\s*\(\s*[\'"`](/api/[^\'"` ]+)[\'"`]', re.IGNORECASE),
    # useApi().get('/path')
    re.compile(
        r'useApi\s*\(\s*\)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[\'"`]([^\'"` ]+)[\'"`]',
        re.IGNORECASE,
    ),
]

# Template literal pattern for dynamic paths
_TEMPLATE_LITERAL_RE = re.compile(r"\$\{[^}]+\}")

# API path pattern
_API_PATH_RE = re.compile(r'[\'"`](/api/[^\'"` ]+)[\'"`]')

# Path parameter pattern for matching
_PATH_PARAM_RE = re.compile(r"\{[^}]+\}")

# Issue #1225: Router import detection patterns (hoisted from _compile_router_patterns)
# from api.module import router as X_router
_ROUTER_IMPORT_RE = re.compile(
    r"from\s+api\.(\w+)\s+import\s+router\s+as\s+(\w+_router)",
    re.MULTILINE,
)
# from api import module1, module2
_IMPORT_MODULES_RE = re.compile(r"from\s+api\s+import\s+([^;\n]+)", re.MULTILINE)
# router.include_router(X_router) or router.include_router(module.router)
_INCLUDE_ROUTER_RE = re.compile(
    r"router\.include_router\s*\(\s*(\w+(?:\.\w+)?)\s*\)",
    re.MULTILINE,
)
# Issue #2652: Relative imports in subdirectory router files
# from .subdir import module1, module2  OR  from . import module1
_RELATIVE_IMPORT_RE = re.compile(
    r"from\s+\.([\w.]*)\s+import\s+([^;\n\\]+)",
    re.MULTILINE,
)

# Issue #1225: Tuple registry patterns (hoisted from _compile_config_tuple_patterns)
_SIMPLE_TUPLE_RE = re.compile(
    r'\(\s*(\w+_router)\s*,\s*["\']([^"\']*)["\']',
    re.MULTILINE,
)
_FIVE_ELEMENT_TUPLE_RE = re.compile(
    r'\(\s*["\']([^"\']+)["\'],\s*["\']router["\'],' r'\s*["\']([^"\']*)["\']',
    re.MULTILINE,
)
_FOUR_ELEMENT_TUPLE_RE = re.compile(
    r'\(\s*["\']([^"\']+)["\'],\s*["\']([^"\']*)["\'],' r"\s*\[",
    re.MULTILINE,
)
# Issue #552: Dynamic router loading pattern
# #12956: names actually passed to include_router(), and the relative imports
# that bind them to a submodule -- `from .costs import router as costs_router`.
_INCLUDE_ROUTER_NAME_RE = re.compile(r"include_router\(\s*(\w+)")
_RELATIVE_ROUTER_IMPORT_RE = re.compile(r"^from\s+\.(\w+)\s+import\s+router\s+as\s+(\w+)", re.MULTILINE)


_DYNAMIC_ROUTER_TUPLE_RE = re.compile(
    r'\(\s*(\w+_router)\s*,\s*["\']([^"\']*)["\'],' r'\s*\[[^\]]*\]\s*,\s*["\'](\w+)["\']',
    re.MULTILINE,
)


# =============================================================================
# Backend Endpoint Scanner
# =============================================================================


#: Directory names that have held the FastAPI backend across layouts. Ordered
#: most-specific-first so a repo containing both is resolved deterministically.
_BACKEND_DIR_CANDIDATES = ("autobot-backend", "backend", ".")

#: What makes a directory *the* backend rather than any directory holding an
#: ``api`` folder — the router registry lives beside the routes it mounts.
_ROUTER_REGISTRY_RELPATH = Path("initialization") / "router_registry"


def _is_test_file(path: Path) -> bool:
    """Whether *path* is a test module rather than a served route (#12953).

    A route defined in a test is not an endpoint, and counting one pollutes the
    report in both directions: it appears as a backend endpoint no frontend
    calls (a phantom "orphaned" finding telling someone to wire or delete
    something that does not exist), and as a scanned path absent from
    ``app.openapi()``.

    Matches the repo's two conventions (``x_test.py`` and ``test_x.py``) plus
    anything under a ``tests`` directory.
    """
    return path.name.endswith("_test.py") or path.name.startswith("test_") or "tests" in path.parts


def find_backend_dir(project_root: Path) -> Path:
    """Locate the FastAPI backend package inside *project_root* (#12853).

    Callers pass the root of the tree being analysed — a source clone, or
    AutoBot's own checkout — and the backend sits at different depths in each.
    Assuming ``project_root / "api"`` silently produced an empty scan for every
    layout that nests it (this repo's ``autobot-backend/``), which reads as
    "this backend has no routes" rather than as a failure to look in the right
    place.

    Prefers a candidate that also carries the router registry, so a directory
    that merely happens to contain ``api/`` does not win over the real backend.
    Falls back to *project_root* unchanged when nothing matches, preserving the
    previous behaviour for callers that already point straight at the backend.
    """
    with_registry: Path | None = None
    with_api: Path | None = None

    for name in _BACKEND_DIR_CANDIDATES:
        candidate = project_root if name == "." else project_root / name
        if not (candidate / "api").is_dir():
            continue
        if (candidate / _ROUTER_REGISTRY_RELPATH).is_dir():
            with_registry = with_registry or candidate
        with_api = with_api or candidate

    return with_registry or with_api or project_root


class BackendEndpointScanner:
    """Scans backend Python files for FastAPI route definitions."""

    # Global API prefix applied to all routers in app_factory.py
    API_PREFIX = "/api"

    def __init__(self, project_root: Path | None = None):
        # Issue #12404: Fall back to resolve_project_root() (deployed-layout-aware,
        # #10730) rather than get_project_root() (hardcoded parents[4], which
        # resolves to /opt/autobot -- not the analyzable repo -- in the deployed
        # standalone rsync layout).
        self.project_root = project_root or Path(resolve_project_root())
        # Issue #12853: the backend is not always directly under the scan root.
        # This repo keeps it in autobot-backend/, so `project_root / "api"` found
        # nothing and the scan reported 0 endpoints against a ~2000-route backend
        # -- which then made every frontend call look like it targeted a missing
        # endpoint. Locate the backend package instead of assuming its depth.
        self.backend_dir = find_backend_dir(self.project_root)
        self.backend_path = self.backend_dir / "api"
        self._router_prefixes: Dict[str, str] = {}
        # Map module name to router prefix (e.g., "chat" -> "", "system" -> "/system")
        self._module_prefix_map: Dict[str, str] = {}
        # #12945: resolved file -> prefix for registry-mounted routers outside api/
        self._external_router_prefixes: Dict[Path, str] = {}

    def scan_all_endpoints(self) -> List[APIEndpointItem]:
        """
        Scan all backend API files for endpoint definitions.

        Returns:
            List of APIEndpointItem objects
        """
        endpoints: List[APIEndpointItem] = []

        if not self.backend_path.exists():
            logger.warning("Backend API path not found: %s", self.backend_path)
            return endpoints

        # First pass: collect router prefixes from registry files
        self._collect_router_prefixes()

        # #12945: routers the registries mount from outside api/ are scanned too,
        # otherwise their routes look missing to every frontend call that uses them.
        self._external_router_prefixes = self._registry_router_files()

        # Second pass: scan all Python files
        scan_targets = list(self.backend_path.rglob("*.py")) + list(self._external_router_prefixes)
        for py_file in scan_targets:
            if py_file.name.startswith("__"):
                continue
            if "archive" in str(py_file).lower():
                continue
            if _is_test_file(py_file):
                continue

            try:
                file_endpoints = self._scan_file(py_file)
                endpoints.extend(file_endpoints)
            except Exception as e:
                logger.debug("Error scanning %s: %s", py_file, e)

        logger.info(
            "Found %d backend endpoints (%d files outside api/)",
            len(endpoints),
            len(self._external_router_prefixes),
        )
        return endpoints

    def _collect_router_prefixes(self) -> None:
        """
        Collect router prefixes from router registry files.

        Issue #552: Extended to parse ALL router registry files including:
        - backend/initialization/router_registry/core_routers.py (tuple format)
        - backend/initialization/router_registry/analytics_routers.py (config tuples)
        - backend/initialization/router_registry/monitoring_routers.py (config tuples)
        - backend/initialization/router_registry/feature_routers.py (config tuples)
        - backend/initialization/router_registry/terminal_routers.py (config tuples)
        - backend/initialization/router_registry/mcp_routers.py (config tuples)
        """
        # Issue #12853: this was `project_root / "backend" / ...`, a path that
        # exists in no current layout -- so no prefix was ever parsed and every
        # endpoint was recorded without its router prefix. The registry lives
        # beside the routes, under the resolved backend directory.
        router_registry_path = self.backend_dir / _ROUTER_REGISTRY_RELPATH

        # Parse core_routers.py for module -> prefix mapping (uses tuple format)
        core_routers_file = router_registry_path / "core_routers.py"
        if core_routers_file.exists():
            self._parse_router_registry(core_routers_file)

        # Issue #552: Parse all *_routers.py files that use config tuple format
        # These files use ROUTER_CONFIGS pattern: ("module_path", "router", "/prefix", [...], "name")
        # Issue #12853: integration_routers.py was missing from this list, so
        # its routers carried no prefix. Parse every *_routers.py present
        # instead of a hand-maintained list that drifts as registries are added.
        config_tuple_files = sorted(
            p.name for p in router_registry_path.glob("*_routers.py") if p.name != "core_routers.py"
        )

        for config_file in config_tuple_files:
            file_path = router_registry_path / config_file
            if file_path.exists():
                self._parse_config_tuple_registry(file_path)

        # Issue #552: Scan API files for include_router patterns to handle nested routers
        # e.g., knowledge.py includes knowledge_vectorization and knowledge_maintenance
        self._scan_include_router_patterns()

        logger.debug("Collected %d module prefix mappings", len(self._module_prefix_map))

    def _compile_router_patterns(self):
        """Return pre-compiled regex patterns for router import detection.

        Issue #665: Extracted from _scan_include_router_patterns.
        Issue #1225: Patterns hoisted to module level.
        """
        return _ROUTER_IMPORT_RE, _IMPORT_MODULES_RE, _INCLUDE_ROUTER_RE

    def _extract_router_imports(
        self,
        content: str,
        import_pattern: re.Pattern,
        import_modules_pattern: re.Pattern,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """
        Extract router imports from file content.

        Issue #665: Extracted from _scan_include_router_patterns to reduce function length.

        Args:
            content: File content to parse
            import_pattern: Pattern for specific router imports
            import_modules_pattern: Pattern for module imports

        Returns:
            Tuple of (imported_routers, imported_modules) dictionaries
        """
        # Find all imported routers from specific module imports
        imported_routers: dict[str, str] = {}
        for match in import_pattern.finditer(content):
            module_name = match.group(1)  # e.g., "knowledge_vectorization"
            router_var = match.group(2)  # e.g., "vectorization_router"
            imported_routers[router_var] = module_name

        # Find all module imports (e.g., from api import analytics_cost)
        imported_modules: dict[str, str] = {}
        for match in import_modules_pattern.finditer(content):
            modules_str = match.group(1)
            # Parse comma-separated module names
            for mod in modules_str.split(","):
                mod = mod.strip()
                if mod:
                    # module.router reference: analytics_cost.router -> analytics_cost
                    imported_modules[f"{mod}.router"] = mod
                    imported_modules[mod] = mod

        return imported_routers, imported_modules

    def _register_nested_router(
        self,
        child_module: str,
        parent_prefix: str,
        parent_module: str,
        child_dir: str | None = None,
    ) -> None:
        """
        Register nested router with parent's prefix if not already registered.

        Issue #665: Extracted from _scan_include_router_patterns to reduce function length.
        Issue #2652: Added child_dir for subdirectory router files (e.g., codebase_analytics/endpoints/).

        Args:
            child_module: Child module name to register
            parent_prefix: Parent router's prefix to inherit
            parent_module: Parent module name for logging
            child_dir: Optional subdirectory path relative to api/ (e.g., "codebase_analytics/endpoints")
        """
        # Issue #552: Only inherit parent prefix if module doesn't have
        # its own standalone registration (e.g., in feature_routers.py).
        # This prevents dual-mounted routers (like knowledge_maintenance)
        # from being incorrectly mapped to parent's prefix.
        if child_module not in self._module_prefix_map:
            # Child inherits parent's prefix
            # Note: The child's own APIRouter(prefix=...) is handled separately
            # in _get_file_router_prefix during scanning
            self._module_prefix_map[child_module] = parent_prefix
            self._module_prefix_map[f"api/{child_module}.py"] = parent_prefix
            self._module_prefix_map[f"api.{child_module}"] = parent_prefix
            # Issue #2652: Also register subdirectory path if provided
            if child_dir:
                subdir_key = f"api/{child_dir}/{child_module}.py"
                self._module_prefix_map[subdir_key] = parent_prefix
            logger.debug(
                "Nested router: %s -> %s (from %s)",
                child_module,
                parent_prefix,
                parent_module,
            )
        else:
            # Issue #2652: Even if already registered by module name, ensure
            # the subdirectory file path key is also registered so _get_module_prefix
            # can resolve it via direct file path match.
            if child_dir:
                subdir_key = f"api/{child_dir}/{child_module}.py"
                if subdir_key not in self._module_prefix_map:
                    self._module_prefix_map[subdir_key] = self._module_prefix_map[child_module]
            logger.debug(
                "Skipping nested router %s (already registered at %s)",
                child_module,
                self._module_prefix_map[child_module],
            )

    def _extract_relative_imports(self, content: str, file_dir: Path) -> dict[str, str]:
        """
        Extract relative imports from subdirectory router files.

        Issue #2652: Handles patterns like:
        - from .endpoints import pattern_analysis, cache, call_graph
        - from . import some_module

        Args:
            content: File content to parse
            file_dir: Directory of the file being parsed (for resolving relative paths)

        Returns:
            Dict mapping router_ref -> child_module name
        """
        relative_modules: dict[str, str] = {}
        for match in _RELATIVE_IMPORT_RE.finditer(content):
            match.group(1).strip()  # e.g., "endpoints" or "" (unused)
            names_str = match.group(2)
            # Parse comma-separated names, ignoring parenthesised continuations
            names = [n.strip().rstrip(")\\") for n in names_str.split(",")]
            for name in names:
                name = name.strip()
                if not name or name.startswith("#"):
                    continue
                # Map both "name" and "name.router" so include_router(name.router) resolves
                relative_modules[name] = name
                relative_modules[f"{name}.router"] = name
        return relative_modules

    def _get_prefix_for_subdir_file(self, py_file: Path) -> tuple[str, str | None]:
        """
        Determine the parent prefix and child_dir for a subdirectory router file.

        Issue #2652: For files like api/codebase_analytics/router.py, look up the
        prefix for the parent package (api.codebase_analytics).

        Args:
            py_file: Path to the Python file being scanned

        Returns:
            Tuple of (parent_prefix, child_dir) where child_dir is the subdirectory
            relative to api/ (e.g., "codebase_analytics/endpoints"), or None for top-level files.
        """
        try:
            rel = py_file.relative_to(self.backend_path)
        except ValueError:
            return self.API_PREFIX, None

        parts = rel.parts  # e.g., ("codebase_analytics", "router.py")
        if len(parts) < 2:
            # Top-level file — handled by existing logic
            return self._module_prefix_map.get(py_file.stem, self.API_PREFIX), None

        # Build module path keys to look up (most specific first)
        # For api/codebase_analytics/endpoints/pattern_analysis.py:
        #   try "api.codebase_analytics.endpoints", "api.codebase_analytics", "codebase_analytics"
        package_parts = parts[:-1]  # directory components only
        for depth in range(len(package_parts), 0, -1):
            sub_module = ".".join(package_parts[:depth])
            for key in (f"api.{sub_module}", sub_module):
                if key in self._module_prefix_map:
                    # child_dir is the subdirectory where child modules live
                    child_dir = "/".join(package_parts)
                    return self._module_prefix_map[key], child_dir

        return self.API_PREFIX, "/".join(package_parts)

    def _resolve_router_context(
        self,
        py_file: Path,
        content: str,
        import_pattern,
        import_modules_pattern,
    ) -> tuple:
        """Resolve parent_module, parent_prefix, child_dir, and imported maps for one file.

        Issue #2735: Extracted from _scan_include_router_patterns for length compliance.
        Issue #2652: Handles both top-level and subdirectory router files.
        Returns (parent_module, parent_prefix, child_dir, imported_routers, imported_modules).
        """
        is_subdirectory = py_file.parent != self.backend_path
        parent_module = py_file.stem
        if is_subdirectory:
            parent_prefix, child_dir = self._get_prefix_for_subdir_file(py_file)
            relative_modules = self._extract_relative_imports(content, py_file.parent)
            imported_routers, imported_modules = self._extract_router_imports(
                content, import_pattern, import_modules_pattern
            )
            imported_modules.update(relative_modules)
        else:
            parent_prefix = self._module_prefix_map.get(parent_module, self.API_PREFIX)
            child_dir = None
            imported_routers, imported_modules = self._extract_router_imports(
                content, import_pattern, import_modules_pattern
            )
        return (
            parent_module,
            parent_prefix,
            child_dir,
            imported_routers,
            imported_modules,
        )

    def _scan_include_router_patterns(self) -> None:
        """
        Scan API files for include_router patterns to map nested routers.

        Issue #552: Handles cases like:
        - knowledge.py includes knowledge_vectorization.py and knowledge_maintenance.py
        - chat.py includes chat_sessions.py
        - analytics.py includes analytics_cost.py (which has its own prefix="/cost")

        Issue #2652: Extended to scan subdirectory router files so nested include_router
        chains (e.g., codebase_analytics/router.py -> endpoints/pattern_analysis.py)
        correctly populate _module_prefix_map with subdirectory file path keys.

        These nested routers inherit the parent router's prefix, and may add their own.
        """
        if not self.backend_path.exists():
            return

        # Compile patterns (Issue #665: extracted)
        import_pattern, import_modules_pattern, include_pattern = self._compile_router_patterns()

        # Issue #2652: Use rglob to include subdirectory router files
        for py_file in self.backend_path.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                (
                    parent_module,
                    parent_prefix,
                    child_dir,
                    imported_routers,
                    imported_modules,
                ) = self._resolve_router_context(py_file, content, import_pattern, import_modules_pattern)

                # Check which routers are included
                for match in include_pattern.finditer(content):
                    router_ref = match.group(1)  # e.g., "vectorization_router" or "pattern_analysis.router"
                    child_module = imported_routers.get(router_ref) or imported_modules.get(router_ref)
                    if child_module:
                        # Register nested router (Issue #665: extracted, #2652: extended)
                        self._register_nested_router(
                            child_module,
                            parent_prefix,
                            parent_module,
                            child_dir=child_dir,
                        )

            except Exception as e:
                logger.debug("Error scanning include_router in %s: %s", py_file, e)

    def _parse_router_registry(self, file_path: Path) -> None:
        """Parse a router registry file to extract module -> prefix mappings.

        #12953: the module was derived by stripping ``_router`` from the router
        variable. That holds for most entries, but the file states the real
        mapping in its own imports, and where the two disagree the guess is
        wrong twice over:

            from api.vnc_manager import router as vnc_router
            (vnc_router, "/vnc", ["vnc"], "vnc"),

        ``/vnc`` was attributed to ``api.vnc`` -- a different module that also
        exists -- while ``api.vnc_manager`` got no prefix and emitted its routes
        unprefixed as ``/api/click``, ``/api/clipboard``. Prefer the import;
        fall back to the guess when a router is not imported by alias.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            alias_modules = dict((alias, module) for module, alias in _ROUTER_IMPORT_RE.findall(content))

            # Pattern to match: (router_name, "/prefix", [...], "name")
            # Matches tuples like: (chat_router, "", ["chat"], "chat")
            for match in _SIMPLE_TUPLE_RE.finditer(content):
                router_var = match.group(1)  # e.g., "chat_router"
                prefix = match.group(2)  # e.g., "" or "/system"

                # Prefer the imported module; else chat_router -> chat
                module_name = alias_modules.get(router_var, router_var.replace("_router", ""))

                # Store mapping: module_name -> full API prefix
                full_prefix = f"{self.API_PREFIX}{prefix}"
                self._module_prefix_map[module_name] = full_prefix

                # Also map the file name pattern
                self._module_prefix_map[f"api/{module_name}.py"] = full_prefix

        except Exception as e:
            logger.debug("Error parsing router registry %s: %s", file_path, e)

    def _compile_config_tuple_patterns(self):
        """Helper for _parse_config_tuple_registry. Ref: #1088, #1225."""
        return (
            _FIVE_ELEMENT_TUPLE_RE,
            _FOUR_ELEMENT_TUPLE_RE,
            _DYNAMIC_ROUTER_TUPLE_RE,
        )

    def _apply_static_tuple_patterns(
        self,
        content: str,
        five_element_pattern,
        four_element_pattern,
    ) -> None:
        """Helper for _parse_config_tuple_registry. Ref: #1088."""
        # Try 5-element pattern first (more specific)
        matched = False
        for match in five_element_pattern.finditer(content):
            matched = True
            module_path = match.group(1)  # e.g., "api.infrastructure"
            prefix = match.group(2)  # e.g., "/iac"
            self._register_module_prefix(module_path, prefix)

        # If no 5-element matches, try 4-element pattern
        if not matched:
            for match in four_element_pattern.finditer(content):
                module_path = match.group(1)  # e.g., "api.analytics"
                prefix = match.group(2)  # e.g., "/analytics"
                self._register_module_prefix(module_path, prefix)

    def _apply_dynamic_router_pattern(self, content: str, dynamic_router_pattern) -> None:
        """Helper for _parse_config_tuple_registry. Ref: #1088.

        #12953: the module used to be *guessed* by stripping ``_router`` from the
        variable name. That is right for most entries but wrong whenever the
        alias does not mirror its module, and the file states the real mapping
        two lines up:

            from api.vnc_manager import router as vnc_router   # -> api.vnc_manager
            (vnc_router, "/vnc", ["vnc"], "vnc"),              # guessed api.vnc

        The guess then attributed ``/vnc`` to ``api.vnc`` -- a different module
        that also exists -- while ``api.vnc_manager`` got no prefix at all and
        emitted its routes as ``/api/click``, ``/api/clipboard``. So a mismatch
        costs twice: a wrong attribution and an unprefixed module. Read the
        import when it is present; fall back to the guess when it is not, since
        some registries build routers without importing them by alias.
        """
        alias_modules = dict((alias, module) for module, alias in _ROUTER_IMPORT_RE.findall(content))

        for match in dynamic_router_pattern.finditer(content):
            router_var = match.group(1)  # e.g., "terminal_router"
            prefix = match.group(2)  # e.g., "/terminal"
            # group(3) contains name (e.g., "terminal") - unused; module resolved below

            # terminal_router -> terminal, agent_terminal_router -> agent_terminal
            module_name = alias_modules.get(router_var, router_var.replace("_router", ""))
            module_path = f"api.{module_name}"
            self._register_module_prefix(module_path, prefix)
            logger.debug("Dynamic router: %s -> %s%s", module_name, self.API_PREFIX, prefix)

    def _parse_config_tuple_registry(self, file_path: Path) -> None:
        """
        Parse router registry files that use config tuple format.

        Issue #552: Handles multiple tuple formats:
        - 4-element (analytics): (module_path, prefix, tags, name)
        - 5-element (monitoring/feature): (module_path, router_attr, prefix, tags, name)
        - Dynamic function-based (terminal_routers.py): (router_var, "/prefix", tags, name)

        Both formats have the module path first and prefix second or third.
        """
        try:
            content = file_path.read_text(encoding="utf-8")

            five_el, four_el, dynamic_el = self._compile_config_tuple_patterns()

            self._apply_static_tuple_patterns(content, five_el, four_el)

            self._apply_dynamic_router_pattern(content, dynamic_el)

        except Exception as e:
            logger.debug("Error parsing config tuple registry %s: %s", file_path, e)

    def _register_module_prefix(self, module_path: str, prefix: str) -> None:
        """
        Register a module path to API prefix mapping.

        Issue #552: Extracted helper for consistent prefix registration.

        Args:
            module_path: Python module path (e.g., "api.infrastructure")
            prefix: Router URL prefix (e.g., "/iac")
        """
        # Build full API prefix
        full_prefix = f"{self.API_PREFIX}{prefix}"
        self._module_prefix_map[module_path] = full_prefix

        # Also derive file path mapping (api.foo -> api/foo)
        file_path_str = module_path.replace(".", "/")
        self._module_prefix_map[file_path_str] = full_prefix

        # Extract module name from path (api.infrastructure -> infrastructure)
        module_name = module_path.split(".")[-1]
        self._module_prefix_map[module_name] = full_prefix
        self._module_prefix_map[f"api/{module_name}.py"] = full_prefix

        logger.debug("Registered prefix: %s -> %s", module_name, full_prefix)

    def _registry_router_files(self) -> Dict[Path, str]:
        """Map files to prefixes for registry-mounted routers outside ``api/`` (#12945).

        The scan walks ``api/`` only, but the registries also mount routers from
        sibling packages -- ``services.advanced_workflow.routes``, ``llc.api``,
        ``routers.*``. Those routes were never discovered, so every frontend call
        to one was reported as targeting a missing endpoint: 419 real routes,
        95.4% of all findings.

        Resolves each registry module path against the backend directory and
        carries the registered prefix, so the routes land under the path they
        are actually served on.

        A registry entry naming a *package* needs its own ``__init__.py`` read
        first (#12945). LLC registers as ``("llc.api", "", …)`` -- an empty
        prefix -- while its real ``/api/llc/*`` paths come from the package
        router declared there:

            llc/api/__init__.py:  router = APIRouter(prefix="/llc")
            llc/api/costs.py:     router = APIRouter(prefix="/costs")

        so a submodule serves ``/api`` + ``/llc`` + ``/costs``. Applying the
        registry prefix alone to each submodule yields ``/api/costs/…`` --
        182 endpoints of which 4 were real. Inventing endpoints is worse than
        missing them, since they resurface as phantom "orphaned" findings.
        """
        files: Dict[Path, str] = {}
        for module_path, prefix in self._module_prefix_map.items():
            # Registry entries are dotted module paths; the map also holds bare
            # module names and "api/x.py"-style keys, which are not those.
            if "." not in module_path or "/" in module_path or module_path.endswith(".py"):
                continue
            if module_path.startswith("api."):
                continue  # already covered by the api/ walk

            target = self.backend_dir.joinpath(*module_path.split("."))
            module_file = target.with_suffix(".py")
            if module_file.is_file():
                files[module_file] = prefix
            elif (target / "__init__.py").is_file():
                files.update(self._package_router_files(target, prefix))
        return files

    def _package_router_files(self, package: Path, registry_prefix: str) -> Dict[Path, str]:
        """Map a registry-mounted package's submodules to their served prefix.

        The package's own ``APIRouter(prefix=...)`` sits between the registry
        prefix and each submodule's router prefix, and ``_scan_file`` applies
        the submodule's own prefix separately -- so only the package-level part
        belongs here.

        A submodule is included only when the package imports its router under
        an alias AND mounts that exact alias via ``include_router``. #12956: the
        previous check only confirmed the package mounted *something*, then
        included every router-declaring module -- so a declared-but-unmounted
        router still contributed routes, which the docstring already claimed it
        would not.

        Nested router subpackages recurse, so their modules resolve under their
        own prefix rather than the parent's.
        """
        init_file = package / "__init__.py"
        init_content = init_file.read_text(encoding="utf-8", errors="ignore")
        package_prefix = self._get_file_router_prefix(init_content) or ""
        if not _INCLUDE_ROUTER_RE.search(init_content):
            return {}

        served_prefix = f"{registry_prefix}{package_prefix}"
        mounted = set(_INCLUDE_ROUTER_NAME_RE.findall(init_content))
        if not mounted:
            return {}

        files: Dict[Path, str] = {}
        # #12956: walk one level and recurse, rather than rglob'ing the tree.
        # rglob descended into nested router subpackages while the "__" filter
        # removed the very __init__.py carrying their own prefix, so their
        # modules were emitted under the PARENT's prefix -- inventing endpoints,
        # the failure this whole change set exists to avoid.
        for module_name, alias in _RELATIVE_ROUTER_IMPORT_RE.findall(init_content):
            if alias not in mounted:
                # Declared but never mounted: it serves nothing.
                continue
            module_file = (package / module_name).with_suffix(".py")
            if module_file.is_file():
                files[module_file] = served_prefix
                continue
            subpackage = package / module_name
            if (subpackage / "__init__.py").is_file():
                files.update(self._package_router_files(subpackage, served_prefix))
        return files

    def _get_module_prefix(self, file_path: Path) -> str:
        """Get the API prefix for a given file based on router registry."""
        # #12945: registry-mounted files outside api/ carry their prefix
        # explicitly -- neither the relative-path nor the stem lookup below can
        # find them (the stem of services/advanced_workflow/routes.py is
        # "routes", which matches nothing).
        override = self._external_router_prefixes.get(file_path)
        if override is not None:
            return override

        try:
            relative_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            return self.API_PREFIX

        # Try direct file path match
        if relative_path in self._module_prefix_map:
            return self._module_prefix_map[relative_path]

        # Try module name from file name (e.g., chat.py -> chat)
        module_name = file_path.stem
        if module_name in self._module_prefix_map:
            return self._module_prefix_map[module_name]

        # Issue #1469: Check if file is in codebase_analytics subdirectory
        # (e.g., api/codebase_analytics/endpoints/pattern_analysis.py)
        if "codebase_analytics" in str(file_path):
            if "api.codebase_analytics" in self._module_prefix_map:
                return self._module_prefix_map["api.codebase_analytics"]

        # Default: use /api prefix with no additional router prefix
        return self.API_PREFIX

    def _scan_file(self, file_path: Path) -> List[APIEndpointItem]:
        """Scan a single Python file for endpoints."""
        endpoints: List[APIEndpointItem] = []

        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()

            # Try AST parsing first for accurate detection
            try:
                tree = ast.parse(content)
                endpoints.extend(self._scan_with_ast(tree, file_path, lines))
            except SyntaxError:
                # Fall back to regex
                endpoints.extend(self._scan_with_regex(content, file_path))

            # Get the module prefix from router registry (includes /api)
            module_prefix = self._get_module_prefix(file_path)

            # Get file-level router prefix (from APIRouter(prefix=...))
            file_prefix = self._get_file_router_prefix(content)

            # Apply prefixes to build full API path
            for ep in endpoints:
                # Start with the endpoint path from decorator
                endpoint_path = ep.path

                # Apply file-level router prefix if present
                if file_prefix and not endpoint_path.startswith(file_prefix):
                    endpoint_path = file_prefix + endpoint_path
                    ep.router_prefix = file_prefix

                # Apply module prefix if path doesn't already have /api
                if not endpoint_path.startswith("/api"):
                    ep.path = module_prefix + endpoint_path
                else:
                    ep.path = endpoint_path

                # Store the full router prefix for reference
                if ep.router_prefix is None:
                    ep.router_prefix = module_prefix

        except Exception as e:
            logger.debug("Error scanning file %s: %s", file_path, e)

        return endpoints

    def _scan_with_ast(self, tree: ast.AST, file_path: Path, lines: List[str]) -> List[APIEndpointItem]:
        """Scan using AST for accurate decorator detection."""
        endpoints: List[APIEndpointItem] = []
        relative_path = str(file_path.relative_to(self.project_root))

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                endpoint = self._parse_decorator(decorator, node, relative_path)
                if endpoint:
                    endpoints.append(endpoint)

        return endpoints

    def _parse_decorator(
        self,
        decorator: ast.expr,
        func_node: ast.AST,
        file_path: str,
    ) -> APIEndpointItem | None:
        """Parse a decorator AST node for route information."""
        # Handle @router.get("/path") style
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                attr = decorator.func
                method = attr.attr.upper()

                if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    return None

                # Get the path from first argument
                path = None
                if decorator.args:
                    first_arg = decorator.args[0]
                    if isinstance(first_arg, ast.Constant):
                        path = str(first_arg.value)

                if path:
                    return APIEndpointItem(
                        method=method,
                        path=path,
                        file_path=file_path,
                        line_number=decorator.lineno,
                        function_name=func_node.name,
                        is_async=isinstance(func_node, ast.AsyncFunctionDef),
                    )

        return None

    def _scan_with_regex(self, content: str, file_path: Path) -> List[APIEndpointItem]:
        """Fallback regex scanning for files that can't be parsed."""
        endpoints: List[APIEndpointItem] = []
        relative_path = str(file_path.relative_to(self.project_root))

        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            match = _ROUTER_DECORATOR_RE.search(line)
            if match:
                method = match.group(1).upper()
                path = match.group(2)

                # Try to get function name from next lines
                func_name = "unknown"
                for j in range(i, min(i + 5, len(lines))):
                    func_match = re.search(r"(?:async\s+)?def\s+(\w+)", lines[j - 1])
                    if func_match:
                        func_name = func_match.group(1)
                        break

                endpoints.append(
                    APIEndpointItem(
                        method=method,
                        path=path,
                        file_path=relative_path,
                        line_number=i,
                        function_name=func_name,
                        is_async=("async def" in lines[i - 1] if i <= len(lines) else False),
                    )
                )

        return endpoints

    def _get_file_router_prefix(self, content: str) -> str | None:
        """Extract router prefix from file content."""
        match = _APIROUTER_PREFIX_RE.search(content)
        if match:
            return match.group(1)
        return None


# =============================================================================
# Frontend API Call Scanner
# =============================================================================


class FrontendAPICallScanner:
    """Scans frontend TypeScript/Vue files for API calls."""

    def __init__(self, project_root: Path | None = None):
        # Issue #12404: Fall back to resolve_project_root() (deployed-layout-aware,
        # #10730) rather than get_project_root() (hardcoded parents[4], which
        # resolves to /opt/autobot -- not the analyzable repo -- in the deployed
        # standalone rsync layout).
        self.project_root = project_root or Path(resolve_project_root())
        self.frontend_path = self.project_root / "autobot-frontend" / "src"

    def scan_all_calls(self) -> List[FrontendAPICallItem]:
        """
        Scan all frontend files for API calls.

        Returns:
            List of FrontendAPICallItem objects
        """
        calls: List[FrontendAPICallItem] = []

        if not self.frontend_path.exists():
            logger.warning("Frontend path not found: %s", self.frontend_path)
            return calls

        # Scan TypeScript and Vue files
        for pattern in ("*.ts", "*.vue", "*.tsx", "*.js"):
            for file in self.frontend_path.rglob(pattern):
                if "node_modules" in str(file):
                    continue
                if file.name.endswith(".d.ts"):
                    continue
                # Skip test files - they contain mock data, not real API calls
                if "__tests__" in str(file) or ".test." in file.name or ".spec." in file.name:
                    continue

                try:
                    file_calls = self._scan_file(file)
                    calls.extend(file_calls)
                except Exception as e:
                    logger.debug("Error scanning %s: %s", file, e)

        logger.info("Found %d frontend API calls", len(calls))
        return calls

    def _scan_file(self, file_path: Path) -> List[FrontendAPICallItem]:
        """Scan a single frontend file for API calls."""
        calls: List[FrontendAPICallItem] = []
        relative_path = str(file_path.relative_to(self.project_root))

        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()

            for i, line in enumerate(lines, 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("/*"):
                    continue

                # Try each API call pattern
                for pattern in _API_CALL_PATTERNS:
                    for match in pattern.finditer(line):
                        call = self._parse_api_call(match, line, i, relative_path)
                        if call:
                            calls.append(call)

                # Also detect standalone API paths
                if "/api/" in line:
                    for path_match in _API_PATH_RE.finditer(line):
                        path = path_match.group(1)
                        # Check if this is already captured
                        if not any(c.path == path and c.line_number == i for c in calls):
                            calls.append(
                                FrontendAPICallItem(
                                    method="UNKNOWN",
                                    path=path,
                                    file_path=relative_path,
                                    line_number=i,
                                    context=stripped[:100],
                                    is_dynamic=bool(_TEMPLATE_LITERAL_RE.search(line)),
                                )
                            )

        except Exception as e:
            logger.debug("Error scanning file %s: %s", file_path, e)

        return calls

    def _parse_api_call(
        self,
        match: re.Match,
        line: str,
        line_number: int,
        file_path: str,
    ) -> FrontendAPICallItem | None:
        """Parse a regex match into an API call item."""
        groups = match.groups()

        # Determine method and path based on pattern
        method = "GET"
        path = ""

        if len(groups) == 2:
            # api.get('/path') style or fetch with method
            if groups[0].upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                method = groups[0].upper()
                path = groups[1]
            elif groups[1].upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                path = groups[0]
                method = groups[1].upper()
            else:
                method = groups[0].upper()
                path = groups[1]
        elif len(groups) == 1:
            # fetch('/api/...') without explicit method
            path = groups[0]
            method = "GET"

        if not path:
            return None

        # Normalize path
        if not path.startswith("/"):
            path = "/" + path

        # Check if path contains template literals
        is_dynamic = bool(_TEMPLATE_LITERAL_RE.search(path)) or "${" in path

        return FrontendAPICallItem(
            method=method,
            path=path,
            file_path=file_path,
            line_number=line_number,
            context=line.strip()[:100],
            is_dynamic=is_dynamic,
        )


# =============================================================================
# Endpoint Matcher - Cross-Reference Engine
# =============================================================================


class EndpointMatcher:
    """Matches frontend calls to backend endpoints."""

    def __init__(
        self,
        endpoints: List[APIEndpointItem],
        calls: List[FrontendAPICallItem],
    ):
        self.endpoints = endpoints
        self.calls = calls
        self._endpoint_map: Dict[str, List[APIEndpointItem]] = {}
        self._build_endpoint_map()

    def _build_endpoint_map(self) -> None:
        """Build a map of normalized paths to endpoints for fast lookup."""
        for ep in self.endpoints:
            # Normalize path for matching
            normalized = self._normalize_path(ep.path)
            key = f"{ep.method}:{normalized}"
            if key not in self._endpoint_map:
                self._endpoint_map[key] = []
            self._endpoint_map[key].append(ep)

    def _normalize_path(self, path: str) -> str:
        """Normalize a path for matching (replace params with placeholder)."""
        # Issue #552: Strip query parameters before normalization
        # e.g., "/api/foo?dry_run=true" -> "/api/foo"
        if "?" in path:
            path = path.split("?")[0]
        # Replace {param} style with wildcard
        normalized = _PATH_PARAM_RE.sub("*", path)
        # Remove trailing slash
        return normalized.rstrip("/")

    def _paths_match(self, endpoint_path: str, call_path: str) -> bool:
        """Check if an endpoint path matches a call path."""
        ep_normalized = self._normalize_path(endpoint_path)
        call_normalized = self._normalize_path(call_path)

        # Exact match
        if ep_normalized == call_normalized:
            return True

        # Check with wildcards
        ep_parts = ep_normalized.split("/")
        call_parts = call_normalized.split("/")

        if len(ep_parts) != len(call_parts):
            return False

        for ep_part, call_part in zip(ep_parts, call_parts):
            if ep_part == "*":
                continue
            if ep_part != call_part:
                return False

        return True

    @staticmethod
    def _is_reportable_call(path: str) -> bool:
        """Is *path* a real API call worth reporting as missing (#12745)?

        The 2400-finding report was padded with strings that were never
        endpoints: bare examples from docstrings (``/endpoint``, ``/save``) and
        base-path fragments left over from URL concatenation
        (``/api/adapters/``, ``/api/secrets/``, both at absurd line numbers).
        Reporting those as drift trains people to ignore the report.
        """
        if not path or not path.startswith("/api"):
            return False
        # A base-path fragment: "/api/adapters/" is the prefix a call builds on,
        # not a route. A real route has a segment after the resource name.
        stripped = path.rstrip("/")
        if path.endswith("/") and len(stripped.strip("/").split("/")) <= 2:
            return False
        return True

    def _match_calls_to_endpoints(
        self,
        used_endpoints: List[EndpointUsageItem],
        missing_endpoints: List[EndpointMismatchItem],
        low_confidence_endpoints: List[EndpointMismatchItem],
    ) -> Set[int]:
        """
        Match API calls to backend endpoints.

        Issue #665: Extracted from analyze() to improve maintainability.

        Args:
            used_endpoints: List to accumulate used endpoint items
            missing_endpoints: List to accumulate missing endpoint items

        Returns:
            Set of endpoint indices that were matched
        """
        used_endpoint_ids: Set[int] = set()

        for call in self.calls:
            matched = False
            for ep_idx, ep in enumerate(self.endpoints):
                if call.method != "UNKNOWN" and call.method != ep.method:
                    continue

                if self._paths_match(ep.path, call.path):
                    matched = True
                    used_endpoint_ids.add(ep_idx)

                    # Find or create usage item
                    usage_item = next((u for u in used_endpoints if u.endpoint == ep), None)
                    if usage_item:
                        usage_item.call_count += 1
                        usage_item.callers.append(call)
                    else:
                        used_endpoints.append(
                            EndpointUsageItem(
                                endpoint=ep,
                                call_count=1,
                                callers=[call],
                            )
                        )
                    break

            if not matched and not call.is_dynamic and self._is_reportable_call(call.path):
                # #12745: method=="UNKNOWN" marks a finding from the standalone-
                # path fallback -- the line held an "/api/..." string but matched
                # no structured call pattern, so this may be a comment, constant
                # or cache-key map rather than a call. Measured 89% false against
                # app.openapi() versus 25% for pattern-matched calls, so these are
                # reported separately instead of drowning the actionable ones.
                # Separated, never dropped: suppression is how #12894 hid 29 real
                # findings behind a label.
                low_confidence = call.method == "UNKNOWN"
                (low_confidence_endpoints if low_confidence else missing_endpoints).append(
                    EndpointMismatchItem(
                        type="low_confidence" if low_confidence else "missing",
                        method=call.method,
                        path=call.path,
                        file_path=call.file_path,
                        line_number=call.line_number,
                        details=(
                            "Path literal with no recognised call pattern — verify before acting"
                            if low_confidence
                            else "Called but no backend endpoint found"
                        ),
                    )
                )

        return used_endpoint_ids

    def _find_orphaned_endpoints(
        self,
        used_endpoint_ids: Set[int],
    ) -> List[EndpointMismatchItem]:
        """
        Find backend endpoints with no frontend calls.

        Issue #665: Extracted from analyze() to improve maintainability.

        Args:
            used_endpoint_ids: Set of endpoint indices that were matched

        Returns:
            List of orphaned endpoint items
        """
        orphaned: List[EndpointMismatchItem] = []

        for ep_idx, ep in enumerate(self.endpoints):
            if ep_idx not in used_endpoint_ids:
                orphaned.append(
                    EndpointMismatchItem(
                        type="orphaned",
                        method=ep.method,
                        path=ep.path,
                        file_path=ep.file_path,
                        line_number=ep.line_number,
                        details="Defined but no frontend calls found",
                    )
                )

        return orphaned

    def _empty_scan_analysis(self) -> APIEndpointAnalysis:
        """Result for a backend scan that found no routes at all (#12745).

        Deliberately reports zero missing rather than "every call is missing":
        the comparison has no basis, and emitting it buried the genuine drift
        under thousands of false positives. ``scan_error`` carries the reason so
        the state is visible instead of looking like a clean report.
        """
        reason = (
            "Backend endpoint scan found 0 routes — missing-endpoint comparison "
            "suppressed because it would report every frontend call as missing. "
            "Check that the analyzed source tree is indexed and reachable."
        )
        logger.error("api_endpoint_scanner: %s", reason)
        return APIEndpointAnalysis(
            backend_endpoints=0,
            frontend_calls=len(self.calls),
            used_endpoints=0,
            orphaned_endpoints=0,
            missing_endpoints=0,
            coverage_percentage=0.0,
            endpoints=[],
            api_calls=self.calls,
            orphaned=[],
            missing=[],
            used=[],
            scan_timestamp=datetime.now(tz=timezone.utc).isoformat(),
            scan_error=reason,
        )

    def analyze(self) -> APIEndpointAnalysis:
        """
        Perform full endpoint analysis.

        Issue #665: Refactored to use extracted helpers for call matching
        and orphan detection.

        Returns:
            APIEndpointAnalysis with all results
        """
        used_endpoints: List[EndpointUsageItem] = []
        missing_endpoints: List[EndpointMismatchItem] = []
        low_confidence_endpoints: List[EndpointMismatchItem] = []

        # #12745: with an empty endpoint map every call matches nothing, so the
        # report claimed 2400 missing endpoints of which 97.4% actually existed.
        # A scan that found no routes cannot conclude anything about drift —
        # report the failure instead of manufacturing findings from it.
        if not self.endpoints:
            return self._empty_scan_analysis()

        # Match calls to endpoints (Issue #665: uses helper)
        used_endpoint_ids = self._match_calls_to_endpoints(
            used_endpoints, missing_endpoints, low_confidence_endpoints
        )

        # Find orphaned endpoints (Issue #665: uses helper)
        orphaned_endpoints = self._find_orphaned_endpoints(used_endpoint_ids)

        # Calculate coverage
        total_endpoints = len(self.endpoints)
        used_count = len(used_endpoint_ids)
        coverage = (used_count / total_endpoints * 100) if total_endpoints > 0 else 0

        return APIEndpointAnalysis(
            backend_endpoints=len(self.endpoints),
            frontend_calls=len(self.calls),
            used_endpoints=len(used_endpoints),
            orphaned_endpoints=len(orphaned_endpoints),
            missing_endpoints=len(missing_endpoints),
            coverage_percentage=round(coverage, 1),
            endpoints=self.endpoints,
            api_calls=self.calls,
            orphaned=orphaned_endpoints,
            missing=missing_endpoints,
            low_confidence=low_confidence_endpoints,
            low_confidence_endpoints=len(low_confidence_endpoints),
            used=used_endpoints,
            scan_timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )


# =============================================================================
# Main Scanner Class
# =============================================================================


class APIEndpointChecker:
    """
    Main API Endpoint Checker that coordinates scanning and analysis.

    Usage:
        checker = APIEndpointChecker()
        analysis = checker.run_full_analysis()
    """

    def __init__(self, project_root: Path | None = None):
        # Issue #12404: Fall back to resolve_project_root() (deployed-layout-aware,
        # #10730) rather than get_project_root() (hardcoded parents[4], which
        # resolves to /opt/autobot -- not the analyzable repo -- in the deployed
        # standalone rsync layout).
        self.project_root = project_root or Path(resolve_project_root())
        self.backend_scanner = BackendEndpointScanner(self.project_root)
        self.frontend_scanner = FrontendAPICallScanner(self.project_root)

    def run_full_analysis(self) -> APIEndpointAnalysis:
        """
        Run complete API endpoint analysis.

        Returns:
            APIEndpointAnalysis with all results
        """
        logger.info("Starting API endpoint analysis...")

        # Scan backend endpoints
        endpoints = self.backend_scanner.scan_all_endpoints()

        # Scan frontend calls
        calls = self.frontend_scanner.scan_all_calls()

        # Match and analyze
        matcher = EndpointMatcher(endpoints, calls)
        analysis = matcher.analyze()

        logger.info(
            "API analysis complete: %d endpoints, %d calls, %.1f%% coverage",
            analysis.backend_endpoints,
            analysis.frontend_calls,
            analysis.coverage_percentage,
        )

        return analysis

    def get_backend_endpoints(self) -> List[APIEndpointItem]:
        """Get only backend endpoints."""
        return self.backend_scanner.scan_all_endpoints()

    def get_frontend_calls(self) -> List[FrontendAPICallItem]:
        """Get only frontend API calls."""
        return self.frontend_scanner.scan_all_calls()
