# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for progress_tracker._invalidate_quality_cache (Issue #6669).

The Code Quality Dashboard caches calculated metrics under
``code_quality:latest*`` for 5 minutes. After a scan completes,
``_mark_task_completed`` must invalidate that cache so the dashboard
returns fresh results instead of stale pre-scan values.
"""

import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _load_progress_tracker():
    """Load progress_tracker.py without triggering the heavy analyzers import chain."""
    spec = importlib.util.spec_from_file_location(
        "progress_tracker_under_test",
        "autobot-backend/api/codebase_analytics/progress_tracker.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestInvalidateQualityCache:
    """Issue #6669: cache invalidation after scan completion."""

    @pytest.mark.asyncio
    async def test_deletes_matching_keys(self):
        """All keys matching code_quality:latest* must be passed to redis.delete()."""
        pt = _load_progress_tracker()

        fake_redis = MagicMock()
        fake_redis.keys = AsyncMock(
            return_value=[
                "code_quality:latest",
                "code_quality:latest:/repos/foo",
                "code_quality:latest:/repos/bar",
            ]
        )
        fake_redis.delete = AsyncMock(return_value=3)

        async def fake_get_client(database=None):
            assert database == "analytics"
            return fake_redis

        with patch.object(pt, "get_async_redis_client", new=fake_get_client):
            await pt._invalidate_quality_cache()

        fake_redis.keys.assert_awaited_once_with("code_quality:latest*")
        fake_redis.delete.assert_awaited_once_with(
            "code_quality:latest",
            "code_quality:latest:/repos/foo",
            "code_quality:latest:/repos/bar",
        )

    @pytest.mark.asyncio
    async def test_no_keys_no_delete(self):
        """When no keys match, redis.delete() must not be called."""
        pt = _load_progress_tracker()

        fake_redis = MagicMock()
        fake_redis.keys = AsyncMock(return_value=[])
        fake_redis.delete = AsyncMock()

        async def fake_get_client(database=None):
            return fake_redis

        with patch.object(pt, "get_async_redis_client", new=fake_get_client):
            await pt._invalidate_quality_cache()

        fake_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_unavailable_does_not_raise(self):
        """If the analytics redis client is unavailable, the helper must not raise."""
        pt = _load_progress_tracker()

        async def fake_get_client(database=None):
            return None

        with patch.object(pt, "get_async_redis_client", new=fake_get_client):
            # Must not raise — scan completion path can't fail because of cache cleanup.
            await pt._invalidate_quality_cache()

    @pytest.mark.asyncio
    async def test_redis_exception_swallowed(self):
        """Underlying Redis errors must be logged but not re-raised."""
        pt = _load_progress_tracker()

        fake_redis = MagicMock()
        fake_redis.keys = AsyncMock(side_effect=RuntimeError("redis is down"))

        async def fake_get_client(database=None):
            return fake_redis

        with patch.object(pt, "get_async_redis_client", new=fake_get_client):
            await pt._invalidate_quality_cache()  # No exception should propagate
