# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-banned-route-path — flag Enhanced/Unified/Consolidated era-markers in route paths.

A route like ``@router.post("/goal/enhanced")`` or ``@router.get("/search/unified")``
bakes an era-marker into the public API surface — the same canonical-debt as an
``EnhancedX`` class name, but on the wire. When a route is genuinely distinct it
must say WHAT it does (``/goal/orchestrated``, ``/search/multi-source``); when it
merely shadows a base route, fold it into the base and drop the segment.

This rule now covers **three** surfaces that can embed era-markers in mount paths:

1. ``@router.<method>("/path/with/era-marker")`` decorator strings  (production always)
2. ``include_router(..., prefix="/era-marker-prefix")`` keyword arguments  (always)
3. Registry-configuration tuples in ``initialization/router_registry/`` files —
   the 2nd string element of a tuple/list that starts with ``/`` is the mount prefix
   and is checked for banned tokens.  (scoped to router-registry files)

BLOCK severity — the backend / slm-backend routers are clean of these tokens
(verified #10746 / #10820). Only the hard era-markers are matched; domain adjectives such
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
DESCRIPTION = "Enhanced/Unified/Consolidated era-marker in a route path or mount prefix — rename to a descriptive path"
FIX_HINT = (
    "Rename the route/prefix to describe what it does, or fold it into the base route:\n"
    "    @router.post('/goal/enhanced')                      ->  @router.post('/goal/orchestrated')\n"
    "    @router.get('/search/unified')                      ->  @router.get('/search/multi-source')\n"
    "    include_router(r, prefix='/enhanced-data')          ->  include_router(r, prefix='/reporting')\n"
    "    ('api.x', '/unified', [...], 'x')  (registry)      ->  ('api.x', '/reporting', [...], 'x')\n"
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


def _is_router_registry_file(file_path: Path) -> bool:
    """Return True for files under initialization/router_registry/ that hold mount-config tuples."""
    return "router_registry" in file_path.parts


def _banned_token(path: str) -> str | None:
    """Return the first banned era-marker token found in *path* (lowercased), or None."""
    lowered = path.lower()
    return next((t for t in _BANNED_TOKENS if t in lowered), None)


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


def _include_router_prefix(call: ast.Call) -> tuple[ast.Constant, str] | None:
    """Return (node, prefix_str) if *call* is an include_router(…, prefix="…") call, else None."""
    func = call.func
    is_include_router = (isinstance(func, ast.Attribute) and func.attr == "include_router") or (
        isinstance(func, ast.Name) and func.id == "include_router"
    )
    if not is_include_router:
        return None
    for kw in call.keywords:
        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return (kw.value, kw.value.value)
    return None


def _registry_mount_prefix(node: ast.expr) -> tuple[ast.Constant, str] | None:
    """Return (node, prefix_str) if *node* is a registry tuple whose 2nd element is a /… string."""
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) < 2:
        return None
    second = node.elts[1]
    if isinstance(second, ast.Constant) and isinstance(second.value, str) and second.value.startswith("/"):
        return (second, second.value)
    return None


def _make_diagnostic(
    rule_id: str,
    issue: str,
    severity: str,
    file_path: Path,
    const_node: ast.Constant,
    prefix_str: str,
    token: str,
    label: str,
    lines: list[str],
    fix_hint: str,
) -> Diagnostic:
    idx = const_node.lineno - 1
    if 0 <= idx < len(lines) and _WAIVER.search(lines[idx]):
        return None  # type: ignore[return-value]
    return Diagnostic(
        rule_id=rule_id,
        issue=issue,
        severity=severity,
        file=file_path,
        line=const_node.lineno,
        col=const_node.col_offset,
        message=f"{label} '{prefix_str}' carries era-marker '{token}' — rename to a descriptive path",
        snippet=(lines[idx].strip()[:120] if 0 <= idx < len(lines) else ""),
        fix_hint=fix_hint,
    )


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    if _is_test_file(file_path):
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    diagnostics: list[Diagnostic] = []
    is_registry = _is_router_registry_file(file_path)

    for node in ast.walk(tree):
        # ── Surface 1: @router.<method>("/path") decorator strings ────────────
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                path = _route_path(decorator)
                if path is None:
                    continue
                token = _banned_token(path)
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

        # ── Surface 2: include_router(…, prefix="/banned-…") anywhere ─────────
        elif isinstance(node, ast.Call):
            result = _include_router_prefix(node)
            if result is not None:
                const_node, prefix_str = result
                token = _banned_token(prefix_str)
                if token is not None:
                    diag = _make_diagnostic(
                        RULE_ID,
                        ISSUE,
                        SEVERITY,
                        file_path,
                        const_node,
                        prefix_str,
                        token,
                        "mount prefix",
                        lines,
                        FIX_HINT,
                    )
                    if diag is not None:
                        diagnostics.append(diag)

        # ── Surface 3: registry-config tuples in router_registry files ────────
        if is_registry and isinstance(node, (ast.Tuple, ast.List)):
            result = _registry_mount_prefix(node)
            if result is not None:
                const_node, prefix_str = result
                token = _banned_token(prefix_str)
                if token is not None:
                    diag = _make_diagnostic(
                        RULE_ID,
                        ISSUE,
                        SEVERITY,
                        file_path,
                        const_node,
                        prefix_str,
                        token,
                        "registry prefix",
                        lines,
                        FIX_HINT,
                    )
                    if diag is not None:
                        diagnostics.append(diag)

    return diagnostics
