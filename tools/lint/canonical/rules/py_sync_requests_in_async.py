# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-sync-requests-in-async — flag blocking requests.* on async paths.

Async-first: a blocking ``requests.get/post/...`` inside an ``async def``
stalls the event loop. Use an async client (aiohttp / httpx.AsyncClient).
Nested sync ``def`` scopes are not flagged. See canonical-debt umbrella #10569.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-sync-requests-in-async"
ISSUE = "#10576"
SEVERITY = "block"
TARGETS = ["autobot-backend", "autobot-slm-backend"]
DESCRIPTION = "Blocking requests.* inside async def — use an async HTTP client"
FIX_HINT = "Replace requests.* with aiohttp/httpx.AsyncClient and await the call."

_METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "options", "request"})
_WAIVER = re.compile(r"#\s*canonical:\s*ignore\s+py-sync-requests-in-async\b")


def _calls_excluding_nested_funcs(fn: ast.AST):
    """Yield Call nodes inside fn, not descending into nested function scopes."""
    stack = list(getattr(fn, "body", []))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            yield node
        stack.extend(ast.iter_child_nodes(node))


def _is_requests_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _METHODS
        and isinstance(func.value, ast.Name)
        and func.value.id == "requests"
    )


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    diagnostics: list[Diagnostic] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        for call in _calls_excluding_nested_funcs(fn):
            if not _is_requests_call(call):
                continue
            idx = call.lineno - 1
            if 0 <= idx < len(lines) and _WAIVER.search(lines[idx]):
                continue
            diagnostics.append(
                Diagnostic(
                    rule_id=RULE_ID,
                    issue=ISSUE,
                    severity=SEVERITY,
                    file=file_path,
                    line=call.lineno,
                    col=call.col_offset,
                    message="blocking requests.* inside async def — use an async client",
                    snippet=(lines[idx].strip()[:120] if 0 <= idx < len(lines) else ""),
                    fix_hint=FIX_HINT,
                )
            )
    return diagnostics
