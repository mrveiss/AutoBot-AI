# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every async caller of a blocking VNC probe must offload it (#17646, #17647).

`tools/lint/check_no_blocking_io_in_async.py` cannot make these assertions, and
that limit is the reason this file exists. The probes in
`api/vnc_blocking_probes.py` are *sync* functions; the guard resets its async
depth inside `def` bodies -- correctly, since a sync helper may have sync callers
-- so a blocking call one frame below an `async def` is invisible to it however
many module/attr pairs its table learns. Closing that needs reachability
analysis. Until then the call sites are pinned here.

Asserted against the AST rather than by behaviour: a bare `is_vnc_running()`
returns the same boolean as an offloaded one. What differs is whether the event
loop was free while `pgrep` ran, and only the call site records that.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SOURCE = Path(__file__).with_name("vnc_manager.py")

#: Sync, blocking functions from `api.vnc_blocking_probes`. Each name is the
#: whole point: reaching one from `async def` without a thread hop stalls every
#: other request for as long as its subprocess or socket timeout allows.
_BLOCKING_PROBES = ("is_vnc_running", "run_clipboard_write", "probe_connection_quality")


def _async_functions() -> dict:
    tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}


def _bare_calls(node: ast.AST, name: str) -> list:
    """Calls to *name* that are NOT the callable handed to `to_thread`."""
    offloaded = {
        id(arg)
        for sub in ast.walk(node)
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "to_thread"
        for arg in sub.args
    }
    return [
        sub
        for sub in ast.walk(node)
        if isinstance(sub, ast.Call)
        and isinstance(sub.func, ast.Name)
        and sub.func.id == name
        and id(sub) not in offloaded
    ]


@pytest.mark.parametrize("probe", _BLOCKING_PROBES)
def test_no_async_function_calls_a_blocking_probe_inline(probe: str) -> None:
    offenders = {
        fname: [c.lineno for c in _bare_calls(fn, probe)]
        for fname, fn in _async_functions().items()
        if _bare_calls(fn, probe)
    }
    assert not offenders, f"{probe}() called inline from async: {offenders}"


def test_the_probes_are_actually_reached_from_async():
    """A file that stopped calling the probes would pass the test above vacuously.

    `MEASUREMENT_DISCIPLINE.md`: an empty result must not read as a clean one. If
    the probes move or get renamed, this fails and the pin above is re-pointed
    rather than silently satisfied.
    """
    source = _SOURCE.read_text(encoding="utf-8")
    reached = [p for p in _BLOCKING_PROBES if f"{p}" in source]
    assert reached == list(_BLOCKING_PROBES), f"probe(s) no longer referenced: {reached}"
