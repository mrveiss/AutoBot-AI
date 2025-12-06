# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Function call graph analysis endpoints
"""

import ast
import logging
from pathlib import Path
from typing import Dict, List

import aiofiles
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from .shared import get_project_root

logger = logging.getLogger(__name__)

router = APIRouter()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_call_graph",
    error_code_prefix="CODEBASE",
)
@router.get("/analytics/call-graph")
async def get_call_graph():
    """
    Get function call graph for visualization.

    Analyzes Python files to extract:
    - Function definitions (nodes)
    - Function calls within functions (edges)
    - Call depth and frequency metrics

    Returns data suitable for network/graph visualization.
    """
    project_root = get_project_root()
    python_files = list(project_root.rglob("*.py"))

    # Filter out unwanted directories
    excluded_dirs = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        "env", ".env", "archive", "dist", "build",
    }
    python_files = [
        f for f in python_files
        if not any(excluded in f.parts for excluded in excluded_dirs)
    ]

    # Data structures
    functions: Dict[str, Dict] = {}  # function_id -> function info
    call_edges: List[Dict] = []  # caller -> callee relationships
    builtin_funcs = {
        "print", "len", "range", "str", "int", "float", "list", "dict", "set",
        "tuple", "bool", "type", "isinstance", "hasattr", "getattr", "setattr",
        "open", "sorted", "enumerate", "zip", "map", "filter", "any", "all",
        "min", "max", "sum", "abs", "round", "format", "input", "super",
    }

    class FunctionCallVisitor(ast.NodeVisitor):
        """AST visitor to extract function definitions and calls."""

        def __init__(self, file_path: str, module_path: str):
            self.file_path = file_path
            self.module_path = module_path
            self.current_class = None
            self.current_function = None
            self.function_stack = []

        def visit_ClassDef(self, node):
            old_class = self.current_class
            self.current_class = node.name
            self.generic_visit(node)
            self.current_class = old_class

        def visit_FunctionDef(self, node):
            self._process_function(node)

        def visit_AsyncFunctionDef(self, node):
            self._process_function(node)

        def _process_function(self, node):
            # Build function ID
            if self.current_class:
                func_id = f"{self.module_path}.{self.current_class}.{node.name}"
                full_name = f"{self.current_class}.{node.name}"
            else:
                func_id = f"{self.module_path}.{node.name}"
                full_name = node.name

            # Store function info
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

            # Track calls within this function
            old_function = self.current_function
            self.current_function = func_id
            self.function_stack.append(func_id)
            self.generic_visit(node)
            self.function_stack.pop() if self.function_stack else None
            self.current_function = old_function

        def _get_decorator_name(self, decorator):
            if isinstance(decorator, ast.Name):
                return decorator.id
            elif isinstance(decorator, ast.Attribute):
                return decorator.attr
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    return decorator.func.id
                elif isinstance(decorator.func, ast.Attribute):
                    return decorator.func.attr
            return "unknown"

        def visit_Call(self, node):
            if not self.current_function:
                self.generic_visit(node)
                return

            callee_name = None

            # Get the function being called
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr

            if callee_name and callee_name not in builtin_funcs:
                # Look for matching function in our registry
                callee_id = None

                # Try module-level function
                possible_id = f"{self.module_path}.{callee_name}"
                if possible_id in functions:
                    callee_id = possible_id

                # Try class method if in a class
                if not callee_id and self.current_class:
                    possible_id = f"{self.module_path}.{self.current_class}.{callee_name}"
                    if possible_id in functions:
                        callee_id = possible_id

                # Create edge even if callee not fully resolved
                call_edges.append({
                    "from": self.current_function,
                    "to": callee_id or callee_name,
                    "to_name": callee_name,
                    "resolved": callee_id is not None,
                    "line": node.lineno,
                })

            self.generic_visit(node)

    # Analyze files (limit for performance)
    for py_file in python_files[:300]:
        try:
            rel_path = str(py_file.relative_to(project_root))
            module_path = rel_path.replace("/", ".").replace(".py", "")

            # Use aiofiles for non-blocking file I/O
            try:
                async with aiofiles.open(py_file, "r", encoding="utf-8") as f:
                    content = await f.read()
            except OSError as e:
                logger.debug(f"Failed to read file for call graph {py_file}: {e}")
                continue

            tree = ast.parse(content)
            visitor = FunctionCallVisitor(rel_path, module_path)
            visitor.visit(tree)

        except Exception as e:
            logger.debug(f"Could not analyze {py_file}: {e}")
            continue

    # Build graph nodes (only functions with connections)
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

    # Count call frequency
    call_counts = {}
    for edge in call_edges:
        key = (edge["from"], edge["to"])
        call_counts[key] = call_counts.get(key, 0) + 1

    # Deduplicate edges with count
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

    # Calculate metrics
    outgoing_calls = {}
    incoming_calls = {}
    for edge in unique_edges:
        outgoing_calls[edge["from"]] = outgoing_calls.get(edge["from"], 0) + edge["count"]
        if edge["resolved"]:
            incoming_calls[edge["to"]] = incoming_calls.get(edge["to"], 0) + edge["count"]

    # Top callers and callees
    top_callers = sorted(
        [{"function": k, "calls": v} for k, v in outgoing_calls.items()],
        key=lambda x: x["calls"], reverse=True
    )[:10]

    top_called = sorted(
        [{"function": k, "calls": v} for k, v in incoming_calls.items()],
        key=lambda x: x["calls"], reverse=True
    )[:10]

    return JSONResponse({
        "status": "success",
        "call_graph": {
            "nodes": nodes[:500],  # Limit for UI performance
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
