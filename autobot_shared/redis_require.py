# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`require_redis_client`: a sync Redis client or a loud failure (#18553).

Lives beside ``redis_client`` (which re-exports it) so that module stays under its size ceiling.
"""

from typing import cast

import redis

from autobot_shared.redis_management.types import RedisDatabase


def require_redis_client(database: RedisDatabase | str = "main", decode_responses: bool | None = None) -> redis.Redis:
    """Return a sync client for *database*, or raise ``ConnectionError`` if there is none.

    For callers that cannot run without Redis (scripts, health checks): ``get_redis_client``
    returns ``None`` when Redis is disabled or the circuit is open, which would otherwise surface
    as an ``AttributeError`` at the first command. Sync only; there is deliberately no
    ``async_client`` parameter.
    """
    # Deferred: redis_client re-exports this function, so a top-level import would be circular.
    from autobot_shared import redis_client

    client = redis_client.get_redis_client(database=database, decode_responses=decode_responses)
    if client is None:
        raise ConnectionError(f"Redis '{database}' unavailable (disabled, unreachable or circuit open)")
    return cast(redis.Redis, client)  # async_client is never passed, so this is the sync client
