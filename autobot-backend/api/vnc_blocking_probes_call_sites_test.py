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

## Why this file classifies four forms rather than two

The first version of this pin asked one question -- "is the probe called without
being handed to `to_thread`?" -- and passed on two of the three ways to get it
wrong. Measured, not assumed:

    1 awaited to_thread(probe)     [correct]           passes   correct
    2 bare probe()                 [blocks]            FLAGGED  correct
    3 unawaited to_thread(probe)   [never runs]        passes    MISS
    4 await to_thread(probe())     [blocks on loop]    passes    MISS

Form 3 leaves a coroutine that is never awaited, so the probe does not run at
all. Form 4 calls the probe and hands its *result* to `to_thread`, so the
blocking work happens inline on the loop -- the shape
`check_no_blocking_io_in_async_test.py` has an explicit test for under
`Path.read_text()`.

Form 4 passed for a specific and instructive reason: the old matcher built an
exclusion set from every `to_thread` argument, so that a probe "handed off" would
not also count as called. For the *correct* form the argument is an `ast.Name`
and no `Call` node exists, so the exclusion never fired -- dead. For the
*defective* form the argument **is** a `Call`, so it landed in the exclusion and
was hidden. The exclusion's only live effect was to conceal the one shape where
the blocking work runs on the loop. Raised on #17647 by a reviewer checking the
pin against all four forms rather than against the code it was written for.
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


def _nodes_outside_nested_defs(fn: ast.AST):
    """Every node in *fn* except those inside a nested function definition.

    A sync helper defined inside an async function is not itself async context --
    it may have sync callers, and handing it to `to_thread` is the canonical fix
    shape. Mirrors the depth reset in `check_no_blocking_io_in_async.py`.
    """
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


# `to_thread(func, *args)` calls only its FIRST argument, so both matchers below
# check `args[0]` rather than any position: accepting any position let a probe
# passed as a later argument satisfy the pin while never being called (#17647).
def _to_thread_calls(fn: ast.AST) -> list:
    return [
        n
        for n in _nodes_outside_nested_defs(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "to_thread"
    ]


def _awaited(fn: ast.AST) -> set:
    """ids of Call nodes that are the operand of an `await`."""
    return {
        id(n.value)
        for n in _nodes_outside_nested_defs(fn)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
    }


def executed_on_the_loop(fn: ast.AST, name: str) -> list:
    """Calls to ``name()`` that run on the event loop (forms 2 and 4).

    No exclusion for `to_thread` arguments: the correct form passes the function
    *object*, which is an `ast.Name` and produces no `Call` node at all. So any
    `Call` to this name inside async context executes it there -- including
    `to_thread(probe())`, where the probe runs before `to_thread` is even entered.
    """
    return [
        n
        for n in _nodes_outside_nested_defs(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name
    ]


def offloaded_but_never_awaited(fn: ast.AST, name: str) -> list:
    """`to_thread(probe)` calls that no `await` consumes (form 3 -- probe never runs)."""
    awaited = _awaited(fn)
    return [
        call
        for call in _to_thread_calls(fn)
        if id(call) not in awaited and call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == name
    ]


def properly_offloaded(fn: ast.AST, name: str) -> list:
    """`await to_thread(probe)` -- the only correct form (form 1)."""
    awaited = _awaited(fn)
    return [
        call
        for call in _to_thread_calls(fn)
        if id(call) in awaited and call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == name
    ]


@pytest.mark.parametrize("probe", _BLOCKING_PROBES)
def test_no_async_function_executes_a_blocking_probe_on_the_loop(probe: str) -> None:
    """Forms 2 and 4: the probe runs on the event loop."""
    offenders = {
        fname: [c.lineno for c in executed_on_the_loop(fn, probe)]
        for fname, fn in _async_functions().items()
        if executed_on_the_loop(fn, probe)
    }
    assert not offenders, (
        f"{probe}() is executed on the event loop: {offenders}. Pass the function "
        f"object -- `await asyncio.to_thread({probe})` -- not its result."
    )


@pytest.mark.parametrize("probe", _BLOCKING_PROBES)
def test_no_offloaded_probe_is_left_unawaited(probe: str) -> None:
    """Form 3: `to_thread` without `await` returns a coroutine that never runs."""
    offenders = {
        fname: [c.lineno for c in offloaded_but_never_awaited(fn, probe)]
        for fname, fn in _async_functions().items()
        if offloaded_but_never_awaited(fn, probe)
    }
    assert not offenders, (
        f"{probe} is handed to an unawaited to_thread: {offenders}. The coroutine is "
        "never scheduled, so the probe does not run at all."
    )


@pytest.mark.parametrize("probe", _BLOCKING_PROBES)
def test_each_probe_is_actually_reached_from_async(probe: str) -> None:
    """The two sweeps above pass trivially if nothing calls the probes at all.

    `MEASUREMENT_DISCIPLINE.md`: an empty result must not read as a clean one. An
    earlier version of this test asked whether the probe's name appeared anywhere
    in the file, which the `import` line alone satisfies -- so it would have passed
    with every call deleted, while its name promised the calls were reached from
    async. A non-vacuity check written vacuously buys nothing and reads like
    coverage.
    """
    reached = {
        fname
        for fname, fn in _async_functions().items()
        if properly_offloaded(fn, probe) or executed_on_the_loop(fn, probe) or offloaded_but_never_awaited(fn, probe)
    }
    assert reached, (
        f"{probe}() is not reached from any `async def` in {_SOURCE.name} -- either it "
        "moved and the sweeps above are now vacuous, or it was renamed and this pin "
        "needs re-pointing"
    )


class TestTheMatchersThemselves:
    """Same reason as the agent pin: the matcher is the instrument.

    Its first-argument rule and its await rule were each added in response to a
    review finding, and neither was pinned -- so reverting either passed the suite.
    """

    @staticmethod
    def _fn(body: str):
        return ast.parse(f"async def h():\n    {body}\n").body[0]

    def test_a_probe_in_a_later_argument_is_not_counted_as_offloaded(self) -> None:
        # to_thread calls only its first argument; this never runs the probe.
        fn = self._fn("await asyncio.to_thread(lambda unused: None, is_vnc_running)")
        assert properly_offloaded(fn, "is_vnc_running") == []
        assert offloaded_but_never_awaited(fn, "is_vnc_running") == []

    def test_the_probe_as_first_argument_and_awaited_is_the_correct_form(self) -> None:
        fn = self._fn("await asyncio.to_thread(is_vnc_running)")
        assert len(properly_offloaded(fn, "is_vnc_running")) == 1
        assert executed_on_the_loop(fn, "is_vnc_running") == []

    def test_the_probe_as_first_argument_unawaited_is_flagged(self) -> None:
        fn = self._fn("asyncio.to_thread(is_vnc_running)")
        assert len(offloaded_but_never_awaited(fn, "is_vnc_running")) == 1
        assert properly_offloaded(fn, "is_vnc_running") == []
