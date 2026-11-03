# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A finished sync records its time on the connector's current record, and nothing else.

The sync holds a config loaded before it began, with its decrypted credentials merged in. Saving
that back would store the credentials in Redis, undo an edit made during the sync, and bring back
a connector deleted during it. So only this field is written, in one transaction on the key.
"""

import asyncio
import json

from redis.exceptions import WatchError

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

_MAX_ATTEMPTS = 5


def _write_last_sync(redis, key: str, when: str) -> bool | None:
    """True when written, False when the connector is gone, None when it exists but kept changing."""
    with redis.pipeline() as pipe:
        for _ in range(_MAX_ATTEMPTS):
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                if raw is None:
                    pipe.unwatch()
                    return False
                record = json.loads(raw)
                record["last_sync_at"] = when
                pipe.multi()
                pipe.set(key, json.dumps(record, ensure_ascii=False))
                pipe.execute()
                return True
            except WatchError:
                continue
    logger.warning("Could not record the last sync on %s: it kept changing", key)
    return None


async def record_last_sync(instance, key: str, sync_result) -> bool:
    """Set ``last_sync_at`` on the stored connector and the live instance. False if it was deleted."""
    when = sync_result.completed_at or now_utc()
    redis = get_redis_client(database="knowledge")
    stored = await asyncio.to_thread(_write_last_sync, redis, key, when.isoformat())
    if stored is True:
        instance.config.last_sync_at = when  # what the status route reads; only once Redis has it
    return stored is not False
