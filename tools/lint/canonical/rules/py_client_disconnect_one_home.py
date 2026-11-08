# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-client-disconnect-one-home — a disconnect handler must use the canonical classifier.

An ``except`` that handles ``WebSocketDisconnect``, ``ClientDisconnect`` or a
connection reset/broken pipe is a client-disconnect handler. Each one decides for itself
whether the event is an error, which is how a dropped peer reached the unhandled-exception
log (#20939). The canonical home is ``autobot_shared.client_disconnect``: catch
``PEER_CLOSED_ERRORS`` and call ``log_client_disconnect`` / ``propagate_client_disconnect``,
or classify with ``is_client_disconnect``. Catching ``PEER_CLOSED_ERRORS`` alone also
counts, for a handler that was silent by design. A handler that re-raises translates the error
and is left alone.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-client-disconnect-one-home"
ISSUE = "#20939"
SEVERITY = "block"
TARGETS = ["autobot-backend", "autobot-slm-backend", "autobot_shared"]
DESCRIPTION = "Client-disconnect handler bypasses autobot_shared.client_disconnect"
FIX_HINT = (
    "Use the canonical classifier and logger:\n"
    "    from autobot_shared.client_disconnect import PEER_CLOSED_ERRORS, log_client_disconnect\n"
    "    except PEER_CLOSED_ERRORS as disconnect:\n"
    '        log_client_disconnect(logger, disconnect, "<operation>")'
)

HANDLED = frozenset({"WebSocketDisconnect", "ClientDisconnect", "ConnectionResetError", "BrokenPipeError"})
CANONICAL_CALLS = frozenset({"log_client_disconnect", "propagate_client_disconnect", "is_client_disconnect"})
_HOME = "autobot_shared/client_disconnect.py"


def _names(node: ast.AST | None) -> set[str]:
    """Every bare or attribute name an ``except`` clause mentions."""
    if node is None:
        return set()
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
    return found


def _calls_canonical(handler: ast.ExceptHandler) -> bool:
    if "PEER_CLOSED_ERRORS" in _names(handler.type):
        return True  # the canonical tuple is itself the classifier; the handler may stay silent
    for sub in ast.walk(handler):
        if isinstance(sub, ast.Raise):
            return True
        if isinstance(sub, ast.Call) and (_names(sub.func) & CANONICAL_CALLS):
            return True
    return False


def _in_scope(rel: str) -> bool:
    if rel == _HOME or rel.endswith("_test.py") or "/tests/" in rel or Path(rel).name.startswith("test_"):
        return False
    return rel.startswith(tuple(f"{t}/" for t in TARGETS))


def _rel(file_path: Path, ctx: Context) -> str:
    try:
        return file_path.resolve().relative_to(ctx.repo_root.resolve()).as_posix()
    except ValueError:
        return file_path.as_posix()


def violations(tree: ast.AST) -> list[ast.ExceptHandler]:
    """Disconnect handlers that neither use the canonical home nor re-raise."""
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ExceptHandler) and (_names(n.type) & HANDLED) and not _calls_canonical(n)
    ]


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    if not _in_scope(_rel(file_path, ctx)):
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [
        Diagnostic(
            rule_id=RULE_ID,
            issue=ISSUE,
            severity=SEVERITY,
            file=file_path,
            line=h.lineno,
            col=h.col_offset,
            message="client-disconnect handler does not use autobot_shared.client_disconnect",
            snippet=lines[h.lineno - 1].strip()[:120] if 0 < h.lineno <= len(lines) else "",
            fix_hint=FIX_HINT,
        )
        for h in violations(tree)
    ]
