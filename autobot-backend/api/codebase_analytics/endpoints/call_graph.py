# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Function call graph analysis endpoints
"""

import ast
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.redis_client import get_redis_client

from .shared import COMMON_THIRD_PARTY, STDLIB_MODULES, ImportContext, get_project_root

logger = logging.getLogger(__name__)

# Issue #711: Cache configuration for call graph
CALL_GRAPH_CACHE_PREFIX = "codebase:call_graph:cache"
CALL_GRAPH_CACHE_TTL = 300  # 5 minutes cache


def _get_cache_key(project_root: str) -> str:
    """
    Generate path-specific cache key.

    Issue #711: Include project root in cache key to prevent
    returning stale data when scanning different paths.

    Args:
        project_root: The root path being analyzed

    Returns:
        Cache key unique to this path
    """
    import hashlib

    path_hash = hashlib.md5(project_root.encode()).hexdigest()[:12]
    return f"{CALL_GRAPH_CACHE_PREFIX}:{path_hash}"


router = APIRouter()


# =============================================================================
# Helper Functions for get_call_graph (Issue #281)
# =============================================================================

# Builtin functions to exclude from call graph
BUILTIN_FUNCS = {
    "print",
    "len",
    "range",
    "str",
    "int",
    "float",
    "list",
    "dict",
    "set",
    "tuple",
    "bool",
    "type",
    "isinstance",
    "hasattr",
    "getattr",
    "setattr",
    "open",
    "sorted",
    "enumerate",
    "zip",
    "map",
    "filter",
    "any",
    "all",
    "min",
    "max",
    "sum",
    "abs",
    "round",
    "format",
    "input",
    "super",
}

# Directories to exclude from analysis
EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    "archive",
    "dist",
    "build",
}


async def _get_python_files(project_root) -> List:
    """Get filtered list of Python files for analysis (Issue #281: extracted)."""
    python_files = await asyncio.to_thread(lambda: list(project_root.rglob("*.py")))
    return [
        f
        for f in python_files
        if not any(excluded in f.parts for excluded in EXCLUDED_DIRS)
    ]


def _get_connected_func_ids(call_edges: List[Dict]) -> set:
    """Get set of function IDs that appear in call edges."""
    connected_funcs = set()
    for edge in call_edges:
        connected_funcs.add(edge["from"])
        if edge["resolved"]:
            connected_funcs.add(edge["to"])
    return connected_funcs


def _build_function_node(func_id: str, info: Dict) -> Dict:
    """Build a single function node dict from function info."""
    return {
        "id": func_id,
        "name": info["name"],
        "full_name": info["full_name"],
        "module": info["module"],
        "class": info["class"],
        "file": info["file"],
        "line": info["line"],
        "is_async": info["is_async"],
    }


def _build_connected_nodes(
    functions: Dict[str, Dict],
    call_edges: List[Dict],
) -> List[Dict]:
    """Build graph nodes from connected functions (Issue #281: extracted)."""
    connected_funcs = _get_connected_func_ids(call_edges)

    nodes = []
    for func_id, info in functions.items():
        if func_id in connected_funcs:
            nodes.append(_build_function_node(func_id, info))
    return nodes


def _build_orphaned_nodes(
    functions: Dict[str, Dict],
    call_edges: List[Dict],
) -> List[Dict]:
    """
    Build list of orphaned functions (defined but never called or calling).

    Orphaned functions are those that:
    - Are not callers (don't appear in edge 'from')
    - Are not callees (don't appear in edge 'to' with resolved=True)

    Returns:
        List of orphaned function nodes sorted by module/file for easier review.
    """
    connected_funcs = _get_connected_func_ids(call_edges)

    orphaned = []
    for func_id, info in functions.items():
        if func_id not in connected_funcs:
            orphaned.append(_build_function_node(func_id, info))

    # Sort by module then name for easier review
    orphaned.sort(key=lambda x: (x["module"] or "", x["name"] or ""))
    return orphaned


def _deduplicate_edges(call_edges: List[Dict]) -> List[Dict]:
    """Deduplicate edges and add call counts (Issue #281: extracted)."""
    call_counts = {}
    for edge in call_edges:
        key = (edge["from"], edge["to"])
        call_counts[key] = call_counts.get(key, 0) + 1

    unique_edges = []
    seen_edges = set()
    for edge in call_edges:
        key = (edge["from"], edge["to"])
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(
                {
                    "from": edge["from"],
                    "to": edge["to"],
                    "to_name": edge["to_name"],
                    "resolved": edge["resolved"],
                    "count": call_counts[key],
                }
            )
    return unique_edges


def _calculate_metrics(unique_edges: List[Dict]) -> tuple:
    """Calculate call metrics and top callers/callees (Issue #281: extracted)."""
    outgoing_calls = {}
    incoming_calls = {}
    for edge in unique_edges:
        outgoing_calls[edge["from"]] = (
            outgoing_calls.get(edge["from"], 0) + edge["count"]
        )
        if edge["resolved"]:
            incoming_calls[edge["to"]] = (
                incoming_calls.get(edge["to"], 0) + edge["count"]
            )

    top_callers = sorted(
        [{"function": k, "calls": v} for k, v in outgoing_calls.items()],
        key=lambda x: x["calls"],
        reverse=True,
    )[:10]

    top_called = sorted(
        [{"function": k, "calls": v} for k, v in incoming_calls.items()],
        key=lambda x: x["calls"],
        reverse=True,
    )[:10]

    return top_callers, top_called


def _get_decorator_name(decorator) -> str:
    """
    Extract decorator name from AST node.

    Issue #665: Extracted from _create_function_visitor to reduce function length.

    Args:
        decorator: AST node representing a decorator

    Returns:
        Name of the decorator or "unknown" if cannot be determined
    """
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    if isinstance(decorator, ast.Call):
        func = decorator.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return "unknown"


def _extract_callee_name(node) -> str | None:
    """
    Extract callee name from Call AST node.

    Issue #665: Extracted from visit_Call to reduce nested class method size.

    Args:
        node: ast.Call node

    Returns:
        Callee name string or None if cannot be determined
    """
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _build_call_edge(
    caller_func: str,
    callee_name: str,
    callee_id: str | None,
    line: int,
) -> Dict:
    """
    Build call edge dictionary.

    Issue #665: Extracted from visit_Call to reduce nested class method size.

    Args:
        caller_func: ID of the calling function
        callee_name: Name of the called function
        callee_id: Resolved ID of callee or None
        line: Line number of the call

    Returns:
        Call edge dictionary
    """
    return {
        "from": caller_func,
        "to": callee_id or callee_name,
        "to_name": callee_name,
        "resolved": callee_id is not None,
        "line": line,
    }


def _resolve_via_import_context(
    callee_name: str,
    import_context: ImportContext,
    functions: Dict,
) -> tuple[str | None, bool]:
    """
    Resolve callee via import context.

    Issue #713: Extracted from _resolve_callee_id to reduce function length.

    Args:
        callee_name: Name of the called function
        import_context: Import context for the current file
        functions: Dictionary of registered functions

    Returns:
        Tuple of (resolved_id, is_external)
    """
    imported_path = import_context.resolve_name(callee_name)
    if not imported_path:
        return None, False

    # Check if it's an external library call
    if import_context.is_external(callee_name):
        return None, True  # External call, not truly unresolved

    # Try the imported path directly
    if imported_path in functions:
        return imported_path, False

    # Try variations (module.func vs module.Class.func)
    parts = imported_path.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i]) + "." + parts[-1]
        if candidate in functions:
            return candidate, False

    return None, False


