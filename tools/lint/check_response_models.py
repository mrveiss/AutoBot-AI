#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pre-commit hook: verify response_model= endpoints return compatible shapes.

Any FastAPI endpoint annotated with response_model=<Schema> will raise an HTTP 500
ValidationError at runtime unless it returns a dict satisfying all required fields.
Static type checkers (mypy/pyright) do not validate response_model= decorator
arguments against actual return shapes — this hook fills that gap.

Checked schemas and their required fields:
  DataResponse              — requires 'success'
  SuccessMessageResponse    — requires 'success' + 'message'
  SuccessDataResponse       — requires 'success' + 'message'

For each, at least one of the following must be true:
  1. The function body calls create_success_response() [DataResponse only]
  2. A return statement contains a dict literal with all required keys
  3. The function returns a bypass type (JSONResponse, Response, StreamingResponse,
     FileResponse, PlainTextResponse, RedirectResponse) that skips FastAPI validation
  4. A local variable is assigned a dict literal containing all required keys and
     that variable is returned (single-assignment pattern — #5926)

Additionally, any schema name used in response_model= must be imported at a line
that appears BEFORE the decorator line. Import-after-use causes NameError at startup
(#6143).

Known limitation: multi-step variable builds (e.g. result = {}; result["success"] = True)
and pass-through returns of function-call results are not analyzed. Use
create_success_response() for those cases to satisfy the hook.

Exit codes:
  0 — clean
  1 — violations found
  2 — usage error

Background: #5843 → #5896 → #5904 cascade — 52+61 runtime-500 bugs introduced by
response_model=DataResponse on endpoints that returned plain dicts without 'success'.
Extended in #5925 to cover SuccessMessageResponse and SuccessDataResponse.
Extended in #6143 to catch import-after-decorator ordering bugs.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

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
ROUTE_METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "options", "route", "api_route"})

# Schemas with required fields (no defaults) that this hook validates.
# Maps schema name → frozenset of required key names that must appear in return dicts.
CHECKED_SCHEMAS: dict[str, frozenset[str]] = {
    "DataResponse": frozenset({"success"}),
    "SuccessMessageResponse": frozenset({"success", "message"}),
    "SuccessDataResponse": frozenset({"success", "message"}),
}

ALLOWLIST = {
    "tools/lint/check_response_models.py",
    "tools/lint/check_response_models_test.py",
}

_FuncNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def _scope_walk(node: ast.AST):
    """Walk AST descendants without entering nested function/class definitions."""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield from _scope_walk(child)


def _checked_schema(decorator: ast.expr) -> str | None:
    """Return the schema name if *decorator* is a route with a checked response_model."""
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in ROUTE_METHODS:
        return None
    for kw in decorator.keywords:
        if kw.arg == "response_model" and isinstance(kw.value, ast.Name) and kw.value.id in CHECKED_SCHEMAS:
            return kw.value.id
    return None


def _collect_import_line_map(tree: ast.Module) -> Dict[str, int]:
    """Return a mapping of imported name → first import line number.

    Covers all standard import forms:
      import foo                       → {"foo": line}
      import foo.bar as baz            → {"baz": line}
      from foo import Bar, Baz         → {"Bar": line, "Baz": line}
      from foo import Bar as B         → {"B": line}
    """
    name_to_line: Dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname if alias.asname else alias.name.split(".")[0]
                if bound_name not in name_to_line:
                    name_to_line[bound_name] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound_name = alias.asname if alias.asname else alias.name
                if bound_name not in name_to_line:
                    name_to_line[bound_name] = node.lineno
    return name_to_line


def _import_order_violation(schema: str, decorator_line: int, import_line_map: Dict[str, int]) -> Optional[str]:
    """Return an error message if *schema* is not imported before *decorator_line*.

    Returns None when the import is present and precedes the decorator.
    """
    if schema not in import_line_map:
        return f"{schema} used in response_model= at line {decorator_line} but never imported"
    import_line = import_line_map[schema]
    if import_line > decorator_line:
        return (
            f"{schema} imported at line {import_line} but used in response_model= "
            f"at line {decorator_line} (import must come first)"
        )
    return None


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


def _return_dict_keys(node: _FuncNode) -> set[str]:
    """Return the set of string keys found in any return dict literal in *node*."""
    keys: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            val = child.value
            if isinstance(val, ast.Dict):
                for key in val.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
    return keys


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


def _var_dict_keys(node: _FuncNode) -> dict[str, set[str]]:
    """Map local variable names to the union of keys from their dict literal assignments.

    Covers the single-assignment pattern:
        result = {"success": True, "data": ...}
        return result
    """
    var_keys: dict[str, set[str]] = {}
    for child in _scope_walk(node):
        if not isinstance(child, ast.Assign):
            continue
        if not isinstance(child.value, ast.Dict):
            continue
        keys: set[str] = set()
        for key in child.value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
        for target in child.targets:
            if isinstance(target, ast.Name):
                var_keys.setdefault(target.id, set()).update(keys)
    return var_keys


def _returned_var_names(node: _FuncNode) -> set[str]:
    """Return the set of local variable names that appear in bare return statements."""
    names: set[str] = set()
    for child in _scope_walk(node):
        if isinstance(child, ast.Return) and isinstance(child.value, ast.Name):
            names.add(child.value.id)
    return names


# Violation tuple: (line_no, func_name, error_message).
# ``error_message`` is None for return-shape violations (message is assembled in main).
_Violation = Tuple[int, str, Optional[str]]

_SHAPE_VIOLATION_MSG = None  # sentinel: use the standard return-shape message in main


def _check_file(path: Path, repo_root: Path) -> List[_Violation]:
    """Return [_Violation] for each problem found in *path*.

    Two classes of violations are detected:
      1. Return-shape mismatch — endpoint body lacks required keys for the schema.
         Tuple: (line_no, func_name, None)
      2. Import-order — schema name is imported after (or never before) its decorator.
         Tuple: (line_no, func_name, "<detail message>")
    """
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

    import_line_map = _collect_import_line_map(tree)
    violations: List[_Violation] = []
    for func_node in ast.walk(tree):
        if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in func_node.decorator_list:
            schema = _checked_schema(dec)
            if schema is None:
                continue
            # Check 1: import ordering — schema must be imported before the decorator.
            order_err = _import_order_violation(schema, dec.lineno, import_line_map)
            if order_err is not None:
                violations.append((func_node.lineno, func_node.name, order_err))
                break
            # Check 2: return-shape — body must satisfy required keys.
            required_keys = CHECKED_SCHEMAS[schema]
            if _returns_bypass_type(func_node):
                break
            if schema == "DataResponse" and _calls_create_success_response(func_node):
                break
            if required_keys.issubset(_return_dict_keys(func_node)):
                break
            # Single-assignment variable pattern: result = {"success": ...}; return result
            var_keys = _var_dict_keys(func_node)
            returned_vars = _returned_var_names(func_node)
            if any(required_keys.issubset(var_keys[name]) for name in returned_vars if name in var_keys):
                break
            violations.append((func_node.lineno, func_node.name, _SHAPE_VIOLATION_MSG))
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
        for line_no, func_name, detail in hits:
            if detail is not None:
                # Import-order violation — detail carries the specific message.
                print(
                    f"[{HOOK_ID}] {rel}:{line_no}: {func_name}(): {detail} (#6143)",
                    file=sys.stderr,
                )
            else:
                # Return-shape violation.
                print(
                    f"[{HOOK_ID}] {rel}:{line_no}: {func_name}() uses a checked response_model "
                    f"but body lacks the required return keys or a safe bypass. "
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
