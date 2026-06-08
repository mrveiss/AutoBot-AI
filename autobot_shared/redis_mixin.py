# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Mixin providing lazy async Redis client initialization.

Eliminates repeated boilerplate across ~43 async service classes:

    async def _get_redis(self):
        if self._redis is None:
            self._redis = await get_async_redis_client(database=...)
        return self._redis

Usage::

    from autobot_shared.redis_mixin import AsyncRedisClientMixin

    class MyService(AsyncRedisClientMixin):
        _redis_database = "analytics"  # override per class; default is "main"

    # The mixin provides _get_redis(); no inline method needed.
"""

import asyncio
from typing import Any

from autobot_shared.redis_client import get_async_redis_client


class AsyncRedisClientMixin:
    """Provides lazy-initialized async Redis client via ``_get_redis()``.

    Subclasses declare ``_redis_database`` as a class variable to select
    the target database.  The client is created on first call and cached
    for the lifetime of the instance.
    """

    _redis_database: str | Any = "main"
    _redis: Any | None = None

    async def _get_redis(self) -> Any | None:
        if self._redis is None:
            self._redis = await get_async_redis_client(database=self._redis_database)
        return self._redis


class AsyncRedisClientLockedMixin(AsyncRedisClientMixin):
    """Thread-safe variant with asyncio.Lock for concurrent initialization.

    Use when multiple concurrent callers could race to initialize the same
    Redis connection — avoids creating duplicate clients under load.
    """

    _redis_lock: asyncio.Lock | None = None

    async def _get_redis(self) -> Any | None:
        if self._redis is None:
            if self._redis_lock is None:
                self._redis_lock = asyncio.Lock()
            async with self._redis_lock:
                if self._redis is None:
                    self._redis = await get_async_redis_client(database=self._redis_database)
        return self._redis
