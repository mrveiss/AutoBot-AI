# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for WorkflowMemory."""

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.workflow_memory import WorkflowMemory


class TestWorkflowMemory:
    def setup_method(self) -> None:
        self.memory = WorkflowMemory("wf-123")

    def test_key_format(self) -> None:
        assert self.memory._key == "autobot:workflow:wf-123:memory"

    @pytest.mark.asyncio
    @patch("autobot_shared.workflow_memory.get_redis_client")
    async def test_write(self, mock_get_redis) -> None:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await self.memory.write("step1:result", '{"status": "done"}')

        mock_redis.hset.assert_called_once_with("autobot:workflow:wf-123:memory", "step1:result", '{"status": "done"}')
        mock_redis.expire.assert_called_once_with("autobot:workflow:wf-123:memory", 3600)

    @pytest.mark.asyncio
    @patch("autobot_shared.workflow_memory.get_redis_client")
    async def test_read(self, mock_get_redis) -> None:
        mock_redis = AsyncMock()
        mock_redis.hget.return_value = '{"status": "done"}'
        mock_get_redis.return_value = mock_redis

        result = await self.memory.read("step1:result")

        assert result == '{"status": "done"}'
        mock_redis.hget.assert_called_once_with("autobot:workflow:wf-123:memory", "step1:result")

    @pytest.mark.asyncio
    @patch("autobot_shared.workflow_memory.get_redis_client")
    async def test_read_all(self, mock_get_redis) -> None:
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {"k1": "v1", "k2": "v2"}
        mock_get_redis.return_value = mock_redis

        result = await self.memory.read_all()

        assert result == {"k1": "v1", "k2": "v2"}

    @pytest.mark.asyncio
    @patch("autobot_shared.workflow_memory.get_redis_client")
    async def test_clear(self, mock_get_redis) -> None:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await self.memory.clear()

        mock_redis.delete.assert_called_once_with("autobot:workflow:wf-123:memory")
