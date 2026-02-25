# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Endpoint Scanner for codebase analytics (Issue #527)

Scans backend Python files for FastAPI route decorators and
frontend TypeScript/Vue files for API calls.
"""

import ast
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .endpoints.shared import get_project_root
from .models import (
    APIEndpointAnalysis,
    APIEndpointItem,
    EndpointMismatchItem,
    EndpointUsageItem,
    FrontendAPICallItem,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Pre-compiled Regex Patterns for Performance (Issue #527)
# =============================================================================

# Backend patterns for FastAPI route decorators
_ROUTER_DECORATOR_RE = re.compile(
    r'@(?:router|app)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
    re.IGNORECASE,
)

# Pattern for router variable names to detect prefix
_ROUTER_INCLUDE_RE = re.compile(
    r'include_router\s*\([^,]+,\s*prefix\s*=\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE
)

# Pattern for router prefix in APIRouter() initialization
_APIROUTER_PREFIX_RE = re.compile(
    r'APIRouter\s*\([^)]*prefix\s*=\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE
)

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


# =============================================================================
# Backend Endpoint Scanner
# =============================================================================


class BackendEndpointScanner:
    """Scans backend Python files for FastAPI route definitions."""

    # Global API prefix applied to all routers in app_factory.py
    API_PREFIX = "/api"

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or get_project_root()
        self.backend_path = self.project_root / "api"
        self._router_prefixes: Dict[str, str] = {}
        # Map module name to router prefix (e.g., "chat" -> "", "system" -> "/system")
        self._module_prefix_map: Dict[str, str] = {}

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

        # Second pass: scan all Python files
        for py_file in self.backend_path.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            if "archive" in str(py_file).lower():
                continue

            try:
                file_endpoints = self._scan_file(py_file)
                endpoints.extend(file_endpoints)
            except Exception as e:
                logger.debug("Error scanning %s: %s", py_file, e)

        logger.info("Found %d backend endpoints", len(endpoints))
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
        router_registry_path = (
            self.project_root / "backend" / "initialization" / "router_registry"
        )

        # Parse core_routers.py for module -> prefix mapping (uses tuple format)
        core_routers_file = router_registry_path / "core_routers.py"
        if core_routers_file.exists():
            self._parse_router_registry(core_routers_file)

        # Issue #552: Parse all *_routers.py files that use config tuple format
        # These files use ROUTER_CONFIGS pattern: ("module_path", "router", "/prefix", [...], "name")
        config_tuple_files = [
            "analytics_routers.py",
            "monitoring_routers.py",
            "feature_routers.py",
            "terminal_routers.py",
            "mcp_routers.py",
        ]

        for config_file in config_tuple_files:
            file_path = router_registry_path / config_file
            if file_path.exists():
                self._parse_config_tuple_registry(file_path)

        # Issue #552: Scan API files for include_router patterns to handle nested routers
        # e.g., knowledge.py includes knowledge_vectorization and knowledge_maintenance
        self._scan_include_router_patterns()

        logger.debug(
            "Collected %d module prefix mappings", len(self._module_prefix_map)
        )

    def _compile_router_patterns(self):
        """
        Compile regex patterns for router import detection.

        Issue #665: Extracted from _scan_include_router_patterns to reduce function length.

        Returns:
            Tuple of (import_pattern, import_modules_pattern, include_pattern)
        """
        # Pattern to detect: from api.module import router as X_router
        import_pattern = re.compile(
            r"from\s+api\.(\w+)\s+import\s+router\s+as\s+(\w+_router)",
            re.MULTILINE,
        )

        # Pattern to detect: from api import module1, module2
        import_modules_pattern = re.compile(
            r"from\s+api\s+import\s+([^;\n]+)", re.MULTILINE
        )

        # Pattern to detect: router.include_router(X_router) or router.include_router(module.router)
        include_pattern = re.compile(
            r"router\.include_router\s*\(\s*(\w+(?:\.\w+)?)\s*\)", re.MULTILINE
        )

        return import_pattern, import_modules_pattern, include_pattern

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
        self, child_module: str, parent_prefix: str, parent_module: str
    ) -> None:
        """
        Register nested router with parent's prefix if not already registered.

        Issue #665: Extracted from _scan_include_router_patterns to reduce function length.

        Args:
            child_module: Child module name to register
            parent_prefix: Parent router's prefix to inherit
            parent_module: Parent module name for logging
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
            logger.debug(
                "Nested router: %s -> %s (from %s)",
                child_module,
                parent_prefix,
                parent_module,
            )
        else:
            logger.debug(
                "Skipping nested router %s (already registered at %s)",
                child_module,
                self._module_prefix_map[child_module],
            )

    def _scan_include_router_patterns(self) -> None:
        """
        Scan API files for include_router patterns to map nested routers.

        Issue #552: Handles cases like:
        - knowledge.py includes knowledge_vectorization.py and knowledge_maintenance.py
        - chat.py includes chat_sessions.py
        - analytics.py includes analytics_cost.py (which has its own prefix="/cost")

        These nested routers inherit the parent router's prefix, and may add their own.
        """
        if not self.backend_path.exists():
            return

        # Compile patterns (Issue #665: extracted)
        (
            import_pattern,
            import_modules_pattern,
            include_pattern,
        ) = self._compile_router_patterns()

        for py_file in self.backend_path.glob("*.py"):
            if py_file.name.startswith("__"):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")

                # Get parent module's prefix
                parent_module = py_file.stem
                parent_prefix = self._module_prefix_map.get(
                    parent_module, self.API_PREFIX
                )

                # Extract imports (Issue #665: extracted)
                imported_routers, imported_modules = self._extract_router_imports(
                    content, import_pattern, import_modules_pattern
                )

                # Check which routers are included
                for match in include_pattern.finditer(content):
                    router_ref = match.group(
                        1
                    )  # e.g., "vectorization_router" or "analytics_cost.router"

                    child_module = None
                    if router_ref in imported_routers:
                        child_module = imported_routers[router_ref]
                    elif router_ref in imported_modules:
                        child_module = imported_modules[router_ref]

                    if child_module:
                        # Register nested router (Issue #665: extracted)
                        self._register_nested_router(
                            child_module, parent_prefix, parent_module
                        )

            except Exception as e:
                logger.debug("Error scanning include_router in %s: %s", py_file, e)

    def _parse_router_registry(self, file_path: Path) -> None:
        """Parse a router registry file to extract module -> prefix mappings."""
        try:
            content = file_path.read_text(encoding="utf-8")

            # Pattern to match: (router_name, "/prefix", [...], "name")
            # Matches tuples like: (chat_router, "", ["chat"], "chat")
            tuple_pattern = re.compile(
                r'\(\s*(\w+_router)\s*,\s*["\']([^"\']*)["\']', re.MULTILINE
            )

            for match in tuple_pattern.finditer(content):
                router_var = match.group(1)  # e.g., "chat_router"
                prefix = match.group(2)  # e.g., "" or "/system"

                # Extract module name from router variable (chat_router -> chat)
                module_name = router_var.replace("_router", "")

                # Store mapping: module_name -> full API prefix
                full_prefix = f"{self.API_PREFIX}{prefix}"
                self._module_prefix_map[module_name] = full_prefix

                # Also map the file name pattern
                self._module_prefix_map[f"api/{module_name}.py"] = full_prefix

        except Exception as e:
            logger.debug("Error parsing router registry %s: %s", file_path, e)

    def _compile_config_tuple_patterns(self):
        """Helper for _parse_config_tuple_registry. Ref: #1088."""
        five_element_pattern = re.compile(
            r'\(\s*["\']([^"\']+)["\'],\s*["\']router["\'],\s*["\']([^"\']*)["\']',
            re.MULTILINE,
        )
        four_element_pattern = re.compile(
            r'\(\s*["\']([^"\']+)["\'],\s*["\']([^"\']*)["\'],\s*\[', re.MULTILINE
        )
        # Issue #552: Pattern for dynamic router loading in terminal_routers.py:
        # (terminal_router, "/terminal", ["terminal"], "terminal")
        dynamic_router_pattern = re.compile(
            r'\(\s*(\w+_router)\s*,\s*["\']([^"\']*)["\'],\s*\[[^\]]*\]\s*,\s*["\'](\w+)["\']',
            re.MULTILINE,
        )
        return five_element_pattern, four_element_pattern, dynamic_router_pattern

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

    def _apply_dynamic_router_pattern(
        self, content: str, dynamic_router_pattern
    ) -> None:
        """Helper for _parse_config_tuple_registry. Ref: #1088."""
        # Issue #552: Also check for dynamic router patterns (terminal_routers.py)
        # These have router variable names instead of module paths
        for match in dynamic_router_pattern.finditer(content):
            router_var = match.group(1)  # e.g., "terminal_router"
            prefix = match.group(2)  # e.g., "/terminal"
            # group(3) contains name (e.g., "terminal") - unused; module derived from var

            # terminal_router -> terminal, agent_terminal_router -> agent_terminal
            module_name = router_var.replace("_router", "")
            module_path = f"api.{module_name}"
            self._register_module_prefix(module_path, prefix)
            logger.debug(
                "Dynamic router: %s -> %s%s", module_name, self.API_PREFIX, prefix
            )

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

    def _get_module_prefix(self, file_path: Path) -> str:
        """Get the API prefix for a given file based on router registry."""
        relative_path = str(file_path.relative_to(self.project_root))

        # Try direct file path match
        if relative_path in self._module_prefix_map:
            return self._module_prefix_map[relative_path]

        # Try module name from file name (e.g., chat.py -> chat)
        module_name = file_path.stem
        if module_name in self._module_prefix_map:
            return self._module_prefix_map[module_name]

        # Check if file is in codebase_analytics subdirectory
        if "codebase_analytics" in str(file_path):
            # Check for router prefix in parent
            if "api.codebase_analytics" in self._module_prefix_map:
                base_prefix = self._module_prefix_map["api.codebase_analytics"]
                # Check for additional prefix from codebase/router.py
                return f"{base_prefix}/codebase"

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

    def _scan_with_ast(
        self, tree: ast.AST, file_path: Path, lines: List[str]
    ) -> List[APIEndpointItem]:
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
    ) -> Optional[APIEndpointItem]:
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
                        is_async=(
                            "async def" in lines[i - 1] if i <= len(lines) else False
                        ),
                    )
                )

        return endpoints

    def _get_file_router_prefix(self, content: str) -> Optional[str]:
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

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or get_project_root()
        self.frontend_path = self.project_root / "autobot-vue" / "src"

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
                if (
                    "__tests__" in str(file)
                    or ".test." in file.name
                    or ".spec." in file.name
                ):
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
                        if not any(
                            c.path == path and c.line_number == i for c in calls
                        ):
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
    ) -> Optional[FrontendAPICallItem]:
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

    def _match_calls_to_endpoints(
        self,
        used_endpoints: List[EndpointUsageItem],
        missing_endpoints: List[EndpointMismatchItem],
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
                    usage_item = next(
                        (u for u in used_endpoints if u.endpoint == ep), None
                    )
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

            if not matched and not call.is_dynamic:
                missing_endpoints.append(
                    EndpointMismatchItem(
                        type="missing",
                        method=call.method,
                        path=call.path,
                        file_path=call.file_path,
                        line_number=call.line_number,
                        details="Called but no backend endpoint found",
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

        # Match calls to endpoints (Issue #665: uses helper)
        used_endpoint_ids = self._match_calls_to_endpoints(
            used_endpoints, missing_endpoints
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
            used=used_endpoints,
            scan_timestamp=datetime.now().isoformat(),
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

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or get_project_root()
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
