# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for skill_promotion_publisher (#7431)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skills.skill_promotion_publisher import (
    CHANNEL_SKILL_PROMOTED,
    _publish_async,
    publish_skill_promoted,
)


def test_publish_skill_promoted_no_loop_returns_silently():
    """No running event loop → silent skip. Must NOT raise."""
    publish_skill_promoted("translation", ["translate"])


def test_publish_skill_promoted_empty_skill_name_noop():
    """Empty skill_name → no-op, no task scheduled."""
    publish_skill_promoted("")
    publish_skill_promoted(None)


@pytest.mark.asyncio
async def test_publish_skill_promoted_schedules_async_task():
    """Within an event loop, publish_skill_promoted schedules a background task."""
    with patch(
        "skills.skill_promotion_publisher._publish_async",
        new_callable=AsyncMock,
    ) as mock_publish:
        publish_skill_promoted("translation", ["translate"])
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        mock_publish.assert_awaited_once()
        payload = mock_publish.call_args[0][0]
        assert payload["event"] == "skill_promoted"
        assert payload["skill_name"] == "translation"
        assert payload["tools"] == ["translate"]
        assert payload["promoted_at"] > 0


@pytest.mark.asyncio
async def test_publish_async_uses_redis_publish():
    """_publish_async calls redis.publish with the JSON-serialized payload."""
    redis_client = MagicMock()
    redis_client.publish = AsyncMock()

    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=redis_client,
    ):
        await _publish_async({"event": "skill_promoted", "skill_name": "x"})

    redis_client.publish.assert_awaited_once()
    channel, message = redis_client.publish.call_args[0]
    assert channel == CHANNEL_SKILL_PROMOTED
    assert json.loads(message) == {"event": "skill_promoted", "skill_name": "x"}


@pytest.mark.asyncio
async def test_publish_async_silent_when_redis_disabled():
    """Redis returning None → silent skip, no exception."""
    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await _publish_async({"event": "skill_promoted", "skill_name": "x"})


@pytest.mark.asyncio
async def test_publish_async_swallows_redis_errors():
    """Redis publish raising → logged at debug, never propagates."""
    redis_client = MagicMock()
    redis_client.publish = AsyncMock(side_effect=ConnectionError("Redis down"))

    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=redis_client,
    ):
        await _publish_async({"event": "skill_promoted", "skill_name": "x"})


@pytest.mark.asyncio
async def test_publish_async_silent_when_redis_module_missing():
    """ImportError on autobot_shared.redis_client → silent skip."""
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "autobot_shared.redis_client":
            raise ImportError("simulated missing module")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_fake_import):
        await _publish_async({"event": "skill_promoted", "skill_name": "x"})
