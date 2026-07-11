# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST-based safety guard for the compose tool's user scripts (GH#11568).

Validates Python source before sandbox execution (hard gate):
- import allowlist (top-level module names only)
- exec/eval/compile/__import__/globals/vars/locals/breakpoint AND the reflective
  accessors getattr/setattr/delattr/hasattr blocked as a bare Name reference ANYWHERE
  (call, decorator, rebind, argument), not only as a call func — closes ``@eval``,
  ``f = eval``, and ``g = getattr; g(...)`` aliasing escapes
- method-style ``obj.exec()``/``obj.eval()`` calls
- ANY dunder attribute access (``.__class__``, ``.__bases__``, ``.__subclasses__``, ...)
- subscripting ``__builtins__`` (or any dunder name)
- forbidden_work token name references
"""

import ast
import os
from dataclasses import dataclass, field

CODEEXEC_IMPORT_ALLOWLIST: frozenset[str] = frozenset(
    os.environ.get("AUTOBOT_CODEEXEC_IMPORT_ALLOWLIST", "autobot_tools,asyncio,json,re,math").split(",")
)

# Names that grant reflective / eval-like reach into the runtime; unrepresentable in v1.
# These are rejected as a bare Name load ANYWHERE (call func, decorator, RHS, arg),
# not only when directly called — ``@eval`` and ``f = eval`` are equally unsafe.
_BLOCKED_CALLS: frozenset[str] = frozenset(
    {"exec", "eval", "compile", "__import__", "globals", "vars", "locals", "breakpoint"}
)
# Reflective attribute accessors — rejected as bare Name references anywhere. They are
# never needed by the clean read-only shims, and permitting them re-opens computed-name,
# dunder-target, and accessor-aliasing (``g = getattr``) smuggling paths.
_GETSET_ATTR: frozenset[str] = frozenset({"getattr", "setattr", "delattr", "hasattr"})


@dataclass
class ASTGuardResult:
    """Result of an AST safety scan."""

    ok: bool
    violations: list[dict] = field(default_factory=list)


def _is_dunder(name: str) -> bool:
    """True for a Python dunder identifier (starts AND ends with ``__``)."""
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _check_import_node(node: ast.stmt) -> list[dict]:
    violations: list[dict] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top not in CODEEXEC_IMPORT_ALLOWLIST:
                violations.append({"line": node.lineno, "message": f"forbidden import: {top!r}"})
    elif isinstance(node, ast.ImportFrom):
        top = (node.module or "").split(".")[0]
        if top not in CODEEXEC_IMPORT_ALLOWLIST:
            violations.append({"line": node.lineno, "message": f"forbidden import: {top!r}"})
    return violations


def _check_call_node(node: ast.Call) -> list[dict]:
    """Reject method-style ``obj.exec()``/``obj.eval()`` etc.

    Bare-Name references to blocked builtins and reflective accessors are handled by
    ``_check_name_node`` (which fires in the call-func position too); this only adds
    the attribute-call form that has no bare Name to catch.
    """
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _BLOCKED_CALLS:
        return [{"line": getattr(node, "lineno", 0), "message": f"forbidden call: .{func.attr!r}"}]
    return []


def _check_attribute_node(node: ast.Attribute) -> list[dict]:
    """Reject any dunder attribute access (blocks __class__/__bases__/__subclasses__)."""
    if _is_dunder(node.attr):
        return [{"line": getattr(node, "lineno", 0), "message": f"dunder attribute access: .{node.attr}"}]
    return []


def _check_subscript_node(node: ast.Subscript) -> list[dict]:
    """Reject ``__builtins__[...]`` and subscripting any dunder name."""
    value = node.value
    if isinstance(value, ast.Name) and _is_dunder(value.id):
        return [{"line": getattr(node, "lineno", 0), "message": f"subscript of dunder name: {value.id}"}]
    return []


def _check_name_node(node: ast.Name, forbidden_work_tokens: frozenset[str]) -> list[dict]:
    """Reject a blocked-builtin, reflective-accessor, forbidden-token, or dunder name.

    Blocking these as a bare Name (not just a call func) closes decorator (``@eval``),
    rebind (``f = eval``), and accessor-aliasing (``g = getattr; g(...)``) escapes.
    The clean shims never reference eval/exec/getattr/hasattr/etc. at all.
    """
    lineno = getattr(node, "lineno", 0)
    if node.id in _BLOCKED_CALLS:
        return [{"line": lineno, "message": f"forbidden builtin reference: {node.id!r}"}]
    if node.id in _GETSET_ATTR:
        return [{"line": lineno, "message": f"reflective accessor reference: {node.id!r}"}]
    if node.id in forbidden_work_tokens:
        return [{"line": lineno, "message": f"forbidden token reference: {node.id!r}"}]
    if _is_dunder(node.id):
        return [{"line": lineno, "message": f"dunder name reference: {node.id!r}"}]
    return []


def check_script(script: str, forbidden_work_tokens: frozenset[str]) -> ASTGuardResult:
    """Parse and safety-scan *script*; return ASTGuardResult (hard gate)."""
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        return ASTGuardResult(ok=False, violations=[{"line": 0, "message": f"SyntaxError: {exc}"}])

    violations: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            violations.extend(_check_import_node(node))
        elif isinstance(node, ast.Call):
            violations.extend(_check_call_node(node))
        elif isinstance(node, ast.Attribute):
            violations.extend(_check_attribute_node(node))
        elif isinstance(node, ast.Subscript):
            violations.extend(_check_subscript_node(node))
        elif isinstance(node, ast.Name):
            violations.extend(_check_name_node(node, forbidden_work_tokens))
    return ASTGuardResult(ok=len(violations) == 0, violations=violations)
