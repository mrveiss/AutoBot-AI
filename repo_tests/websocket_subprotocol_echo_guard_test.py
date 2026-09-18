# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A module that authenticates a WebSocket must accept through ``accept_websocket`` (#16457).

When a client authenticates with ``Sec-WebSocket-Protocol: bearer, <jwt>``, the
server must echo ``bearer`` on ``accept()`` or the browser fails the handshake
(RFC 6455 section 4.2.2). A test client does not enforce that, so an endpoint that
calls ``websocket.accept()`` directly passes CI and breaks in every browser the
moment the frontend sends the header to it. Four such endpoints existed.

This fails any module that authenticates a WebSocket and awaits ``.accept(``
itself, so the echo cannot be left out again. Scoped to authenticating modules:
endpoints that never read the header do not need the echo.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

BACKEND = repo_root() / "autobot-backend"
HELPER = BACKEND / "websocket_subprotocol.py"
AUTHENTICATORS = ("authenticate_websocket", "authenticate_ws_admin", "enforce_ws_admin")


def _authenticates(tree: ast.AST) -> bool:
    """Calls or imports one of the WebSocket authenticators."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in AUTHENTICATORS:
                return True
        if isinstance(node, ast.ImportFrom) and any(a.name in AUTHENTICATORS for a in node.names):
            return True
    return False


def _direct_accepts(tree: ast.AST) -> list[int]:
    """Lines awaiting ``<anything>.accept(...)`` -- the call the helper exists to wrap."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "accept"
    ]


def _offenders() -> tuple[int, list[str]]:
    scanned, found = 0, []
    for path in sorted(BACKEND.rglob("*.py")):
        if path == HELPER or path.name.endswith("_test.py") or path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not _authenticates(tree):
            continue
        scanned += 1
        found += [f"{path.relative_to(BACKEND)}:{line}" for line in _direct_accepts(tree)]
    return scanned, found


def test_no_authenticating_module_accepts_without_the_echo() -> None:
    scanned, offenders = _offenders()
    # Reach, not just a clean result: a scan that found no authenticating modules
    # would report zero offenders having looked at nothing.
    assert scanned >= 7, f"only {scanned} authenticating modules found -- has discovery broken?"
    assert not offenders, (
        "these await `.accept(` directly in a module that authenticates a WebSocket; "
        "use `websocket_subprotocol.accept_websocket(websocket)` so the bearer "
        f"subprotocol is echoed: {offenders}"
    )


def test_the_guard_catches_a_direct_accept() -> None:
    """Negative control: the detector fires on exactly the pattern it forbids."""
    offending = ast.parse(
        "async def ep(websocket):\n    await authenticate_websocket(websocket)\n    await websocket.accept()\n"
    )
    assert _authenticates(offending)
    assert _direct_accepts(offending) == [3]


def test_the_guard_passes_the_helper_form() -> None:
    fixed = ast.parse(
        "async def ep(websocket):\n    await authenticate_websocket(websocket)\n    await accept_websocket(websocket)\n"
    )
    assert _authenticates(fixed)
    assert _direct_accepts(fixed) == []
