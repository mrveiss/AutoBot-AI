# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A quarantine-aware index over the category fact sets (#21957, part of #16665).

``category:facts:{category_id}`` holds fact ids only, so a count that must exclude research-quarantined
facts would need a hash read per id. ``category:quarantined:{category_id}`` holds the ids of the
quarantined members of that set; the servable ids are ``SDIFF(facts, quarantined)``, read with no
per-id hash read, so ``total_count``, ``has_more`` and the page boundaries are exact.

The index is a derived projection of (category membership x ``metadata.collection``). The only paths
that change either side of it:

* ``CategoriesMixin._assign_fact_to_category`` -- membership gained (the only ``SADD`` to a category set);
* ``CategoriesMixin._remove_from_old_category`` / ``_delete_category_records`` -- membership lost;
* ``FactsMixin.update_fact`` -- the one writer that changes an existing fact's ``collection`` marker
  (the promotion gate, a re-quarantine), through :func:`sync_fact_quarantine`;
* :func:`rebuild_category_quarantine_index` -- one-time rebuild of facts categorised before the index existed.
"""

import asyncio
from typing import Any, Dict, Iterable

from autobot_shared.logging_manager import get_logger
from knowledge.fact_redis_codec import _decode_redis_hash
from knowledge.quarantine import is_quarantined

logger = get_logger(__name__)

FACTS_KEY = "category:facts:{}"
QUARANTINED_KEY = "category:quarantined:{}"
#: Set once the rebuild has covered every category set; the startup hook skips the scan after that.
REBUILT_MARKER = "category_quarantine_index:rebuilt"


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _metadata_of(raw: Any) -> Dict[str, Any]:
    """The parsed ``metadata`` of a raw hash field (a JSON string or bytes)."""
    return _decode_redis_hash({"metadata": raw})["_parsed_metadata"] if raw else {}


async def servable_fact_ids(redis: Any, category_ids: Iterable[str]) -> set:
    """Ids in the given category sets that are not quarantined: ``SDIFF`` per category, no hash reads."""
    ids: set = set()
    for cat_id in category_ids:
        members = await redis.sdiff(FACTS_KEY.format(cat_id), QUARANTINED_KEY.format(cat_id))
        ids.update(_text(m) for m in members)
    return ids


async def index_assigned_fact(redis: Any, fact_id: str, category_id: str) -> None:
    """A fact joined *category_id*: record it as quarantined when its own marker says so."""
    raw = await redis.hget(f"fact:{fact_id}", "metadata")
    if is_quarantined({"metadata": _metadata_of(raw)}):
        await redis.sadd(QUARANTINED_KEY.format(category_id), fact_id)


async def unindex_fact(redis: Any, fact_id: str, category_id: str) -> None:
    """A fact left *category_id* (or the category went): drop it from the quarantine index."""
    await redis.srem(QUARANTINED_KEY.format(category_id), fact_id)


async def sync_fact_quarantine(redis_client: Any, fact_id: str, metadata: Dict[str, Any]) -> None:
    """``update_fact``'s step: bring the index in line with *metadata* for a fact that is categorised.

    Takes the sync client ``update_fact`` writes the hash with, so it runs on the same connection.
    """
    category_id = await asyncio.to_thread(redis_client.hget, f"fact:{fact_id}", "category_id")
    if not category_id:
        return
    key = QUARANTINED_KEY.format(_text(category_id))
    write = redis_client.sadd if is_quarantined({"metadata": metadata}) else redis_client.srem
    await asyncio.to_thread(write, key, fact_id)


async def rebuild_category_quarantine_index(redis: Any) -> int:
    """Index every already-categorised quarantined fact; idempotent, never deletes. Returns facts indexed."""
    if await redis.exists(REBUILT_MARKER):
        return 0
    indexed = 0
    async for key in redis.scan_iter(match=FACTS_KEY.format("*"), count=200):
        category_id = _text(key).split(":", 2)[2]
        for fact_id in await redis.smembers(_text(key)):
            await index_assigned_fact(redis, _text(fact_id), category_id)
            indexed += 1
    await redis.set(REBUILT_MARKER, "1")
    logger.info("Category quarantine index rebuilt over %d categorised facts", indexed)
    return indexed
