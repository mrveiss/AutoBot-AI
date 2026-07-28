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

import inspect
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


def test_every_exit_path_returns_true_or_raises():
    """No path may fall off the end and implicitly return None again."""
    src = inspect.getsource(AutoBotMemoryGraph.initialize)
    body = src.split('"""', 2)[-1]

    assert body.count("return True") == 2, "expected the early-return and success paths to return True"
    assert "return False" not in body, "failures raise; a False return would be silently unactionable"
