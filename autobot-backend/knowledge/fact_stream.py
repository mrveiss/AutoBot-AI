# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Streaming read of ``fact:*`` hashes so pagination counts eligible facts, not raw keys (#20866).

``get_all_facts`` used to materialise the whole keyspace, slice it by ``offset``/``limit`` and only then
drop other-collection and quarantined facts, so a page could come back short while eligible facts existed
beyond the window. :func:`stream_facts` yields the facts that survive the filters, one batch of hashes at a
time, so the caller can stop scanning as soon as ``offset + limit`` eligible facts are in hand.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Dict, List

from autobot_shared.env_utils import env_int
from knowledge.quarantine import not_quarantined

FACT_KEY_PATTERN = "fact:*"
FACT_SCAN_BATCH_SIZE: int = env_int("AUTOBOT_FACT_SCAN_BATCH_SIZE", 200)

FactProcessor = Callable[[Any, Any, "str | None"], "Dict[str, Any] | None"]


async def _read_batch(redis: Any, keys: List[Any]) -> List[Any]:
    """Fetch the hashes of *keys* in one round trip."""
    pipeline = redis.pipeline()
    for key in keys:
        pipeline.hgetall(key)
    return await pipeline.execute()


def _eligible(keys: List[Any], rows: List[Any], process: FactProcessor, collection, keep_held: bool):
    """The facts of one batch that pass the collection filter and (unless *keep_held*) quarantine."""
    for key, row in zip(keys, rows):
        fact = process(key, row, collection)
        if fact and (keep_held or not_quarantined(fact)):
            yield fact


async def stream_facts(
    redis: Any,
    process: FactProcessor,
    collection: str | None,
    include_quarantined: bool,
    batch_size: int | None = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Yield eligible facts lazily; the Redis scan advances only as the consumer asks for more."""
    batch_size = batch_size or FACT_SCAN_BATCH_SIZE
    batch: List[Any] = []
    async for key in redis.scan_iter(match=FACT_KEY_PATTERN, count=batch_size):
        batch.append(key)
        if len(batch) >= batch_size:
            for fact in _eligible(batch, await _read_batch(redis, batch), process, collection, include_quarantined):
                yield fact
            batch = []
    if batch:
        for fact in _eligible(batch, await _read_batch(redis, batch), process, collection, include_quarantined):
            yield fact


async def collect_facts(stream: AsyncIterator[Dict[str, Any]], offset: int, limit: int | None) -> List[Dict[str, Any]]:
    """Skip *offset* and take *limit* facts from the eligible stream; stop reading once satisfied."""
    facts: List[Dict[str, Any]] = []
    skipped = 0
    async for fact in stream:
        if limit is not None and len(facts) >= limit:
            break
        if skipped < offset:
            skipped += 1
            continue
        facts.append(fact)
        if limit is not None and len(facts) >= limit:
            break
    return facts
