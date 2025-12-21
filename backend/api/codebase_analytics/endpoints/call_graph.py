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


def _create_function_visitor(functions: Dict, call_edges: List):
    """Create FunctionCallVisitor class for AST analysis (Issue #281: extracted)."""

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

            functions[func_id] = {
                "id": func_id,
                "name": node.name,
                "full_name": full_name,
                "file": self.file_path,
                "module": self.module_path,
                "class": self.current_class,
                "line": node.lineno,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "args": len(node.args.args),
                "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
            }

            old_function = self.current_function
            self.current_function = func_id
            self.function_stack.append(func_id)
            self.generic_visit(node)
            self.function_stack.pop() if self.function_stack else None
            self.current_function = old_function

        def _get_decorator_name(self, decorator):
            """Extract decorator name from AST node."""
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

        def visit_Call(self, node):
            """Visit function call and record caller-callee relationship."""
            if not self.current_function:
                self.generic_visit(node)
                return

            callee_name = None
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr

            if callee_name and callee_name not in BUILTIN_FUNCS:
                callee_id = None
                possible_id = f"{self.module_path}.{callee_name}"
                if possible_id in functions:
                    callee_id = possible_id

                if not callee_id and self.current_class:
                    possible_id = f"{self.module_path}.{self.current_class}.{callee_name}"
                    if possible_id in functions:
                        callee_id = possible_id

                call_edges.append({
                    "from": self.current_function,
                    "to": callee_id or callee_name,
                    "to_name": callee_name,
                    "resolved": callee_id is not None,
                    "line": node.lineno,
                })

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
