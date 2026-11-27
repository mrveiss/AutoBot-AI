# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Streaming read of ``fact:*`` hashes so pagination counts eligible facts, not raw keys (#20866).

``get_all_facts`` used to materialise the whole keyspace, slice it by ``offset``/``limit`` and only then
drop other-collection and quarantined facts, so a page could come back short while eligible facts existed
beyond the window. :func:`stream_facts` yields the facts that survive the filters, one batch of hashes at a
time, so the caller can stop scanning as soon as ``offset + limit`` eligible facts are in hand.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Callable, Dict, List

from autobot_shared.env_utils import env_int
from autobot_shared.fact_key_families import fact_keys_only, is_fact_key
from autobot_shared.logging_manager import get_logger
from knowledge.quarantine import not_quarantined

logger = get_logger(__name__)
FACT_KEY_PATTERN = "fact:*"
FACT_SCAN_BATCH_SIZE: int = env_int("AUTOBOT_FACT_SCAN_BATCH_SIZE", 200)

FactProcessor = Callable[[Any, Any, "str | None"], "Dict[str, Any] | None"]


_exemption_load_logged = False


def retention_exemption_rules() -> "tuple[str, str]":
    """``(memory category, connector source_type)`` the retention exemption keys on.

    The importer module is imported lazily (it pulls the PII pipeline). If that import fails the error is logged at
    WARNING once per process and RE-RAISED: silently treating "memory" as "not memory" would let retention delete
    Claude-memory facts the owner wants kept, so the retention task aborts its run on this error instead.
    """
    global _exemption_load_logged
    try:
        from knowledge.claude_memory_importer import CATEGORY
        from knowledge.connectors.base import CONNECTOR_SOURCE_TYPE
    except ImportError:
        if not _exemption_load_logged:
            _exemption_load_logged = True
            logger.warning("Retention exemption rules cannot be loaded; retention will not delete", exc_info=True)
        raise
    return CATEGORY, CONNECTOR_SOURCE_TYPE


def is_retention_exempt(raw_metadata: Any) -> bool:
    """True for a fact that age-based retention must keep (owner decision 2026-11-27, #17530).

    Claude-memory facts and connector-synced facts are exempt. Read from ``metadata``, not the id: ids come from
    several builders (``claude_code_memory:<owner>:<slug>``, ``<type>:<connector>:file:<id>``, ``ext:``/``stream:``
    and a connector's own source ids), but every connector write goes through ``_ingest_content``, which stamps
    ``source_type`` (``CONNECTOR_SOURCE_TYPE``), and the importer stamps ``category`` (``CATEGORY``). That covers
    ``ext:`` and ``stream:`` facts too, since the external adapter ingests through the same path. One predicate for
    the retention task and the admin count, so the count excludes exactly what retention keeps.

    Fail-safe direction: if the rules cannot be loaded (:func:`retention_exemption_rules`) this raises
    ``ImportError`` rather than answering "not exempt" -- an unloadable memory rule must never become a deletion.
    """
    CATEGORY, CONNECTOR_SOURCE_TYPE = retention_exemption_rules()

    if isinstance(raw_metadata, (bytes, str)):
        try:
            raw_metadata = json.loads(raw_metadata)
        except ValueError:
            return False
    meta = raw_metadata if isinstance(raw_metadata, dict) else {}
    return meta.get("source_type") == CONNECTOR_SOURCE_TYPE or meta.get("category") == CATEGORY


def scan_fact_keys(client: Any, cursor: Any, count: int) -> "tuple[Any, List[Any]]":
    """One sync ``SCAN`` step over ``fact:*``: ``(next_cursor, fact-hash keys only)``."""
    next_cursor, keys = client.scan(cursor, match=FACT_KEY_PATTERN, count=count)
    return next_cursor, fact_keys_only(keys)


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
    keys = fact_keys_only(raw)
    rows = await _read_batch(redis, keys) if keys else []
    return int(next_cursor), list(_eligible(keys, rows, kb._process_fact_data, collection, False))
