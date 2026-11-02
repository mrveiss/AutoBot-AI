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
from datetime import datetime

from redis.exceptions import WatchError

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client

logger = get_logger(__name__)

_MAX_ATTEMPTS = 5


def _write_last_sync(redis, key: str, when: str) -> bool:
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
    return False


async def record_last_sync(key: str, when: datetime) -> bool:
    """Set ``last_sync_at`` on the stored connector. False if it's gone or kept changing."""
    redis = get_redis_client(database="knowledge")
    return await asyncio.to_thread(_write_last_sync, redis, key, when.isoformat())
