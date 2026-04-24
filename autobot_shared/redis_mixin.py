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
from typing import Any, Optional, Union

from autobot_shared.redis_client import get_async_redis_client


class AsyncRedisClientMixin:
    """Provides lazy-initialized async Redis client via ``_get_redis()``.

    Subclasses declare ``_redis_database`` as a class variable to select
    the target database.  The client is created on first call and cached
    for the lifetime of the instance.
    """

    _redis_database: Union[str, Any] = "main"
    _redis: Optional[Any] = None

    async def _get_redis(self) -> Optional[Any]:
        if self._redis is None:
            self._redis = await get_async_redis_client(database=self._redis_database)
        return self._redis
