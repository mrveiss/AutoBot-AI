# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No test decides a call assertion with a fixed sleep (#16224).

``await asyncio.sleep(0.05)`` followed by ``store.write.assert_called_once()`` is
a claim about how much wall clock a shared runner grants a background task. A
loaded runner that has not scheduled the task yet produces exactly the red a real
regression produces, so the red cannot say which one it saw. #16009 found these
sites and #16224 fixed the last of them; this guard names any new one, with the
fix: wait on the observable with ``autobot_shared.eventually.eventually``.

The shape it flags, in a collectable test's OWN body -- never a nested helper, a
fake loop or a lambda, which ``own_nodes`` skips -- is a statement
``await asyncio.sleep(<positive constant>)`` followed within ``_WINDOW_LINES``
lines by a positive call assertion: an ``assert_called*`` / ``assert_awaited*``
call, or an ``assert`` that reads ``.call_count`` / ``.await_count``. The
``assert_not_*`` forms are spared: a slow runner can make them pass vacuously but
cannot turn them red, which is a different defect from the one this guards.
"""

from __future__ import annotations

import ast
import functools
import re

from repo_tests.collected_test_model import REPO_ROOT, collectable_tests, own_nodes, parse_module, test_modules

_WINDOW_LINES = 8
#: Measured 2026-09-11 with ``test_modules()``'s own population rules: 2316 test
#: modules holding 30717 collectable tests. The floors sit just below, so an
#: enumeration that silently loses a subtree fails here instead of reading clean.
_MIN_MODULES = 2250
_MIN_TEST_FUNCTIONS = 30000
_CALL_ASSERTION = re.compile(r"\.assert_(?:called|awaited)\w*\(|\.(?:call|await)_count\b")


def _is_fixed_sleep(node: ast.AST) -> bool:
    if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Await)):
        return False
    call = node.value.value
    if not (isinstance(call, ast.Call) and ast.unparse(call.func) == "asyncio.sleep" and call.args):
        return False
    delay = call.args[0]
    return isinstance(delay, ast.Constant) and isinstance(delay.value, (int, float)) and delay.value > 0


def _is_call_assertion(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return bool(_CALL_ASSERTION.search(ast.unparse(node)))
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        return bool(_CALL_ASSERTION.search(ast.unparse(node.value.func) + "("))
    return False


def fixed_sleep_call_assertions(tree: ast.Module) -> list[int]:
    """Line of every fixed sleep that a call assertion follows, as the module docstring defines."""
    found: list[int] = []
    for function in collectable_tests(tree):
        statements = sorted(own_nodes(function, (ast.stmt,)), key=lambda node: node.lineno)
        for index, node in enumerate(statements):
            if not _is_fixed_sleep(node):
                continue
            window = [s for s in statements[index + 1 :] if s.lineno <= node.lineno + _WINDOW_LINES]
            if any(_is_call_assertion(s) for s in window):
                found.append(node.lineno)
    return found


@functools.lru_cache(maxsize=1)
def _sweep() -> tuple[int, int, tuple[str, ...]]:
    modules = test_modules()
    tests = 0
    offenders: list[str] = []
    for path in modules:
        tree = parse_module(path)
        tests += len(collectable_tests(tree))
        relative = path.relative_to(REPO_ROOT)
        offenders.extend(f"{relative}:{line}" for line in fixed_sleep_call_assertions(tree))
    return len(modules), tests, tuple(offenders)


def test_the_population_is_present_and_large_enough_to_mean_anything() -> None:
    modules, tests, _ = _sweep()
    assert modules >= _MIN_MODULES, f"only {modules} test modules found (floor {_MIN_MODULES}): a subtree went missing"
    assert tests >= _MIN_TEST_FUNCTIONS, f"only {tests} tests (floor {_MIN_TEST_FUNCTIONS}): a subtree went missing"


def test_no_test_decides_a_call_assertion_with_a_fixed_sleep() -> None:
    _, _, offenders = _sweep()
    assert not offenders, (
        "These tests sleep a fixed interval and then assert that a call happened. A loaded runner "
        "fails them exactly as a regression would (#16224):\n  "
        + "\n  ".join(offenders)
        + "\nWait on the observable instead, e.g. `await eventually(task.done)` or "
        "`await eventually(lambda: mock.called)` from autobot_shared.eventually."
    )


_PLANTED = (
    "import asyncio\n\n"
    "async def test_flagged_count():\n    await asyncio.sleep(0.05)\n    assert worker.call_count == 2\n\n"
    "async def test_flagged_method():\n    await asyncio.sleep(0.2)\n    store.write.assert_called_once()\n\n"
    "async def test_spared_negative():\n    await asyncio.sleep(0.05)\n    store.write.assert_not_called()\n\n"
    "async def test_spared_nested_loop():\n    async def loop():\n        await asyncio.sleep(0.1)\n"
    "    await wait_until(lambda: check.await_count >= 2, loop=loop)\n\n"
    "async def test_spared_observable():\n    await eventually(lambda: store.write.called)\n"
    "    store.write.assert_called_once()\n\n"
    "async def test_spared_zero_yield():\n    await asyncio.sleep(0)\n    store.write.assert_called_once()\n\n"
    "async def test_spared_far_away():\n    await asyncio.sleep(0.05)\n"
    + "    pass\n" * _WINDOW_LINES
    + "    store.write.assert_called_once()\n"
)


def test_the_detector_flags_the_planted_shapes_and_spares_the_rest() -> None:
    tree = ast.parse(_PLANTED)
    lines = fixed_sleep_call_assertions(tree)
    flagged = {fn.name for fn in collectable_tests(tree) if any(fn.lineno <= ln <= fn.end_lineno for ln in lines)}
    assert flagged == {"test_flagged_count", "test_flagged_method"}, flagged
