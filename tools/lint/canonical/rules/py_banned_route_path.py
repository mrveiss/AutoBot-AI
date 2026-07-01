# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-banned-route-path — flag Enhanced/Unified/Consolidated era-markers in route paths.

A route like ``@router.post("/goal/enhanced")`` or ``@router.get("/search/unified")``
bakes an era-marker into the public API surface — the same canonical-debt as an
``EnhancedX`` class name, but on the wire. When a route is genuinely distinct it
must say WHAT it does (``/goal/orchestrated``, ``/search/multi-source``); when it
merely shadows a base route, fold it into the base and drop the segment.

BLOCK severity — the backend / slm-backend routers are clean of these tokens
(verified #10746). Only the hard era-markers are matched; domain adjectives such
as ``/advanced-stats`` or ``/advanced_search`` (pre-existing RAG feature) are NOT
flagged — synonym judgement is left to review, not the linter. See #10569 / #10746.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-banned-route-path"
ISSUE = "#10746"
SEVERITY = "block"
TARGETS = ["autobot-backend", "autobot-slm-backend"]
DESCRIPTION = "Enhanced/Unified/Consolidated era-marker in a route path — rename to a descriptive path"
FIX_HINT = (
    "Rename the route to describe what it does, or fold it into the base route:\n"
    "    @router.post('/goal/enhanced')   ->  @router.post('/goal/orchestrated')\n"
    "    @router.get('/search/unified')   ->  @router.get('/search/multi-source')\n"
    "  Never a synonym (/advanced, /aggregated). Suppress with:\n"
    "    # canonical: ignore py-banned-route-path — <reason> (#NNNN)"
)

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head"})
_BANNED_TOKENS = ("enhanced", "unified", "consolidated")
_WAIVER = re.compile(r"#\s*canonical:\s*ignore\s+py-banned-route-path\b")


def _is_test_file(file_path: Path) -> bool:
    """Tests may define fixture routes with legacy paths for migration coverage."""
    name = file_path.name
    return name.endswith("_test.py") or name.startswith("test_") or "tests" in file_path.parts


def _route_path(decorator: ast.expr) -> str | None:
    """Return the path string of an @router.<method>("...") decorator, else None."""
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute) or func.attr.lower() not in _HTTP_METHODS:
        return None
    if not decorator.args:
        return None
    first = decorator.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    if _is_test_file(file_path):
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    diagnostics: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            path = _route_path(decorator)
            if path is None:
                continue
            lowered = path.lower()
            token = next((t for t in _BANNED_TOKENS if t in lowered), None)
            if token is None:
                continue
            idx = decorator.lineno - 1
            if 0 <= idx < len(lines) and _WAIVER.search(lines[idx]):
                continue
            diagnostics.append(
                Diagnostic(
                    rule_id=RULE_ID,
                    issue=ISSUE,
                    severity=SEVERITY,
                    file=file_path,
                    line=decorator.lineno,
                    col=decorator.col_offset,
                    message=f"route path '{path}' carries era-marker '{token}' — rename to a descriptive path",
                    snippet=(lines[idx].strip()[:120] if 0 <= idx < len(lines) else ""),
                    fix_hint=FIX_HINT,
                )
            )
    return diagnostics
