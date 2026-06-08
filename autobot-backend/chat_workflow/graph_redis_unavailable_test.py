# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for graph.py resilience when AsyncRedisSaver is unavailable (Bug #5623).

Simulates the production failure: redisvl's broken dependency on
redis.commands.search.indexDefinition causes the AsyncRedisSaver import to fail.
graph.py must still load and expose _REDIS_CHECKPOINTER_AVAILABLE=False.
"""

import importlib.util
import sys
import types
import typing
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub all dependencies, but intentionally omit AsyncRedisSaver to simulate
# the broken redisvl → redis.commands.search.indexDefinition import chain.
# ---------------------------------------------------------------------------

_STUBS: dict = {
    "langchain_core": types.ModuleType("langchain_core"),
    "langchain_core.messages": types.ModuleType("langchain_core.messages"),
    "langchain_core.runnables": types.ModuleType("langchain_core.runnables"),
    "xxhash": types.ModuleType("xxhash"),
    "redis": types.ModuleType("redis"),
    "redis.asyncio": types.ModuleType("redis.asyncio"),
    "langgraph": types.ModuleType("langgraph"),
    "langgraph.checkpoint": types.ModuleType("langgraph.checkpoint"),
    "langgraph.checkpoint.redis": types.ModuleType("langgraph.checkpoint.redis"),
    # Empty stub — no AsyncRedisSaver attribute → simulates broken redisvl chain
    "langgraph.checkpoint.redis.aio": types.ModuleType("langgraph.checkpoint.redis.aio"),
    "langgraph.graph": types.ModuleType("langgraph.graph"),
    "langgraph.types": types.ModuleType("langgraph.types"),
    "typing_extensions": types.ModuleType("typing_extensions"),
}

for _name, _stub in _STUBS.items():
    sys.modules.setdefault(_name, _stub)

for _attr in ("END", "START", "StateGraph"):
    if not hasattr(sys.modules["langgraph.graph"], _attr):
        setattr(sys.modules["langgraph.graph"], _attr, MagicMock())

if not hasattr(sys.modules["langgraph.types"], "interrupt"):
    sys.modules["langgraph.types"].interrupt = MagicMock()

if not hasattr(sys.modules["typing_extensions"], "TypedDict"):
    sys.modules["typing_extensions"].TypedDict = typing.TypedDict

for _attr in ("HumanMessage", "SystemMessage", "AIMessage", "BaseMessage"):
    if not hasattr(sys.modules["langchain_core.messages"], _attr):
        setattr(sys.modules["langchain_core.messages"], _attr, MagicMock())

if not hasattr(sys.modules["langchain_core.runnables"], "RunnableConfig"):
    sys.modules["langchain_core.runnables"].RunnableConfig = MagicMock()

# NOTE: AsyncRedisSaver is deliberately NOT set on langgraph.checkpoint.redis.aio

# ---------------------------------------------------------------------------
# Load graph.py in isolation so the test is independent of the real environment.
# ---------------------------------------------------------------------------

_GRAPH_PATH = Path(__file__).parent / "graph.py"
_SENTINEL = object()


def _load_graph_isolated():
    """Load graph.py as an isolated module with AsyncRedisSaver absent from the stub.

    Uses a unique module name each call so the loader doesn't cache the result.
    Temporarily removes AsyncRedisSaver from the shared stub so that the
    try/except in graph.py sets _REDIS_CHECKPOINTER_AVAILABLE = False, regardless
    of what other test files may have injected into sys.modules first.
    """
    aio_mod = sys.modules["langgraph.checkpoint.redis.aio"]
    orig = getattr(aio_mod, "AsyncRedisSaver", _SENTINEL)
    if orig is not _SENTINEL:
        delattr(aio_mod, "AsyncRedisSaver")
    try:
        spec = importlib.util.spec_from_file_location(f"_graph_redis_unavail_{id(object())}", _GRAPH_PATH)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    finally:
        if orig is not _SENTINEL:
            aio_mod.AsyncRedisSaver = orig


def test_graph_loads_when_async_redis_saver_unavailable():
    """graph.py must import successfully even when AsyncRedisSaver is missing."""
    mod = _load_graph_isolated()
    assert mod is not None


def test_redis_checkpointer_available_flag_is_false_when_import_fails():
    """_REDIS_CHECKPOINTER_AVAILABLE must be False when AsyncRedisSaver is unavailable."""
    mod = _load_graph_isolated()
    assert hasattr(mod, "_REDIS_CHECKPOINTER_AVAILABLE"), "graph.py must expose _REDIS_CHECKPOINTER_AVAILABLE"
    assert mod._REDIS_CHECKPOINTER_AVAILABLE is False


def test_get_redis_checkpointer_raises_when_unavailable():
    """get_redis_checkpointer() must raise RuntimeError when AsyncRedisSaver is unavailable."""
    mod = _load_graph_isolated()
    with pytest.raises(RuntimeError, match="AsyncRedisSaver"):
        import asyncio

        asyncio.get_event_loop().run_until_complete(mod.get_redis_checkpointer())