def _resolve_callee_id(
    callee_name: str,
    module_path: str,
    current_class: str,
    functions: Dict,
    import_context: Optional[ImportContext] = None,
) -> tuple[str | None, bool]:
    """
    Resolve a callee name to its full function ID.

    Issue #665: Extracted from _create_function_visitor to reduce function length.
    Issue #713: Enhanced with import context for cross-module resolution.

    Args:
        callee_name: Name of the called function
        module_path: Current module path
        current_class: Current class context (or None)
        functions: Dictionary of registered functions
        import_context: Import context for the current file (Issue #713)

    Returns:
        Tuple of (resolved_id, is_external):
        - resolved_id: Function ID if found, None otherwise
        - is_external: True if call is to external library (not unresolved)
    """
    # Try module-level function first
    possible_id = f"{module_path}.{callee_name}"
    if possible_id in functions:
        return possible_id, False

    # Try class method if in class context
    if current_class:
        possible_id = f"{module_path}.{current_class}.{callee_name}"
        if possible_id in functions:
            return possible_id, False

    # Issue #713: Try resolving via import context
    if import_context:
        result = _resolve_via_import_context(callee_name, import_context, functions)
        if result[0] or result[1]:  # Found or is external
            return result

    # Issue #713: Check if callee_name itself is external (e.g., json.loads)
    if callee_name and "." in callee_name:
        base = callee_name.split(".")[0]
        if base in STDLIB_MODULES or base in COMMON_THIRD_PARTY:
            return None, True

    return None, False


