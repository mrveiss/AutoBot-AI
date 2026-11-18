# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A finished sync records its time on the connector's current record, and nothing else.

The sync holds a config loaded before it began, with its decrypted credentials merged in. Saving
that back would store the credentials in Redis, undo an edit made during the sync, and bring back
a connector deleted during it. So only this field is written, in one transaction on the key.

It only moves forward (#20758): two runs can still overlap once a lease is lost, and the one that
finishes first must not set an older time over a newer one, which would widen the next ``since``.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Literal

from redis.exceptions import WatchError

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc, parse_utc_iso

logger = get_logger(__name__)

_MAX_ATTEMPTS = 5


def _aware(value) -> datetime | None:
    """A comparable UTC time from a datetime or an ISO string; None when absent or unreadable."""
    if isinstance(value, str):
        try:
            return parse_utc_iso(value)
        except ValueError:
            logger.warning("Ignoring an unreadable stored last_sync_at %r", value)
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def _is_later(when: datetime, current) -> bool:
    current = _aware(current)
    return current is None or when > current


def _write_last_sync(redis, key: str, when: datetime) -> datetime | Literal[False] | None:
    """The time Redis holds afterwards: *when*, or a later (or equal) one already stored. False when
    the connector is gone, None when it exists but kept changing."""
    with redis.pipeline() as pipe:
        for _ in range(_MAX_ATTEMPTS):
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                if raw is None:
                    pipe.unwatch()
                    return False
                record = json.loads(raw)
                current = _aware(record.get("last_sync_at"))
                if current is not None and current >= when:
                    pipe.unwatch()
                    return current
                record["last_sync_at"] = when.isoformat()
                pipe.multi()
                pipe.set(key, json.dumps(record, ensure_ascii=False))
                pipe.execute()
                return when
            except WatchError:
                continue
    logger.warning("Could not record the last sync on %s: it kept changing", key)
    return None


async def record_last_sync(instance, key: str, sync_result) -> bool:
    """Set ``last_sync_at`` after a successful sync, on the stored connector and the live instance.

    False if the connector was deleted. ``last_sync_at`` is the next incremental sync's ``since``, so
    only a run that reached every source may move it. A run that failed, finished partial or was
    stopped (#20556: it lost its lease) leaves it where it was, together with its checkpoint, or
    the next incremental sync would skip the sources this run never reached.
    """
    redis = get_redis_client(database="knowledge")
    if getattr(sync_result, "status", None) != "success":
        return bool(await asyncio.to_thread(redis.exists, key))
    when = _aware(sync_result.completed_at) or now_utc()
    stored = await asyncio.to_thread(_write_last_sync, redis, key, when)
    if isinstance(stored, datetime) and _is_later(stored, instance.config.last_sync_at):
        instance.config.last_sync_at = stored  # what the status route reads: what Redis holds
    return stored is not False
