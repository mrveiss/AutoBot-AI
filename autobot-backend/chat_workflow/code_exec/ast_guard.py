# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST-based safety guard for the compose tool's user scripts (GH#11568).

Validates Python source before sandbox execution:
- import allowlist
- exec/eval/compile/__import__ call block
- getattr/setattr smuggling block
- forbidden_work token name check
"""

import ast
import os
from dataclasses import dataclass, field

CODEEXEC_IMPORT_ALLOWLIST: frozenset[str] = frozenset(
    os.environ.get("AUTOBOT_CODEEXEC_IMPORT_ALLOWLIST", "autobot_tools,asyncio,json,re,math").split(",")
)

_BLOCKED_CALLS: frozenset[str] = frozenset({"exec", "eval", "compile", "__import__"})
_GETSET_ATTR: frozenset[str] = frozenset({"getattr", "setattr"})


@dataclass
class ASTGuardResult:
    """Result of an AST safety scan."""

    ok: bool
    violations: list[dict] = field(default_factory=list)


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
    violations: list[dict] = []
    lineno = node.lineno if hasattr(node, "lineno") else 0
    if isinstance(node.func, ast.Name):
        if node.func.id in _BLOCKED_CALLS:
            violations.append({"line": lineno, "message": f"forbidden call: {node.func.id!r}"})
        if node.func.id in _GETSET_ATTR and node.args and isinstance(node.args[0], ast.Name):
            if node.args[0].id == "autobot_tools":
                violations.append({"line": lineno, "message": f"attribute smuggling via {node.func.id!r}"})
    elif isinstance(node.func, ast.Attribute):
        if node.func.attr in _BLOCKED_CALLS:
            violations.append({"line": lineno, "message": f"forbidden call: .{node.func.attr!r}"})
    return violations


def _check_name_node(node: ast.Name, forbidden_work_tokens: frozenset[str]) -> list[dict]:
    if node.id in forbidden_work_tokens:
        lineno = node.lineno if hasattr(node, "lineno") else 0
        return [{"line": lineno, "message": f"forbidden token reference: {node.id!r}"}]
    return []


def check_script(script: str, forbidden_work_tokens: frozenset[str]) -> ASTGuardResult:
    """Parse and safety-scan *script*; return ASTGuardResult."""
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
        elif isinstance(node, ast.Name):
            violations.extend(_check_name_node(node, forbidden_work_tokens))
    return ASTGuardResult(ok=len(violations) == 0, violations=violations)
