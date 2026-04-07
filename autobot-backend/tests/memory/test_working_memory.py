# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for WorkingMemoryService (issue #3768)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from memory.working_memory import WorkingMemoryService

SESSION = "sess-abc123"
KEY = "context"
VALUE = {"role": "user", "text": "hello"}


def _make_redis_mock(get_return=None):
    """Return an async-compatible Redis mock."""
    mock = AsyncMock()
    encoded = json.dumps(get_return).encode() if get_return is not None else None
    mock.get = AsyncMock(return_value=encoded)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)

    # scan_iter must be an async generator
    async def _scan_iter(match=None):
        yield f"autobot:session:{SESSION}:memory:{KEY}".encode()

    mock.scan_iter = _scan_iter
    return mock


@pytest.fixture
def service():
    return WorkingMemoryService()


@pytest.fixture
def redis_mock():
    return _make_redis_mock(get_return=VALUE)


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_sets_key_with_default_ttl(service, redis_mock):
    with patch(
        "memory.working_memory.get_redis_client", new=AsyncMock(return_value=redis_mock)
    ):
        await service.store(SESSION, KEY, VALUE)
        redis_mock.set.assert_awaited_once()
        call_args = redis_mock.set.call_args
        assert call_args.args[0] == f"autobot:session:{SESSION}:memory:{KEY}"
        assert json.loads(call_args.args[1]) == VALUE
        assert call_args.kwargs["ex"] == 3600


@pytest.mark.asyncio
async def test_store_uses_custom_ttl(service, redis_mock):
    with patch(
        "memory.working_memory.get_redis_client", new=AsyncMock(return_value=redis_mock)
    ):
        await service.store(SESSION, KEY, VALUE, ttl=120)
        assert redis_mock.set.call_args.kwargs["ex"] == 120


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_returns_deserialised_value(service, redis_mock):
    with patch(
        "memory.working_memory.get_redis_client", new=AsyncMock(return_value=redis_mock)
    ):
        result = await service.get(SESSION, KEY)
        assert result == VALUE


@pytest.mark.asyncio
async def test_get_returns_none_on_missing_key(service):
    missing_mock = _make_redis_mock(get_return=None)
    missing_mock.get = AsyncMock(return_value=None)
    with patch(
        "memory.working_memory.get_redis_client", new=AsyncMock(return_value=missing_mock)
    ):
        result = await service.get(SESSION, "nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_returns_key_suffixes(service):
    mock = _make_redis_mock()

    async def _scan_iter(match=None):
        yield f"autobot:session:{SESSION}:memory:{KEY}".encode()
        yield f"autobot:session:{SESSION}:memory:other".encode()

    mock.scan_iter = _scan_iter

    with patch(
        "memory.working_memory.get_redis_client", new=AsyncMock(return_value=mock)
    ):
        keys = await service.list(SESSION)
        assert sorted(keys) == sorted([KEY, "other"])


@pytest.mark.asyncio
async def test_list_returns_empty_when_no_keys(service):
    mock = _make_redis_mock()

    async def _empty_scan(match=None):
        return
        yield  # make it an async generator

    mock.scan_iter = _empty_scan

    with patch(
        "memory.working_memory.get_redis_client", new=AsyncMock(return_value=mock)
    ):
        keys = await service.list(SESSION)
        assert keys == []


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clear_deletes_all_session_keys(service):
    mock = _make_redis_mock()

    async def _scan_iter(match=None):
        yield f"autobot:session:{SESSION}:memory:{KEY}".encode()

    mock.scan_iter = _scan_iter
    mock.delete = AsyncMock(return_value=1)

    with patch(
        "memory.working_memory.get_redis_client", new=AsyncMock(return_value=mock)
    ):
        deleted = await service.clear(SESSION)
        assert deleted == 1
        mock.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_returns_zero_when_no_keys(service):
    mock = _make_redis_mock()

    async def _empty_scan(match=None):
        return
        yield

    mock.scan_iter = _empty_scan

    with patch(
        "memory.working_memory.get_redis_client", new=AsyncMock(return_value=mock)
    ):
        deleted = await service.clear(SESSION)
        assert deleted == 0
        mock.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# manager integration
# ---------------------------------------------------------------------------

def test_manager_exposes_working_memory_property():
    """UnifiedMemoryManager.working_memory returns a WorkingMemoryService singleton."""
    from memory.manager import UnifiedMemoryManager

    mgr = UnifiedMemoryManager(db_path="/tmp/test_wm_manager.db")
    svc = mgr.working_memory
    assert isinstance(svc, WorkingMemoryService)
    # Second access returns same instance
    assert mgr.working_memory is svc
