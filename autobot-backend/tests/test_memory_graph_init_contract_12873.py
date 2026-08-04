# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Memory graph init must report success truthfully (#12873).

`AutoBotMemoryGraph.initialize()` was declared `-> None` and returned nothing,
but `chat_history/base.py` does:

    initialized = await self.memory_graph.initialize()
    if initialized: ...

so a SUCCESSFUL init returned None — falsy — and conversation entity tracking
was disabled on every boot while the graph itself was fine. Nothing logged an
error because nothing had failed, which is why #12780's fix removed the visible
errors without recovering the feature.
"""

import ast
import inspect
import textwrap
from unittest.mock import AsyncMock, patch

import pytest

from autobot_memory_graph.core import AutoBotMemoryGraphCore as AutoBotMemoryGraph


def _graph():
    g = AutoBotMemoryGraph.__new__(AutoBotMemoryGraph)
    import asyncio

    g._lock = asyncio.Lock()
    g._initialized = False
    g.redis_client = None
    return g


@pytest.mark.asyncio
async def test_successful_init_returns_true():
    """The whole bug: this returned None, which the caller read as failure."""
    g = _graph()
    with patch("autobot_memory_graph.core.get_async_redis_client", new=AsyncMock(return_value=AsyncMock())):
        with patch.object(AutoBotMemoryGraph, "_create_search_indexes", new=AsyncMock()):
            result = await g.initialize()

    assert result is True, "a successful init must be truthy — the caller gates on it"
    assert g._initialized is True


@pytest.mark.asyncio
async def test_second_call_is_idempotent_and_still_truthy():
    """The early return also used to yield None, so a re-init reported failure."""
    g = _graph()
    with patch("autobot_memory_graph.core.get_async_redis_client", new=AsyncMock(return_value=AsyncMock())):
        with patch.object(AutoBotMemoryGraph, "_create_search_indexes", new=AsyncMock()):
            await g.initialize()
            again = await g.initialize()

    assert again is True


@pytest.mark.asyncio
async def test_failure_still_raises_rather_than_returning_false():
    """Callers wrap this in try/except; swallowing the cause would hide it."""
    g = _graph()
    with patch(
        "autobot_memory_graph.core.get_async_redis_client",
        new=AsyncMock(side_effect=RuntimeError("redis down")),
    ):
        with pytest.raises(RuntimeError, match="redis down"):
            await g.initialize()

    assert g._initialized is False


def test_signature_declares_a_bool_return():
    """A `-> None` annotation is what let the falsy return look intentional."""
    sig = inspect.signature(AutoBotMemoryGraph.initialize)

    assert sig.return_annotation is bool or sig.return_annotation == "bool", (
        f"return annotation is {sig.return_annotation!r}; a None-returning init "
        "silently disables entity tracking at the call site"
    )


def _return_statements(func) -> list[ast.Return]:
    """Every ``return`` in *func*, parsed rather than grepped.

    ``assert body.count("return True") == 2`` (#13311) counted literals in the
    source text: it matched a ``return True`` in a comment, missed
    ``return bool(...)``, and pinned the exact number of branches so any
    refactor broke it. The property that actually matters is that no exit path
    yields a falsy value.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Return)]


def test_no_exit_path_yields_a_falsy_value():
    """The #12873 defect: a successful init that the caller reads as failure."""
    returns = _return_statements(AutoBotMemoryGraph.initialize)

    assert returns, "initialize has no return statement at all — it falls through to None"
    for node in returns:
        assert node.value is not None, f"bare `return` at line {node.lineno} yields None — the original bug"
        assert not isinstance(node.value, ast.Constant) or bool(node.value.value), (
            f"`return {ast.unparse(node.value)}` at line {node.lineno} is falsy; "
            "a failed init must raise so the cause reaches the caller"
        )


def test_the_function_cannot_fall_off_its_end():
    """A trailing non-return statement re-creates the implicit ``return None``."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(AutoBotMemoryGraph.initialize)))
    func = tree.body[0]
    last = func.body[-1]

    assert isinstance(last, (ast.Return, ast.Raise, ast.With, ast.AsyncWith, ast.Try)), (
        f"initialize ends with {type(last).__name__}; execution can reach the end of "
        "the function and implicitly return None (#12873)"
    )