def _build_function_info(
    node,
    func_id: str,
    full_name: str,
    file_path: str,
    module_path: str,
    current_class: str,
) -> Dict:
    """
    Build function information dictionary from AST node.

    Issue #665: Extracted from _create_function_visitor to reduce function length.

    Args:
        node: AST function definition node
        func_id: Full function identifier
        full_name: Display name of the function
        file_path: Source file path
        module_path: Module path
        current_class: Current class context (or None)

    Returns:
        Dictionary containing function metadata
    """
    return {
        "id": func_id,
        "name": node.name,
        "full_name": full_name,
        "file": file_path,
        "module": module_path,
        "class": current_class,
        "line": node.lineno,
        "is_async": isinstance(node, ast.AsyncFunctionDef),
        "args": len(node.args.args),
        "decorators": [_get_decorator_name(d) for d in node.decorator_list],
    }


def _compute_func_identity(
    node_name: str, module_path: str, current_class: Optional[str]
) -> tuple:
    """
    Compute function ID and full display name.

    Issue #665: Extracted from _create_function_visitor._process_function
    to reduce nested class method size.

    Args:
        node_name: Name of the function node
        module_path: Module path
        current_class: Current class context (or None)

    Returns:
        Tuple of (func_id, full_name)
    """
    if current_class:
        func_id = f"{module_path}.{current_class}.{node_name}"
        full_name = f"{current_class}.{node_name}"
    else:
        func_id = f"{module_path}.{node_name}"
        full_name = node_name
    return func_id, full_name


def _extract_import_context(tree: ast.AST) -> ImportContext:
    """
    Extract import context from an AST tree.

    Issue #713: Build import map for cross-module resolution.

    Args:
        tree: Parsed AST tree

    Returns:
        ImportContext with all imports from the file
    """
    ctx = ImportContext()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                ctx.add_import(module=alias.name, name=None, alias=alias.asname)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "*":
                    # Star import - can't track specific names
                    continue
                ctx.add_import(module=node.module, name=alias.name, alias=alias.asname)

    return ctx


class FunctionCallVisitor(ast.NodeVisitor):
    """
    AST visitor to extract function definitions and calls.

    Issue #713: Refactored to module level for reduced function length.
    Uses constructor injection for data collections instead of closure.
    """

    def __init__(
        self,
        file_path: str,
        module_path: str,
        functions: Dict,
        call_edges: List,
        external_calls: Optional[List] = None,
        import_context: Optional[ImportContext] = None,
    ):
        """Initialize visitor with file path, module context, and data stores."""
        self.file_path = file_path
        self.module_path = module_path
        self.functions = functions
        self.call_edges = call_edges
        self.external_calls = external_calls
        self.import_context = import_context
        self.current_class = None
        self.current_function = None
        self.function_stack = []

    def visit_ClassDef(self, node):
        """Visit class definition and track current class context."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node):
        """Visit synchronous function definition."""
        self._process_function(node)

    def visit_AsyncFunctionDef(self, node):
        """Visit asynchronous function definition."""
        self._process_function(node)

    def _process_function(self, node):
        """Process function node and register it with its call relationships."""
        func_id, full_name = _compute_func_identity(
            node.name, self.module_path, self.current_class
        )
        self.functions[func_id] = _build_function_info(
            node,
            func_id,
            full_name,
            self.file_path,
            self.module_path,
            self.current_class,
        )

        old_function = self.current_function
        self.current_function = func_id
        self.function_stack.append(func_id)
        self.generic_visit(node)
        self.function_stack.pop() if self.function_stack else None
        self.current_function = old_function

    def visit_Call(self, node):
        """Visit function call and record caller-callee relationship."""
        if not self.current_function:
            self.generic_visit(node)
            return

        callee_name = _extract_callee_name(node)
        if callee_name and callee_name not in BUILTIN_FUNCS:
            self._record_call(callee_name, node.lineno)

        self.generic_visit(node)

    def _record_call(self, callee_name: str, line: int):
        """Record a function call edge. Issue #713: Extracted for brevity."""
        callee_id, is_external = _resolve_callee_id(
            callee_name,
            self.module_path,
            self.current_class,
            self.functions,
            self.import_context,
        )

        if is_external and self.external_calls is not None:
            self.external_calls.append(
                {
                    "from": self.current_function,
                    "to_name": callee_name,
                    "line": line,
                }
            )
        else:
            self.call_edges.append(
                _build_call_edge(self.current_function, callee_name, callee_id, line)
            )


# =============================================================================
# API Endpoint
# =============================================================================


async def _get_cached_call_graph(project_root: str) -> Optional[dict]:
    """
    Get cached call graph from Redis.

    Issue #711: Cache call graph for 5 minutes to improve load times.
    Cache key is path-specific to handle different scan paths.

    Args:
        project_root: The root path being analyzed

    Returns:
        Cached call graph data or None if not cached/expired
    """
    try:
        cache_key = _get_cache_key(project_root)
        redis_client = get_redis_client(async_client=False, database="cache")
        cached = redis_client.get(cache_key)
        if cached:
            logger.debug("Call graph cache hit for path: %s", project_root)
            return json.loads(cached)
    except Exception as e:
        logger.debug("Cache read error (non-critical): %s", e)
    return None


