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
from knowledge.fact_key_families import NON_HASH_FACT_PREFIXES
from knowledge.quarantine import not_quarantined

FACT_KEY_PATTERN = "fact:*"
FACT_SCAN_BATCH_SIZE: int = env_int("AUTOBOT_FACT_SCAN_BATCH_SIZE", 200)

FactProcessor = Callable[[Any, Any, "str | None"], "Dict[str, Any] | None"]


def is_fact_key(key: Any) -> bool:
    """True for a real ``fact:<id>`` hash; the other ``fact:`` key families share the scan prefix and are not hashes.

    Fact ids legitimately contain ``:`` (``claude_memory:<owner>:<slug>``, connector ``<src>:<id>:file:<path>``,
    ``ext:...``, ``stream:...``), so a colon cannot be the discriminator. A key is a fact hash unless it starts
    with one of :data:`NON_HASH_FACT_PREFIXES` (``fact:collections:``, ``fact:origin:session:``,
    ``fact:versions:``, ``fact:version:meta:``), defined once in ``fact_key_families`` and imported by their
    writers. A prefix test is chosen over a pipelined ``TYPE`` check because it costs no round trip and no
    production id starts with one of those four namespaced prefixes. A WRONGTYPE ``hgetall`` on a non-hash
    family would fail the whole pipelined batch.
    """
    text = key.decode("utf-8") if isinstance(key, bytes) else key
    return text.startswith("fact:") and not text.startswith(NON_HASH_FACT_PREFIXES)


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
        if not is_fact_key(key):
            continue
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


async def get_facts_page(
    kb: Any, cursor: int = 0, count: int = 100, collection: str | None = None
) -> tuple[int, List[Dict[str, Any]]]:
    """One SCAN step over the ``fact:<id>`` hashes: ``(next_cursor, eligible facts)``; cursor 0 means done (#17530).

    Every fact the step touched is returned, so the cursor never advances past a fact the caller did not get.
    Quarantined facts are excluded, as in ``get_all_facts``. A fact is ``{fact_id, content, metadata, timestamp}``.
    """
    kb.ensure_initialized()
    redis = kb.redis()
    next_cursor, raw = await redis.scan(cursor=cursor, match=FACT_KEY_PATTERN, count=count)
    keys = [k for k in raw if is_fact_key(k)]
    rows = await _read_batch(redis, keys) if keys else []
    return int(next_cursor), list(_eligible(keys, rows, kb._process_fact_data, collection, False))
