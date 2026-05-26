# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for PipelineDispatcher."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Load the real modules from file, bypassing sys.modules stubs that the
# root conftest installs for services.npu_pipeline.*.
_PKG_DIR = Path(__file__).parent


def _load_module(name: str, filename: str):
    if name in sys.modules and hasattr(sys.modules[name], "__file__"):
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(_PKG_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "services.npu_pipeline"
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_shard_planner = _load_module("services.npu_pipeline.shard_planner", "shard_planner.py")
_dispatcher_mod = _load_module("services.npu_pipeline.dispatcher", "dispatcher.py")

LayerRange = _shard_planner.LayerRange
ShardAssignment = _shard_planner.ShardAssignment
PipelineDispatcher = _dispatcher_mod.PipelineDispatcher
PipelinePlan = _dispatcher_mod.PipelinePlan
WorkerDropError = _dispatcher_mod.WorkerDropError


WORKER_URLS = {
    "w0": "http://worker0:8080",
    "w1": "http://worker1:8080",
    "w2": "http://worker2:8080",
}

PROMPT_TOKENS = [1, 2, 3, 4]


def _make_plan(*worker_ids: str, peer_map=None) -> PipelinePlan:
    assignments = [
        ShardAssignment(
            worker_id=wid,
            layer_range=LayerRange(i * 10, i * 10 + 9),
        )
        for i, wid in enumerate(worker_ids)
    ]
    return PipelinePlan(assignments=assignments, peer_map=peer_map or {})


async def _collect(gen) -> List[str]:
    return [t async for t in gen]


# ---------------------------------------------------------------------------
# Happy path: 3 workers, full pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_three_workers():
    plan = _make_plan("w0", "w1", "w2")

    call_log: List[str] = []

    async def mock_post(url, json=None):
        resp = AsyncMock()
        resp.raise_for_status = MagicMock()
        if "/forward" in url:
            call_log.append(f"forward:{url}")
            resp.json = AsyncMock(return_value={"hidden_state": {"data": [0.1]}})
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
        else:  # /generate
            call_log.append(f"generate:{url}")

            async def _content():
                for tok in [b"hello\n", b"world\n"]:
                    yield tok

            resp.content = _content()
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    session_mock = MagicMock()
    session_mock.post = mock_post
    session_mock.close = AsyncMock()

    async with PipelineDispatcher(WORKER_URLS) as d:
        d._session = session_mock
        tokens = await _collect(d.run_pipeline(plan, PROMPT_TOKENS))

    assert tokens == ["hello", "world"]
    assert sum(1 for c in call_log if c.startswith("forward")) == 2
    assert sum(1 for c in call_log if c.startswith("generate")) == 1


# ---------------------------------------------------------------------------
# Worker drop mid-pass: failover to peer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_drop_mid_pass_failover():
    """w1 is last worker; it drops and peer w2 takes over its layer range."""
    peer_map = {"w1": ["w2"]}
    plan = _make_plan("w0", "w1", peer_map=peer_map)

    call_counts: dict = {"w0_fwd": 0, "w1_gen": 0, "w2_gen": 0}

    import aiohttp as _aiohttp

    async def mock_post(url, json=None):
        resp = AsyncMock()
        resp.raise_for_status = MagicMock()

        if "worker0" in url and "/forward" in url:
            call_counts["w0_fwd"] += 1
            resp.json = AsyncMock(return_value={"hidden_state": {"data": [0.5]}})
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
        elif "worker1" in url:
            call_counts["w1_gen"] += 1
            raise _aiohttp.ClientConnectionError("worker1 down")
        elif "worker2" in url:
            call_counts["w2_gen"] += 1

            async def _content():
                yield b"ok\n"

            resp.content = _content()
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    session_mock = MagicMock()
    session_mock.post = mock_post
    session_mock.close = AsyncMock()

    async with PipelineDispatcher(WORKER_URLS) as d:
        d._session = session_mock
        tokens = await _collect(d.run_pipeline(plan, PROMPT_TOKENS))

    assert tokens == ["ok"]
    assert call_counts["w0_fwd"] == 1
    assert call_counts["w1_gen"] == 1
    assert call_counts["w2_gen"] == 1


# ---------------------------------------------------------------------------
# Worker drop mid-pass: no peer → clear WorkerDropError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_drop_no_peer_raises():
    """w0 drops in forward pass and has no peers — expect WorkerDropError."""
    plan = _make_plan("w0", "w1")

    import aiohttp as _aiohttp

    async def mock_post(url, json=None):
        raise _aiohttp.ClientConnectionError("worker0 down")

    session_mock = MagicMock()
    session_mock.post = mock_post
    session_mock.close = AsyncMock()

    with pytest.raises(WorkerDropError, match="w0"):
        async with PipelineDispatcher(WORKER_URLS) as d:
            d._session = session_mock
            await _collect(d.run_pipeline(plan, PROMPT_TOKENS))


# ---------------------------------------------------------------------------
# Last worker produces tokens (single-worker plan)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_worker_produces_tokens():
    """Single-worker plan: worker is both first and last, produces tokens."""
    plan = _make_plan("w0")

    async def mock_post(url, json=None):
        assert "/generate" in url, f"Expected /generate, got {url}"
        resp = AsyncMock()
        resp.raise_for_status = MagicMock()

        async def _content():
            for tok in [b"a\n", b"b\n", b"c\n"]:
                yield tok

        resp.content = _content()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    session_mock = MagicMock()
    session_mock.post = mock_post
    session_mock.close = AsyncMock()

    async with PipelineDispatcher(WORKER_URLS) as d:
        d._session = session_mock
        tokens = await _collect(d.run_pipeline(plan, PROMPT_TOKENS))

    assert tokens == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Context manager teardown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_manager_closes_session():
    close_called = False

    async def fake_close():
        nonlocal close_called
        close_called = True

    with patch("aiohttp.ClientSession") as MockSession:
        instance = MagicMock()
        instance.close = AsyncMock(side_effect=fake_close)
        MockSession.return_value = instance

        async with PipelineDispatcher(WORKER_URLS):
            pass

    assert close_called
