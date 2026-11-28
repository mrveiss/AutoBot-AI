# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The startup HNSW pickle repair runs in a worker thread, never on the event loop (#18789).

`repair_hnsw_pickles_locked` waits up to REPAIR_LOCK_TIMEOUT_SECONDS for a flock and
fsyncs files, so a direct call from the async startup path stalls every request.
"""

import ast
from pathlib import Path

_LIFESPAN = Path(__file__).with_name("lifespan.py")
_REPAIR = "repair_hnsw_pickles_locked"


def _repair_names(tree: ast.AST) -> set[str]:
    """Every local name bound to the repair function: imports (aliased or not) and plain re-binds."""
    names = {_REPAIR}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(a.asname or a.name for a in node.names if a.name == _REPAIR)
        elif isinstance(node, ast.Assign) and _is_repair_ref(node.value, names):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _is_repair_ref(expr: ast.expr, names: set[str]) -> bool:
    """A reference to the repair function: a bound name, or ``anything.repair_hnsw_pickles_locked``."""
    if isinstance(expr, ast.Name):
        return expr.id in names
    return isinstance(expr, ast.Attribute) and expr.attr == _REPAIR


def _repair_call_sites(tree: ast.AST) -> tuple[list[int], list[int]]:
    """(lines calling it directly, lines handing it to asyncio.to_thread), aliases and attributes included."""
    names, direct, threaded = _repair_names(tree), [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_repair_ref(node.func, names):
            direct.append(node.lineno)
        is_to_thread = isinstance(node.func, ast.Attribute) and node.func.attr == "to_thread"
        if is_to_thread and node.args and _is_repair_ref(node.args[0], names):
            threaded.append(node.lineno)
    return direct, threaded


def test_startup_repair_is_handed_to_a_worker_thread():
    direct, threaded = _repair_call_sites(ast.parse(_LIFESPAN.read_text(encoding="utf-8")))
    assert direct == [], f"{_REPAIR} called on the event loop at lifespan.py:{direct}"
    assert threaded, f"{_REPAIR} is no longer called from lifespan.py -- the #1390 post-index repair is gone"


def test_detector_sees_aliased_and_attribute_calls():
    """CodeRabbit on #18827: an alias or a module-attribute call must not slip past."""
    aliased = f"from utils.chromadb_store_repairs import {_REPAIR} as r\nasync def f(p):\n    r(p)\n"
    attribute = f"import utils.chromadb_store_repairs as mod\nasync def f(p):\n    mod.{_REPAIR}(p)\n"
    rebound = f"from x import {_REPAIR}\nfix = {_REPAIR}\nasync def f(p):\n    fix(p)\n"
    offloaded = f"import asyncio\nimport m\nasync def f(p):\n    await asyncio.to_thread(m.{_REPAIR}, p)\n"
    assert _repair_call_sites(ast.parse(aliased)) == ([3], [])
    assert _repair_call_sites(ast.parse(attribute)) == ([3], [])
    assert _repair_call_sites(ast.parse(rebound)) == ([4], [])
    assert _repair_call_sites(ast.parse(offloaded)) == ([], [4])


def test_detector_contrast():
    blocking = f"async def f(p):\n    {_REPAIR}(p)\n"
    offloaded = f"import asyncio\nasync def f(p):\n    await asyncio.to_thread({_REPAIR}, p)\n"
    assert _repair_call_sites(ast.parse(blocking)) == ([2], [])
    assert _repair_call_sites(ast.parse(offloaded)) == ([], [3])
