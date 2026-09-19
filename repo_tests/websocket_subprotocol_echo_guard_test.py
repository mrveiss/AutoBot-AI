# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A module that authenticates a WebSocket must accept through ``accept_websocket`` (#16457).

When a client authenticates with ``Sec-WebSocket-Protocol: bearer, <jwt>``, the
server must echo ``bearer`` on ``accept()`` or the browser fails the handshake
(RFC 6455 section 4.2.2). A test client does not enforce that, so an endpoint that
calls ``websocket.accept()`` directly passes CI and breaks in every browser the
moment the frontend sends the header to it.

This fails any module that authenticates a WebSocket and awaits ``.accept(``
itself, so the echo cannot be left out again. Scoped to authenticating modules:
endpoints that never read the header do not need the echo.

TWO PRIOR GAPS, BOTH CLOSED HERE (#16457 review)
-------------------------------------------------
1. ``AUTHENTICATORS`` named only three functions, so a module authenticating
   *transitively* through a wrapper -- ``api/terminal.py`` and
   ``api/vnc_proxy.py`` call ``enforce_ws_terminal_auth`` /
   ``enforce_ws_desktop_auth``, which reach ``authenticate_websocket`` via
   ``enforce_ws_remote_control_auth`` -> ``enforce_ws_authentication`` -- was
   invisible to the scan. Both bare-accepted and both broke a browser sending
   the header, with CI green. The wrapper family is now named explicitly
   rather than resolved by call-graph analysis, which would need to track
   `ws_security.py` internals this guard has no reason to know about.
2. The scan covered only ``autobot-backend``. ``autobot-slm-backend`` runs the
   identical contract through its own ``_authenticate_websocket_token`` /
   ``ConnectionManager.connect``, entirely uncovered.

Reach is now declared through ``repo_tests._reach.declare`` rather than an
inline ``assert scanned >= N``, so ``reach_declarations_test`` can drive the
same discovery against an empty repository and prove the floor actually fires
-- an inline assert cannot be enumerated or driven that way.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

#: Backend directory name -> the names that authenticate a WebSocket in it.
#: ``autobot-backend`` funnels through ``auth_middleware.authenticate_websocket``
#: (directly, or via one of ``api/ws_security.py``'s wrappers -- gap 1 above).
#: ``autobot-slm-backend`` is a separate service with its own equivalent
#: (``api/websocket.py::_authenticate_websocket_token``) -- gap 2 above.
BACKEND_AUTHENTICATORS: dict[str, tuple[str, ...]] = {
    "autobot-backend": (
        "authenticate_websocket",
        "authenticate_ws_admin",
        "enforce_ws_admin",
        "enforce_ws_authentication",
        "enforce_ws_remote_control_auth",
        "enforce_ws_terminal_auth",
        "enforce_ws_desktop_auth",
        # #17009: the one call nine formerly unauthenticated endpoints now make; it
        # authenticates and accepts through ``accept_websocket`` itself.
        "open_authenticated_ws",
    ),
    "autobot-slm-backend": ("_authenticate_websocket_token",),
}


def _authenticates(tree: ast.AST, authenticators: tuple[str, ...]) -> bool:
    """Calls or imports one of *authenticators*."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in authenticators:
                return True
        if isinstance(node, ast.ImportFrom) and any(a.name in authenticators for a in node.names):
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


def _authenticating_modules(root: Path) -> list[Path]:
    """WebSocket-authenticating modules across both backends -- the reach population.

    Must return ``[]`` on an empty tree, never raise: ``reach_declarations_test``
    drives every declaration against an empty repository to prove its floor
    actually fires (#15826, #16457 review).
    """
    found: list[Path] = []
    for backend_name, authenticators in BACKEND_AUTHENTICATORS.items():
        backend_dir = root / backend_name
        if not backend_dir.is_dir():
            continue
        for path in sorted(backend_dir.rglob("*.py")):
            if path.name.endswith("_test.py") or path.name.startswith("test_"):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            if _authenticates(tree, authenticators):
                found.append(path)
    return found


#: MEASURED 2026-09-18 against this branch: 11 authenticating modules (10 in
#: `autobot-backend` -- the 7 the narrower detector already found, plus
#: `api/terminal.py` and `api/vnc_proxy.py` from gap 1, plus `api/ws_security.py`
#: itself, which imports `enforce_ws_admin` -- and 1 in `autobot-slm-backend`
#: from gap 2). `growth=5` covers a handful of new authenticating endpoints
#: before this needs a deliberate ratchet; this population moves with ordinary
#: feature work, unlike a fixed-cardinality set.
#:
#: RE-MEASURED 2026-09-18 for #17009: 19. The eight endpoint modules that used
#: to accept unauthenticated now authenticate through `open_authenticated_ws`:
#: `api/analytics.py`, `api/analytics_quality.py`, `api/knowledge_research_ws.py`,
#: `api/logs.py`, `api/long_running_operations.py`, `api/monitoring.py`,
#: `api/overseer_handlers.py` and `services/workflow_automation/ws_endpoint.py`.
#: All are in the population, with no exemption.
REACH = declare(
    "websocket-subprotocol-echo",
    discover=_authenticating_modules,
    floor=19,
    growth=5,
    what="WebSocket-authenticating backend modules",
)


def test_no_authenticating_module_accepts_without_the_echo() -> None:
    root = repo_root()
    # REACH.examined() asserts the floor itself: a scan that found no
    # authenticating modules would report zero offenders having looked at
    # nothing, which is exactly what the floor exists to catch.
    modules = REACH.examined(root)
    offenders: list[str] = []
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [f"{path.relative_to(root)}:{line}" for line in _direct_accepts(tree)]
    assert not offenders, (
        "these await `.accept(` directly in a module that authenticates a WebSocket; "
        "use `autobot_shared.websocket_subprotocol.accept_websocket(websocket)` so the "
        f"bearer subprotocol is echoed: {offenders}"
    )


def test_the_guard_catches_a_direct_accept() -> None:
    """Negative control: the detector fires on exactly the pattern it forbids."""
    offending = ast.parse(
        "async def ep(websocket):\n    await authenticate_websocket(websocket)\n    await websocket.accept()\n"
    )
    assert _authenticates(offending, BACKEND_AUTHENTICATORS["autobot-backend"])
    assert _direct_accepts(offending) == [3]


def test_the_guard_catches_a_direct_accept_after_the_open_helper() -> None:
    """#17009: a module that authenticates through ``open_authenticated_ws`` is in the
    population, so a stray bare ``accept()`` in it is caught like any other."""
    offending = ast.parse(
        "async def ep(websocket):\n    await open_authenticated_ws(websocket)\n    await websocket.accept()\n"
    )
    assert _authenticates(offending, BACKEND_AUTHENTICATORS["autobot-backend"])
    assert _direct_accepts(offending) == [3]


def test_the_guard_passes_the_helper_form() -> None:
    fixed = ast.parse(
        "async def ep(websocket):\n    await authenticate_websocket(websocket)\n    await accept_websocket(websocket)\n"
    )
    assert _authenticates(fixed, BACKEND_AUTHENTICATORS["autobot-backend"])
    assert _direct_accepts(fixed) == []


def test_the_guard_catches_a_wrapper_authenticated_endpoint() -> None:
    """Negative control for gap 1: a module reached only through a wrapper name.

    `api/terminal.py` never calls `authenticate_websocket` directly -- it calls
    `enforce_ws_terminal_auth`, which reaches it transitively. The narrower,
    three-name detector missed exactly this shape and both `terminal.py`
    accept() sites shipped unechoed; this proves the wrapper names are
    recognised so a *new* wrapper-authenticated endpoint that skips the echo
    cannot pass CI the same way.
    """
    offending = ast.parse(
        "async def ep(websocket):\n"
        "    user = await enforce_ws_terminal_auth(websocket)\n"
        "    if user is None:\n"
        "        return\n"
        "    await websocket.accept()\n"
    )
    assert _authenticates(offending, BACKEND_AUTHENTICATORS["autobot-backend"])
    assert _direct_accepts(offending) == [5]


def test_the_guard_catches_the_slm_backend_authenticator() -> None:
    """Negative control for gap 2: the second backend's own authenticator name."""
    offending = ast.parse(
        "async def ep(websocket):\n"
        "    if not await _authenticate_websocket_token(websocket):\n"
        "        return\n"
        "    await websocket.accept()\n"
    )
    assert _authenticates(offending, BACKEND_AUTHENTICATORS["autobot-slm-backend"])
    assert not _authenticates(offending, BACKEND_AUTHENTICATORS["autobot-backend"])
    assert _direct_accepts(offending) == [4]
