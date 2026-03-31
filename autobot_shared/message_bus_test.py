# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for ServiceMessageBus (#1379).

Uses mock Redis to verify publish, get_message, and
get_correlation_chain behavior without a live Redis connection.

The ``autobot_shared.redis_client`` module depends on backend internals
(``utils.redis_management``) that are unavailable in the shared-only test
environment.  We inject a stub *before* importing ``message_bus`` so the
real redis_client is never loaded.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

# ------------------------------------------------------------------ #
# Module-level stub for autobot_shared.redis_client                  #
# ------------------------------------------------------------------ #


def _install_redis_stub():
    """Install a fake ``autobot_shared.redis_client`` in sys.modules.

    This must run before ``autobot_shared.message_bus`` is imported
    so the ``from autobot_shared.redis_client import get_redis_client``
    inside message_bus.py resolves to our stub.
    """
    mod_name = "autobot_shared.redis_client"
    if mod_name in sys.modules:
        return  # Already loaded (real or stub)

    stub = types.ModuleType(mod_name)
    stub.get_redis_client = MagicMock(name="stub_get_redis_client")
    sys.modules[mod_name] = stub


_install_redis_stub()

# Now safe to import the module under test
from autobot_shared.message_bus import ServiceMessageBus  # noqa: E402
from autobot_shared.models.service_message import ServiceMessage  # noqa: E402

# ------------------------------------------------------------------ #
# Fixtures                                                           #
# ------------------------------------------------------------------ #


@pytest.fixture
def mock_redis():
    """Create a mock async Redis client with sensible defaults."""
    client = AsyncMock()
    client.hset = AsyncMock(return_value=1)
    client.xadd = AsyncMock(return_value=b"1234567890-0")
    client.sadd = AsyncMock(return_value=1)
    client.publish = AsyncMock(return_value=1)
    client.expire = AsyncMock(return_value=True)
    client.hget = AsyncMock(return_value=None)
    client.smembers = AsyncMock(return_value=set())
    return client


@pytest.fixture
def sample_message():
    """Create a sample ServiceMessage for testing."""
    return ServiceMessage(
        msg_id="test-msg-001",
        sender="main-backend",
        receiver="slm-backend",
        msg_type="task",
        content='{"action": "deploy"}',
        correlation_id="corr-001",
    )


@pytest_asyncio.fixture
async def bus_and_redis(mock_redis):
    """Create a ServiceMessageBus wired to the mock Redis client.

    Patches ``get_redis_client`` in the already-imported module so that
    ``_get_redis()`` returns *mock_redis*.
    """
    import autobot_shared.message_bus as mb_module

    async def _mock_get_redis(async_client=False, database="logs"):
        return mock_redis

    original = mb_module.get_redis_client
    mb_module.get_redis_client = _mock_get_redis
    try:
        bus = ServiceMessageBus()
        yield bus, mock_redis
    finally:
        mb_module.get_redis_client = original
        # Reset singleton so tests don't leak state
        mb_module._bus_instance = None


# ------------------------------------------------------------------ #
# Tests                                                              #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_publish_stores_message(bus_and_redis, sample_message):
    """Publish should call hset, xadd, sadd, and publish on Redis."""
    bus, mock_redis = bus_and_redis

    await bus.publish(sample_message)

    # Verify hash storage (full message data)
    mock_redis.hset.assert_called_once()
    hset_call = mock_redis.hset.call_args
    assert hset_call.args[0] == "autobot:service:msg:test-msg-001"

    # Verify stream append
    mock_redis.xadd.assert_called_once()
    xadd_call = mock_redis.xadd.call_args
    assert xadd_call.args[0] == "autobot:service:messages"

    # Verify correlation set
    mock_redis.sadd.assert_called_once()
    sadd_call = mock_redis.sadd.call_args
    assert "autobot:service:corr:corr-001" in str(sadd_call)
    assert "test-msg-001" in str(sadd_call)

    # Verify pub/sub publish
    mock_redis.publish.assert_called_once()
    pub_call = mock_redis.publish.call_args
    assert pub_call.args[0] == "autobot:service:live"


@pytest.mark.asyncio
async def test_publish_sets_ttl(bus_and_redis, sample_message):
    """Publish should set TTL on the message hash and correlation set."""
    bus, mock_redis = bus_and_redis

    await bus.publish(sample_message)

    # expire should be called twice: once for hash, once for correlation
    assert mock_redis.expire.call_count == 2

    expire_calls = mock_redis.expire.call_args_list
    keys_and_ttls = [(call.args[0], call.args[1]) for call in expire_calls]

    hash_key = "autobot:service:msg:test-msg-001"
    corr_key = "autobot:service:corr:corr-001"

    hash_ttl = next(ttl for key, ttl in keys_and_ttls if key == hash_key)
    corr_ttl = next(ttl for key, ttl in keys_and_ttls if key == corr_key)

    assert hash_ttl == 86400 * 14  # 14 days
    assert corr_ttl == 86400 * 7  # 7 days


@pytest.mark.asyncio
async def test_get_message(bus_and_redis, sample_message):
    """get_message should retrieve and deserialize from hash."""
    bus, mock_redis = bus_and_redis

    msg_json = sample_message.model_dump_json()
    mock_redis.hget.return_value = msg_json.encode("utf-8")

    result = await bus.get_message("test-msg-001")

    mock_redis.hget.assert_called_once_with("autobot:service:msg:test-msg-001", "data")
    assert result is not None
    assert result.msg_id == "test-msg-001"
    assert result.sender == "main-backend"
    assert result.receiver == "slm-backend"
    assert result.msg_type == "task"


