# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Cheap whole-store reads over the ``fact:<id>`` hashes for the stats and category counts (#17530).

``/categories``, ``/detailed_stats`` and ``/man_pages/summary`` need each fact's metadata and the size of its content,
never the content. Reading them through ``get_all_facts`` pulled every fact's full text over the wire on every
request. :func:`fact_rows` reads ``HGET metadata`` and ``HSTRLEN content`` per fact (a pipelined round trip per batch)
and keeps the result for ``FACT_AGGREGATE_TTL_SECONDS``, so concurrent admin screens share one scan.

The per-category membership index (``category:facts:<category_id>``, ``knowledge/category_keys.py``) is not a source
for these counts: it holds the facts explicitly assigned to a category-tree node by id, while the endpoints count the
free-text ``metadata.category`` every fact carries, so the two disagree for any fact stored without a tree node.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from autobot_shared.env_utils import env_int
from knowledge.fact_redis_codec import _decode_redis_hash
from knowledge.fact_stream import FACT_KEY_PATTERN, FACT_SCAN_BATCH_SIZE, is_fact_key
from knowledge.quarantine import not_quarantined

FACT_AGGREGATE_TTL_SECONDS: int = env_int("AUTOBOT_FACT_AGGREGATE_TTL_SECONDS", 30)
_CACHE_ATTR = "_fact_rows_cache"


async def _read_rows(redis: Any, keys: List[Any]) -> List[Dict[str, Any]]:
    """``{metadata, size}`` per fact of one batch, quarantined facts dropped; size is ``HSTRLEN`` (bytes)."""
    pipeline = redis.pipeline()
    for key in keys:
        pipeline.hget(key, "metadata")
        pipeline.hstrlen(key, "content")
    results = await pipeline.execute()
    rows = []
    for raw, size in zip(results[0::2], results[1::2]):
        if raw is None and not size:
            continue  # the key vanished between SCAN and read
        metadata = _decode_redis_hash({"metadata": raw})["_parsed_metadata"] if raw is not None else {}
        if not_quarantined({"metadata": metadata}):
            rows.append({"metadata": metadata, "size": int(size or 0)})
    return rows


async def _scan_rows(kb: Any) -> List[Dict[str, Any]]:
    kb.ensure_initialized()
    redis = kb.redis()
    rows: List[Dict[str, Any]] = []
    batch: List[Any] = []
    async for key in redis.scan_iter(match=FACT_KEY_PATTERN, count=FACT_SCAN_BATCH_SIZE):
        if not is_fact_key(key):
            continue
        batch.append(key)
        if len(batch) >= FACT_SCAN_BATCH_SIZE:
            rows += await _read_rows(redis, batch)
            batch = []
    if batch:
        rows += await _read_rows(redis, batch)
    return rows


async def fact_rows(kb: Any) -> List[Dict[str, Any]]:
    """Every non-quarantined fact as ``{metadata, size}``, cached on *kb* for ``FACT_AGGREGATE_TTL_SECONDS``.

    Errors propagate: the callers decide how their endpoint degrades.
    """
    cached = getattr(kb, _CACHE_ATTR, None)
    if cached and FACT_AGGREGATE_TTL_SECONDS > 0 and time.monotonic() - cached[0] < FACT_AGGREGATE_TTL_SECONDS:
        return cached[1]
    rows = await _scan_rows(kb)
    setattr(kb, _CACHE_ATTR, (time.monotonic(), rows))
    return rows
