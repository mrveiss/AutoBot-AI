# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-client-disconnect-one-home — a disconnect handler must use the canonical classifier.

An ``except`` that handles ``WebSocketDisconnect``, ``ClientDisconnect``, a connection
reset/broken pipe, or ``ConnectionError`` / ``OSError`` around websocket send/receive is a
client-disconnect handler. Each one decided for itself whether the event is an error, which is
how a dropped peer reached the unhandled-exception log (#20939). The canonical home is
``autobot_shared.client_disconnect``: catch ``PEER_CLOSED_ERRORS`` (alone is enough for a handler
that is silent by design) and/or call ``log_client_disconnect`` / ``propagate_client_disconnect``,
or classify with ``is_client_disconnect``. A handler that bare re-raises, or re-raises or chains
the caught name, translates the error and is left alone; an unrelated ``raise`` does not count.
"""

from __future__ import annotations

import ast
from pathlib import Path

from autobot_shared.testfile_names import is_test_filename
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

# Always a client-disconnect handler.
HANDLED = frozenset({"WebSocketDisconnect", "ClientDisconnect", "ConnectionResetError", "BrokenPipeError"})
# Broad classes that mean a disconnect only on a client send/receive, so they count when the
# ``try`` body does websocket I/O (same ``on_send`` semantics as the classifier).
HANDLED_ON_SOCKET_IO = frozenset({"ConnectionError", "OSError"})
CANONICAL_CALLS = frozenset({"log_client_disconnect", "propagate_client_disconnect", "is_client_disconnect"})
_SOCKET_IO = frozenset(
    {"send", "send_text", "send_json", "send_bytes", "receive", "receive_text", "receive_json", "receive_bytes"}
)
_HOME = "autobot_shared/client_disconnect.py"


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Local name -> imported name, so ``WebSocketDisconnect as WSD`` is still seen."""
    table: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            table.update({a.asname: a.name for a in node.names if a.asname})
    return table


def _names(node: ast.AST | None, aliases: dict[str, str] | None = None) -> set[str]:
    """Every bare or attribute name an ``except`` clause mentions, import aliases resolved."""
    if node is None:
        return set()
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add((aliases or {}).get(sub.id, sub.id))
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
    return found


def _is_rethrow(node: ast.Raise, caught: str | None) -> bool:
    """A bare ``raise``, ``raise <caught>`` or ``raise ... from <caught>`` keeps the disconnect visible."""
    if node.exc is None:
        return True
    names = {n.id for n in (node.exc, node.cause) if isinstance(n, ast.Name)}
    return caught is not None and caught in names


def _calls_canonical(handler: ast.ExceptHandler, aliases: dict[str, str]) -> bool:
    if "PEER_CLOSED_ERRORS" in _names(handler.type, aliases):
        return True  # the canonical tuple is itself the classifier; the handler may stay silent
    for sub in ast.walk(handler):
        if isinstance(sub, ast.Raise) and _is_rethrow(sub, handler.name):
            return True
        if isinstance(sub, ast.Call) and (_names(sub.func) & CANONICAL_CALLS):
            return True
    return False


def _does_socket_io(body: list[ast.stmt]) -> bool:
    """True when the statements call send/receive on something named like a websocket."""
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr in _SOCKET_IO:
                owner = ast.unparse(sub.func.value).lower()
                if owner == "ws" or owner.endswith(("websocket", ".ws")):
                    return True
    return False


def _in_scope(rel: str) -> bool:
    if rel == _HOME or is_test_filename(Path(rel).name) or "/tests/" in rel:
        return False
    return rel.startswith(tuple(f"{t}/" for t in TARGETS))


def _rel(file_path: Path, ctx: Context) -> str:
    try:
        return file_path.resolve().relative_to(ctx.repo_root.resolve()).as_posix()
    except ValueError:
        return file_path.as_posix()


def _handles_disconnect(names: set[str], body: list[ast.stmt]) -> bool:
    return bool(names & HANDLED) or (bool(names & HANDLED_ON_SOCKET_IO) and _does_socket_io(body))


def violations(tree: ast.AST) -> list[ast.ExceptHandler]:
    """Disconnect handlers that neither use the canonical home nor re-raise it."""
    aliases = _aliases(tree)
    found: list[ast.ExceptHandler] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if _handles_disconnect(_names(handler.type, aliases), node.body) and not _calls_canonical(handler, aliases):
                found.append(handler)
    return found


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