async def _set_cached_call_graph(project_root: str, data: dict) -> None:
    """
    Cache call graph in Redis.

    Issue #711: Cache for 5 minutes (300 seconds).
    Cache key is path-specific to handle different scan paths.

    Args:
        project_root: The root path being analyzed
        data: Call graph response data to cache
    """
    try:
        cache_key = _get_cache_key(project_root)
        redis_client = get_redis_client(async_client=False, database="cache")
        redis_client.setex(cache_key, CALL_GRAPH_CACHE_TTL, json.dumps(data))
        logger.debug(
            "Call graph cached for %d seconds (path: %s)",
            CALL_GRAPH_CACHE_TTL,
            project_root,
        )
    except Exception as e:
        logger.debug("Cache write error (non-critical): %s", e)


async def _analyze_python_files(
    python_files: List[Path],
    project_root: Path,
    functions: Dict[str, Dict],
    call_edges: List[Dict],
    external_calls: Optional[List[Dict]] = None,
) -> None:
    """Analyze Python files and populate functions/call_edges.

    Issue #665: Extracted from get_call_graph to reduce function length.
    Issue #713: Added import context extraction for cross-module resolution.
    """
    for py_file in python_files[:300]:
        try:
            rel_path = str(py_file.relative_to(project_root))
            module_path = rel_path.replace("/", ".").replace(".py", "")
            try:
                async with aiofiles.open(py_file, "r", encoding="utf-8") as f:
                    content = await f.read()
            except OSError as e:
                logger.debug("Failed to read file for call graph %s: %s", py_file, e)
                continue
            tree = ast.parse(content)
            # Issue #713: Extract import context for cross-module resolution
            import_context = _extract_import_context(tree)
            visitor = FunctionCallVisitor(
                file_path=rel_path,
                module_path=module_path,
                functions=functions,
                call_edges=call_edges,
                external_calls=external_calls,
                import_context=import_context,
            )
            visitor.visit(tree)
        except Exception as e:
            logger.debug("Could not analyze %s: %s", py_file, e)


def _build_call_graph_response(
    functions: Dict,
    nodes: List,
    orphaned_nodes: List,
    unique_edges: List,
    top_callers: List,
    top_called: List,
    external_calls_count: int = 0,
) -> dict:
    """Build call graph response dictionary.

    Issue #665: Extracted from get_call_graph to reduce function length.
    Issue #713: Added external_calls_count to show filtered library calls.
    """
    resolved_count = len([e for e in unique_edges if e["resolved"]])
    unresolved_count = len([e for e in unique_edges if not e["resolved"]])

    return {
        "status": "success",
        "call_graph": {"nodes": nodes[:500], "edges": unique_edges[:2000]},
        "orphaned_functions": orphaned_nodes[:500],
        "summary": {
            "total_functions": len(functions),
            "connected_functions": len(nodes),
            "orphaned_functions": len(orphaned_nodes),
            "total_call_relationships": len(unique_edges),
            "resolved_calls": resolved_count,
            "unresolved_calls": unresolved_count,
            # Issue #713: New metrics for external calls
            "external_library_calls": external_calls_count,
            "resolution_rate": round(
                resolved_count / max(resolved_count + unresolved_count, 1) * 100, 1
            ),
            "top_callers": top_callers,
            "most_called": top_called,
        },
        "from_cache": False,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_call_graph",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/call-graph")
async def get_call_graph(
    refresh: bool = Query(False, description="Force refresh, bypass cache")
):
    """Get function call graph.

    Issue #281/#665/#711: Refactored with caching.
    Issue #713: Enhanced with import-aware cross-module resolution.
    """
    project_root = get_project_root()

    if not refresh:
        cached_data = await _get_cached_call_graph(str(project_root))
        if cached_data:
            cached_data["from_cache"] = True
            return JSONResponse(cached_data)

    python_files = await _get_python_files(project_root)
    functions: Dict[str, Dict] = {}
    call_edges: List[Dict] = []
    external_calls: List[Dict] = []  # Issue #713: Track external library calls

    await _analyze_python_files(
        python_files, project_root, functions, call_edges, external_calls
    )

    nodes = _build_connected_nodes(functions, call_edges)
    orphaned_nodes = _build_orphaned_nodes(functions, call_edges)
    unique_edges = _deduplicate_edges(call_edges)
    top_callers, top_called = _calculate_metrics(unique_edges)

    response_data = _build_call_graph_response(
        functions,
        nodes,
        orphaned_nodes,
        unique_edges,
        top_callers,
        top_called,
        external_calls_count=len(external_calls),  # Issue #713
    )
    await _set_cached_call_graph(str(project_root), response_data)

    return JSONResponse(response_data)
