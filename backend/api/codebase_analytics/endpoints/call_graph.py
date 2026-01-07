# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Function call graph analysis endpoints
"""

import ast
import asyncio
import logging
from typing import Dict, List

import aiofiles
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from .shared import get_project_root

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Helper Functions for get_call_graph (Issue #281)
# =============================================================================

# Builtin functions to exclude from call graph
BUILTIN_FUNCS = {
    "print", "len", "range", "str", "int", "float", "list", "dict", "set",
    "tuple", "bool", "type", "isinstance", "hasattr", "getattr", "setattr",
    "open", "sorted", "enumerate", "zip", "map", "filter", "any", "all",
    "min", "max", "sum", "abs", "round", "format", "input", "super",
}

# Directories to exclude from analysis
EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env", "archive", "dist", "build",
}


async def _get_python_files(project_root) -> List:
    """Get filtered list of Python files for analysis (Issue #281: extracted)."""
    python_files = await asyncio.to_thread(lambda: list(project_root.rglob("*.py")))
    return [
        f for f in python_files
        if not any(excluded in f.parts for excluded in EXCLUDED_DIRS)
    ]


def _build_connected_nodes(
    functions: Dict[str, Dict],
    call_edges: List[Dict],
) -> List[Dict]:
    """Build graph nodes from connected functions (Issue #281: extracted)."""
    connected_funcs = set()
    for edge in call_edges:
        connected_funcs.add(edge["from"])
        if edge["resolved"]:
            connected_funcs.add(edge["to"])

    nodes = []
    for func_id, info in functions.items():
        if func_id in connected_funcs:
            nodes.append({
                "id": func_id,
                "name": info["name"],
                "full_name": info["full_name"],
                "module": info["module"],
                "class": info["class"],
                "file": info["file"],
                "line": info["line"],
                "is_async": info["is_async"],
            })
    return nodes


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
            unique_edges.append({
                "from": edge["from"],
                "to": edge["to"],
                "to_name": edge["to_name"],
                "resolved": edge["resolved"],
                "count": call_counts[key],
            })
    return unique_edges


def _calculate_metrics(unique_edges: List[Dict]) -> tuple:
    """Calculate call metrics and top callers/callees (Issue #281: extracted)."""
    outgoing_calls = {}
    incoming_calls = {}
    for edge in unique_edges:
        outgoing_calls[edge["from"]] = outgoing_calls.get(edge["from"], 0) + edge["count"]
        if edge["resolved"]:
            incoming_calls[edge["to"]] = incoming_calls.get(edge["to"], 0) + edge["count"]

    top_callers = sorted(
        [{"function": k, "calls": v} for k, v in outgoing_calls.items()],
        key=lambda x: x["calls"], reverse=True
    )[:10]

    top_called = sorted(
        [{"function": k, "calls": v} for k, v in incoming_calls.items()],
        key=lambda x: x["calls"], reverse=True
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


def _resolve_callee_id(
    callee_name: str,
    module_path: str,
    current_class: str,
    functions: Dict,
) -> str:
    """
    Resolve a callee name to its full function ID.

    Issue #665: Extracted from _create_function_visitor to reduce function length.

    Args:
        callee_name: Name of the called function
        module_path: Current module path
        current_class: Current class context (or None)
        functions: Dictionary of registered functions

    Returns:
        Resolved function ID or None if not found
    """
    # Try module-level function first
    possible_id = f"{module_path}.{callee_name}"
    if possible_id in functions:
        return possible_id

    # Try class method if in class context
    if current_class:
        possible_id = f"{module_path}.{current_class}.{callee_name}"
        if possible_id in functions:
            return possible_id

    return None


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


def _create_function_visitor(functions: Dict, call_edges: List):
    """
    Create FunctionCallVisitor class for AST analysis.

    Issue #281: Extracted from get_call_graph.
    Issue #665: Refactored to use extracted helpers for reduced function length.

    Args:
        functions: Dictionary to populate with function definitions
        call_edges: List to populate with call relationships

    Returns:
        FunctionCallVisitor class for use with ast.NodeVisitor
    """

    class FunctionCallVisitor(ast.NodeVisitor):
        """AST visitor to extract function definitions and calls."""

        def __init__(self, file_path: str, module_path: str):
            """Initialize visitor with file path and module context."""
            self.file_path = file_path
            self.module_path = module_path
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
            if self.current_class:
                func_id = f"{self.module_path}.{self.current_class}.{node.name}"
                full_name = f"{self.current_class}.{node.name}"
            else:
                func_id = f"{self.module_path}.{node.name}"
                full_name = node.name

            functions[func_id] = _build_function_info(
                node, func_id, full_name,
                self.file_path, self.module_path, self.current_class
            )

            old_function = self.current_function
            self.current_function = func_id
            self.function_stack.append(func_id)
            self.generic_visit(node)
            self.function_stack.pop() if self.function_stack else None
            self.current_function = old_function

        def visit_Call(self, node):
            """
            Visit function call and record caller-callee relationship.

            Issue #665: Refactored to use _extract_callee_name and _build_call_edge helpers.
            """
            if not self.current_function:
                self.generic_visit(node)
                return

            callee_name = _extract_callee_name(node)
            if callee_name and callee_name not in BUILTIN_FUNCS:
                callee_id = _resolve_callee_id(
                    callee_name, self.module_path, self.current_class, functions
                )
                call_edges.append(_build_call_edge(
                    self.current_function, callee_name, callee_id, node.lineno
                ))

            self.generic_visit(node)

    return FunctionCallVisitor


# =============================================================================
# API Endpoint
# =============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_call_graph",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/call-graph")
async def get_call_graph():
    """
    Get function call graph for visualization.

    Issue #281: Refactored from 247 lines to use extracted helper methods.

    Analyzes Python files to extract:
    - Function definitions (nodes)
    - Function calls within functions (edges)
    - Call depth and frequency metrics

    Returns data suitable for network/graph visualization.
    """
    project_root = get_project_root()

    # Get filtered Python files (Issue #281: uses helper)
    python_files = await _get_python_files(project_root)

    # Data structures for function and call tracking
    functions: Dict[str, Dict] = {}
    call_edges: List[Dict] = []

    # Create visitor class (Issue #281: uses helper)
    FunctionCallVisitor = _create_function_visitor(functions, call_edges)

    # Analyze files (limit for performance)
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
            visitor = FunctionCallVisitor(rel_path, module_path)
            visitor.visit(tree)

        except Exception as e:
            logger.debug("Could not analyze %s: %s", py_file, e)
            continue

    # Build graph data (Issue #281: uses helpers)
    nodes = _build_connected_nodes(functions, call_edges)
    unique_edges = _deduplicate_edges(call_edges)
    top_callers, top_called = _calculate_metrics(unique_edges)

    return JSONResponse({
        "status": "success",
        "call_graph": {
            "nodes": nodes[:500],
            "edges": unique_edges[:2000],
        },
        "summary": {
            "total_functions": len(functions),
            "connected_functions": len(nodes),
            "total_call_relationships": len(unique_edges),
            "resolved_calls": len([e for e in unique_edges if e["resolved"]]),
            "unresolved_calls": len([e for e in unique_edges if not e["resolved"]]),
            "top_callers": top_callers,
            "most_called": top_called,
        },
    })
