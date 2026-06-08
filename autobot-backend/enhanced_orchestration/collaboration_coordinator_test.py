# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for CollaborationCoordinator. Issue #6421."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_orchestration.collaboration_coordinator import CollaborationCoordinator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(msg_type: str, data: dict) -> dict:
    return {"type": msg_type, "data": json.dumps(data)}


def _make_redis(messages: list):
    """Build a minimal fake Redis client whose pubsub replays `messages`.

    redis.pubsub() is synchronous in redis-py, so pubsub must be a MagicMock
    returned from a MagicMock call (not an awaited AsyncMock).
    """
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()

    async def _listen():
        for msg in messages:
            yield msg

    pubsub.listen = _listen
    redis = AsyncMock()
    redis.pubsub = MagicMock(return_value=pubsub)
    redis.publish = AsyncMock()
    return redis, pubsub


# ---------------------------------------------------------------------------
# _ensure_redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_redis_calls_factory_once():
    redis = AsyncMock()
    factory = AsyncMock(return_value=redis)
    coord = CollaborationCoordinator(redis_factory=factory)

    await coord._ensure_redis()
    await coord._ensure_redis()  # second call must not invoke factory again

    factory.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_redis_raises_when_factory_returns_none():
    coord = CollaborationCoordinator(redis_factory=AsyncMock(return_value=None))
    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await coord._ensure_redis()


# ---------------------------------------------------------------------------
# coordinate_collaboration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinate_collaboration_broadcasts_share_insight():
    insight_msg = _make_message("message", {"type": "share_insight", "agent": "agent_a", "insight": "foo"})
    redis, pubsub = _make_redis([{"type": "subscribe"}, insight_msg])

    coord = CollaborationCoordinator(redis_factory=AsyncMock(return_value=redis))
    await coord.coordinate_collaboration("chan:test")

    pubsub.subscribe.assert_awaited_once_with("chan:test")
    redis.publish.assert_awaited_once()
    published_payload = json.loads(redis.publish.call_args[0][1])
    assert published_payload["type"] == "context_update"
    assert "agent_a_insight" in published_payload["shared_context"]


@pytest.mark.asyncio
async def test_coordinate_collaboration_skips_non_message_type():
    redis, pubsub = _make_redis([{"type": "subscribe"}, {"type": "psubscribe"}])
    coord = CollaborationCoordinator(redis_factory=AsyncMock(return_value=redis))
    await coord.coordinate_collaboration("chan:test")
    redis.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinate_collaboration_skips_bad_json():
    bad_msg = {"type": "message", "data": "not-json{{{"}
    redis, pubsub = _make_redis([bad_msg])
    coord = CollaborationCoordinator(redis_factory=AsyncMock(return_value=redis))
    await coord.coordinate_collaboration("chan:test")
    redis.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinate_collaboration_unsubscribes_on_cancellation():
    """pubsub must be unsubscribed even when the task is cancelled (#6419)."""

    async def _infinite_listen():
        await asyncio.sleep(9999)
        yield  # pragma: no cover

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.listen = _infinite_listen
    redis = AsyncMock()
    redis.pubsub = MagicMock(return_value=pubsub)

    coord = CollaborationCoordinator(redis_factory=AsyncMock(return_value=redis))
    task = asyncio.create_task(coord.coordinate_collaboration("chan:test"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    pubsub.unsubscribe.assert_awaited_once_with("chan:test")


@pytest.mark.asyncio
async def test_coordinate_collaboration_unsubscribes_on_redis_error():
    """pubsub must be unsubscribed when a non-CancelledError exception fires (#6419)."""

    async def _error_listen():
        raise ConnectionError("Redis dropped")
        yield  # make this an async generator

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.listen = _error_listen
    redis = AsyncMock()
    redis.pubsub = MagicMock(return_value=pubsub)

    coord = CollaborationCoordinator(redis_factory=AsyncMock(return_value=redis))
    with pytest.raises(ConnectionError):
        await coord.coordinate_collaboration("chan:test")

    pubsub.unsubscribe.assert_awaited_once_with("chan:test")


# ---------------------------------------------------------------------------
# broadcast_to_agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_to_agents_publishes_json():
    redis = AsyncMock()
    redis.pubsub.return_value = AsyncMock()
    coord = CollaborationCoordinator(redis_factory=AsyncMock(return_value=redis))
    await coord._ensure_redis()

    await coord.broadcast_to_agents("chan:x", {"key": "val"})
    redis.publish.assert_awaited_once_with("chan:x", json.dumps({"key": "val"}))