@pytest.mark.asyncio
async def test_get_message_not_found(bus_and_redis):
    """get_message should return None when message doesn't exist."""
    bus, mock_redis = bus_and_redis

    mock_redis.hget.return_value = None

    result = await bus.get_message("nonexistent-id")

    assert result is None


@pytest.mark.asyncio
async def test_get_correlation_chain(bus_and_redis):
    """get_correlation_chain should return all chained messages sorted."""
    bus, mock_redis = bus_and_redis

    msg_a = ServiceMessage(
        msg_id="msg-a",
        ts="2026-03-04T10:00:00+00:00",
        sender="main-backend",
        receiver="slm-backend",
        msg_type="task",
        content='{"step": 1}',
        correlation_id="corr-chain",
    )
    msg_b = ServiceMessage(
        msg_id="msg-b",
        ts="2026-03-04T10:01:00+00:00",
        sender="slm-backend",
        receiver="main-backend",
        msg_type="result",
        content='{"step": 2}',
        correlation_id="corr-chain",
    )

    # Mock smembers to return the set of message IDs
    mock_redis.smembers.return_value = {b"msg-a", b"msg-b"}

    # Mock hget to return the correct message for each ID
    async def mock_hget(key, field):
        if key == "autobot:service:msg:msg-a":
            return msg_a.model_dump_json().encode("utf-8")
        elif key == "autobot:service:msg:msg-b":
            return msg_b.model_dump_json().encode("utf-8")
        return None

    mock_redis.hget.side_effect = mock_hget

    chain = await bus.get_correlation_chain("corr-chain")

    mock_redis.smembers.assert_called_once_with("autobot:service:corr:corr-chain")
    assert len(chain) == 2
    # Should be sorted by timestamp (ascending)
    assert chain[0].msg_id == "msg-a"
    assert chain[1].msg_id == "msg-b"


@pytest.mark.asyncio
async def test_get_latest_no_filter(bus_and_redis):
    """get_latest without filters should hydrate all stream entries."""
    bus, mock_redis = bus_and_redis

    msg_a = ServiceMessage(
        msg_id="latest-a",
        sender="main-backend",
        receiver="slm-backend",
        msg_type="task",
        content='{"n": 1}',
        correlation_id="corr-lat",
    )
    msg_b = ServiceMessage(
        msg_id="latest-b",
        sender="slm-backend",
        receiver="main-backend",
        msg_type="result",
        content='{"n": 2}',
        correlation_id="corr-lat",
    )

    # xrevrange returns list of (stream-id, field-dict) tuples
    mock_redis.xrevrange.return_value = [
        (
            b"1709500000000-0",
            {
                b"msg_id": b"latest-a",
                b"sender": b"main-backend",
                b"receiver": b"slm-backend",
                b"msg_type": b"task",
            },
        ),
        (
            b"1709500001000-0",
            {
                b"msg_id": b"latest-b",
                b"sender": b"slm-backend",
                b"receiver": b"main-backend",
                b"msg_type": b"result",
            },
        ),
    ]

    # hget returns full JSON for each msg_id
    async def mock_hget(key, field):
        if key == "autobot:service:msg:latest-a":
            return msg_a.model_dump_json().encode("utf-8")
        elif key == "autobot:service:msg:latest-b":
            return msg_b.model_dump_json().encode("utf-8")
        return None

    mock_redis.hget.side_effect = mock_hget

    results = await bus.get_latest(count=10)

    mock_redis.xrevrange.assert_called_once_with(
        "autobot:service:messages",
        count=10,
    )
    assert len(results) == 2
    assert results[0].msg_id == "latest-a"
    assert results[1].msg_id == "latest-b"


@pytest.mark.asyncio
async def test_get_latest_with_filter(bus_and_redis):
    """get_latest with sender filter should skip non-matching entries."""
    bus, mock_redis = bus_and_redis

    msg_match = ServiceMessage(
        msg_id="match-1",
        sender="main-backend",
        receiver="slm-backend",
        msg_type="task",
        content='{"ok": true}',
        correlation_id="corr-filt",
    )

    # Stream has two entries but only one matches the sender filter
    mock_redis.xrevrange.return_value = [
        (
            b"1709600000000-0",
            {
                b"msg_id": b"match-1",
                b"sender": b"main-backend",
                b"receiver": b"slm-backend",
                b"msg_type": b"task",
            },
        ),
        (
            b"1709600001000-0",
            {
                b"msg_id": b"skip-1",
                b"sender": b"browser-worker",
                b"receiver": b"main-backend",
                b"msg_type": b"event",
            },
        ),
    ]

    async def mock_hget(key, field):
        if key == "autobot:service:msg:match-1":
            return msg_match.model_dump_json().encode("utf-8")
        return None

    mock_redis.hget.side_effect = mock_hget

    results = await bus.get_latest(count=10, sender="main-backend")

    # With a filter, fetch_count should be count * 3
    mock_redis.xrevrange.assert_called_once_with(
        "autobot:service:messages",
        count=30,
    )
    assert len(results) == 1
    assert results[0].msg_id == "match-1"
    assert results[0].sender == "main-backend"
