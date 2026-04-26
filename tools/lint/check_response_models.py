#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pre-commit hook: verify response_model=DataResponse endpoints return compatible shapes.

Any FastAPI endpoint annotated with response_model=DataResponse will raise an HTTP 500
ValidationError at runtime unless it returns a dict with a 'success' key (required, no
default).  Static type checkers (mypy/pyright) do not validate response_model= decorator
arguments against actual return shapes — this hook fills that gap.

Implements the minimum viable check from issue #5913:

  For every route decorated with response_model=DataResponse, at least one of:
    1. The function body calls create_success_response()
    2. A return statement contains a dict literal with key 'success'
    3. The function returns a bypass type (JSONResponse, Response, StreamingResponse,
       FileResponse, PlainTextResponse, RedirectResponse) that skips FastAPI validation

Exit codes:
  0 — clean
  1 — violations found
  2 — usage error

Background: #5843 → #5896 → #5904 cascade — 52 runtime-500 bugs introduced by
response_model=DataResponse on endpoints that returned plain dicts without 'success'.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Tuple, Union

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402

HOOK_ID = "response-model-data-response"

# FastAPI response types whose direct return bypasses response_model validation.
BYPASS_TYPES = frozenset(
    {
        "JSONResponse",
        "Response",
        "StreamingResponse",
        "FileResponse",
        "PlainTextResponse",
        "HTMLResponse",
        "RedirectResponse",
    }
)

# Route decorator attribute names accepted by FastAPI routers.
ROUTE_METHODS = frozenset(
    {"get", "post", "put", "delete", "patch", "head", "options", "route", "api_route"}
)

ALLOWLIST = {
    "tools/lint/check_response_models.py",
    "tools/lint/check_response_models_test.py",
}

_FuncNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def _has_data_response_model(decorator: ast.expr) -> bool:
    """Return True if *decorator* is a route call with response_model=DataResponse."""
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in ROUTE_METHODS:
        return False
    for kw in decorator.keywords:
        if (
            kw.arg == "response_model"
            and isinstance(kw.value, ast.Name)
            and kw.value.id == "DataResponse"
        ):
            return True
    return False


def _calls_create_success_response(node: _FuncNode) -> bool:
    """Return True if the function body calls create_success_response()."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id == "create_success_response":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "create_success_response":
                return True
    return False


def _returns_success_dict(node: _FuncNode) -> bool:
    """Return True if any return statement yields a dict literal with key 'success'."""
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            val = child.value
            if isinstance(val, ast.Dict):
                for key in val.keys:
                    if isinstance(key, ast.Constant) and key.value == "success":
                        return True
    return False


def _returns_bypass_type(node: _FuncNode) -> bool:
    """Return True if the function returns a bypass response object directly."""
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            val = child.value
            if isinstance(val, ast.Call):
                func = val.func
                if isinstance(func, ast.Name) and func.id in BYPASS_TYPES:
                    return True
                if isinstance(func, ast.Attribute) and func.attr in BYPASS_TYPES:
                    return True
    return False


def _check_file(path: Path, repo_root: Path) -> List[Tuple[int, str]]:
    """Return [(line_no, func_name)] for each DataResponse violation in *path*."""
    try:
        rel = str(path.resolve().relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel = str(path)
    if rel in ALLOWLIST:
        return []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    violations: List[Tuple[int, str]] = []
    for func_node in ast.walk(tree):
        if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in func_node.decorator_list:
            if not _has_data_response_model(dec):
                continue
            if (
                _calls_create_success_response(func_node)
                or _returns_success_dict(func_node)
                or _returns_bypass_type(func_node)
            ):
                break
            violations.append((func_node.lineno, func_node.name))
            break
    return violations


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    files = list(iter_python_files(argv[1:], repo_root))
    total = 0
    for path in files:
        hits = _check_file(path, repo_root)
        if not hits:
            continue
        try:
            rel = path.resolve().relative_to(repo_root)
        except ValueError:
            rel = path
        for line_no, func_name in hits:
            print(
                f"[{HOOK_ID}] {rel}:{line_no}: {func_name}() has response_model=DataResponse "
                f"but body lacks create_success_response() or a return dict with 'success'. "
                f"Use create_success_response() or a named schema instead. (#5913)",
                file=sys.stderr,
            )
            total += 1
    if total:
        print(
            f"\n[{HOOK_ID}] {total} violation(s). "
            f"Fix: add create_success_response() or change response_model= to a named schema.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
