# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one non-blocking pattern walk over a Redis keyspace (#18999).

``KEYS pattern`` blocks the server for the whole keyspace; ``scan_iter`` without COUNT
makes ~keys/10 round trips. Callers that need "every key matching a pattern" use
``scan_keys`` / ``count_keys`` here: same keys as ``KEYS``, bounded work per call
(COUNT from ``AUTOBOT_REDIS_SCAN_COUNT``, default 1000).
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

REDIS_SCAN_COUNT = env_int_clamped("AUTOBOT_REDIS_SCAN_COUNT", 1000, 10, 100000)


async def scan_keys(client: Any, pattern: str) -> List[Any]:
    """Return every key matching ``pattern`` using SCAN with a large COUNT.

    SCAN may return a key more than once, so the result is de-duplicated, first-seen order kept.
    """
    seen: Dict[Any, None] = {}
    async for key in client.scan_iter(match=pattern, count=REDIS_SCAN_COUNT):
        seen.setdefault(key, None)
    return list(seen)


async def count_keys(client: Any, pattern: str) -> int:
    """Count distinct keys matching ``pattern``.

    SCAN may repeat a key, so keys are tracked in a seen-set: memory is bounded by the matched
    keyspace (one entry per matching key), not by the whole database.
    """
    seen: set = set()
    async for key in client.scan_iter(match=pattern, count=REDIS_SCAN_COUNT):
        seen.add(key)
    return len(seen)


_log = get_logger(__name__)

#: pattern -> (last attempt ts, last good count or None, ts of that count), monotonic seconds.
CountStore = Dict[str, Tuple[float, Optional[int], Optional[float]]]


_locks: Dict[Tuple[int, str], asyncio.Lock] = {}


def _fresh(store: CountStore, pattern: str, refresh: float) -> bool:
    attempt_ts = store.get(pattern, (None, None, None))[0]
    return attempt_ts is not None and time.monotonic() - attempt_ts < refresh


async def cached_count(store: CountStore, client: Any, pattern: str, refresh: float) -> Optional[int]:
    """``count_keys`` at most once per ``refresh`` seconds, remembered in ``store``.

    A failed walk keeps serving the last good count (``None`` when there is none, so the caller
    omits the metric instead of zeroing it) and stamps the attempt, so the next try waits a full
    window rather than retrying every cycle while Redis struggles. A per-pattern lock makes
    concurrent callers on an expired entry share one walk (the cache is re-checked under the lock).
    """
    if _fresh(store, pattern, refresh):
        return store[pattern][1]
    async with _locks.setdefault((id(store), pattern), asyncio.Lock()):
        if _fresh(store, pattern, refresh):
            return store[pattern][1]
        _, count, count_ts = store.get(pattern, (None, None, None))
        now = time.monotonic()
        try:
            count, count_ts = await count_keys(client, pattern), now
        except Exception as exc:  # noqa: BLE001 - serve the stale count, retry next window
            _log.warning("key count walk for %r failed; serving stale value: %s", pattern, exc)
        store[pattern] = (now, count, count_ts)
        return count


def count_age_seconds(store: CountStore, pattern: str) -> float:
    """Seconds since the cached count for ``pattern`` was taken."""
    count_ts = store[pattern][2]
    return round(time.monotonic() - (count_ts if count_ts is not None else time.monotonic()), 1)
