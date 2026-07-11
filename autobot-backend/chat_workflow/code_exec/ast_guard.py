# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST-based safety guard for the compose tool's user scripts (GH#11568).

Validates Python source before sandbox execution (hard gate):
- import allowlist (top-level module names only)
- exec/eval/compile/__import__/globals/vars/locals/breakpoint call block
- getattr/setattr smuggling on the autobot_tools module (incl. import aliases)
- ANY dunder attribute access (``.__class__``, ``.__bases__``, ``.__subclasses__``, ...)
- subscripting ``__builtins__``
- forbidden_work token name references
"""

import ast
import os
from dataclasses import dataclass, field

CODEEXEC_IMPORT_ALLOWLIST: frozenset[str] = frozenset(
    os.environ.get("AUTOBOT_CODEEXEC_IMPORT_ALLOWLIST", "autobot_tools,asyncio,json,re,math").split(",")
)

# Names that grant reflective / eval-like reach into the runtime; unrepresentable in v1.
_BLOCKED_CALLS: frozenset[str] = frozenset(
    {"exec", "eval", "compile", "__import__", "globals", "vars", "locals", "breakpoint"}
)
_GETSET_ATTR: frozenset[str] = frozenset({"getattr", "setattr", "delattr"})
_TOOLS_MODULE = "autobot_tools"


@dataclass
class ASTGuardResult:
    """Result of an AST safety scan."""

    ok: bool
    violations: list[dict] = field(default_factory=list)


def _is_dunder(name: str) -> bool:
    """True for a Python dunder identifier (starts AND ends with ``__``)."""
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _tools_aliases(tree: ast.AST) -> frozenset[str]:
    """Local names bound to the autobot_tools module (``import autobot_tools as t``)."""
    aliases = {_TOOLS_MODULE}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == _TOOLS_MODULE:
                    aliases.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return frozenset(aliases)


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


def _arg_targets_tools(arg: ast.expr, tools_aliases: frozenset[str]) -> bool:
    """True when *arg* references the tools module (a bound Name, or any Attribute)."""
    if isinstance(arg, ast.Name):
        return arg.id in tools_aliases
    return isinstance(arg, ast.Attribute)


def _check_call_node(node: ast.Call, tools_aliases: frozenset[str]) -> list[dict]:
    violations: list[dict] = []
    lineno = getattr(node, "lineno", 0)
    func = node.func
    if isinstance(func, ast.Name):
        if func.id in _BLOCKED_CALLS:
            violations.append({"line": lineno, "message": f"forbidden call: {func.id!r}"})
        if func.id in _GETSET_ATTR and node.args and _arg_targets_tools(node.args[0], tools_aliases):
            violations.append({"line": lineno, "message": f"attribute smuggling via {func.id!r}"})
    elif isinstance(func, ast.Attribute) and func.attr in _BLOCKED_CALLS:
        violations.append({"line": lineno, "message": f"forbidden call: .{func.attr!r}"})
    return violations


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
    if node.id in forbidden_work_tokens or _is_dunder(node.id):
        reason = "forbidden token reference" if node.id in forbidden_work_tokens else "dunder name reference"
        return [{"line": getattr(node, "lineno", 0), "message": f"{reason}: {node.id!r}"}]
    return []


def check_script(script: str, forbidden_work_tokens: frozenset[str]) -> ASTGuardResult:
    """Parse and safety-scan *script*; return ASTGuardResult (hard gate)."""
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        return ASTGuardResult(ok=False, violations=[{"line": 0, "message": f"SyntaxError: {exc}"}])

    tools_aliases = _tools_aliases(tree)
    violations: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            violations.extend(_check_import_node(node))
        elif isinstance(node, ast.Call):
            violations.extend(_check_call_node(node, tools_aliases))
        elif isinstance(node, ast.Attribute):
            violations.extend(_check_attribute_node(node))
        elif isinstance(node, ast.Subscript):
            violations.extend(_check_subscript_node(node))
        elif isinstance(node, ast.Name):
            violations.extend(_check_name_node(node, forbidden_work_tokens))
    return ASTGuardResult(ok=len(violations) == 0, violations=violations)
