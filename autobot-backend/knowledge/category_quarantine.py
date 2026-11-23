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

* :func:`add_to_category` -- membership gained (the only ``SADD`` to a category set);
* :func:`remove_from_category` and ``CategoriesMixin._delete_category_records`` (one ``DEL`` over both
  keys) -- membership lost;
* ``FactsMixin.update_fact`` -- the one writer that changes an existing fact's ``collection`` marker
  (the promotion gate, a re-quarantine), through :func:`sync_fact_quarantine`;
* :func:`rebuild_category_quarantine_index` -- repairs every set from the facts' own metadata.

Atomicity. A membership change and its index entry go in one ``MULTI`` so a crash cannot split them.
The "is it quarantined" decision reads the fact's metadata, which a concurrent ``update_fact`` may
change between the read and the write. Rather than a Lua script (the repo's ``eval`` users guard plain
values; this decision is the Python quarantine predicate over a JSON field, and a Lua copy of it would
be a second definition), the decision is re-read after the write and corrected once. ``category_id`` is
written before the first read, and ``update_fact`` writes the metadata before it reads ``category_id``,
so either the re-read sees the new metadata or ``update_fact`` sees the category and syncs it itself.

Why a Redis marker and not the visibility backfill's durable row flag (``knowledge_facts``): category
membership and ``category_id`` live only in Redis, never in the durable row, so there is no row to flag.
The marker holds :data:`INDEX_VERSION`; bumping it, or a KB wipe (which deletes it), re-runs the rebuild.
The rebuild sets each fact's entry from its metadata (adds and removes index entries only, never facts
or category sets), so it also heals a wrong index.
"""

import asyncio
from typing import Any, Dict, Iterable

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from knowledge.category_keys import FACTS_KEY, QUARANTINED_KEY, REBUILT_MARKER
from knowledge.fact_redis_codec import _decode_redis_hash
from knowledge.quarantine import is_quarantined

logger = get_logger(__name__)

#: Bump when the index's meaning changes; the marker then differs and the rebuild runs again.
INDEX_VERSION = "1"
REBUILD_BATCH = env_int_clamped("AUTOBOT_KB_CATEGORY_INDEX_REBUILD_BATCH", 500, 1, 5000)


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _is_held(raw: Any) -> bool:
    """Whether a raw ``metadata`` hash field (JSON string or bytes, or ``None``) marks a quarantined fact."""
    parsed = _decode_redis_hash({"metadata": raw})["_parsed_metadata"] if raw else {}
    return is_quarantined({"metadata": parsed})


async def servable_fact_ids(redis: Any, category_ids: Iterable[str]) -> set:
    """Ids in the given category sets that are not quarantined: ``SDIFF`` per category, no hash reads."""
    ids: set = set()
    for cat_id in category_ids:
        members = await redis.sdiff(FACTS_KEY.format(cat_id), QUARANTINED_KEY.format(cat_id))
        ids.update(_text(m) for m in members)
    return ids


async def _write_membership(redis: Any, fact_id: str, category_id: str, held: bool) -> None:
    """Join the set and set the index entry for *held* in one ``MULTI``."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.sadd(FACTS_KEY.format(category_id), fact_id)
        (pipe.sadd if held else pipe.srem)(QUARANTINED_KEY.format(category_id), fact_id)
        await pipe.execute()


async def add_to_category(redis: Any, fact_id: str, category_id: str) -> None:
    """Add *fact_id* to the category set and index it by its own marker; re-read and correct once.

    The caller has already written ``category_id`` on the fact hash (see the module docstring).
    """
    held = _is_held(await redis.hget(f"fact:{fact_id}", "metadata"))
    await _write_membership(redis, fact_id, category_id, held)
    now_held = _is_held(await redis.hget(f"fact:{fact_id}", "metadata"))
    if now_held != held:
        write = redis.sadd if now_held else redis.srem
        await write(QUARANTINED_KEY.format(category_id), fact_id)


async def remove_from_category(redis: Any, fact_id: str, category_id: str) -> None:
    """Leave the set and the index together, in one ``MULTI``."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.srem(FACTS_KEY.format(category_id), fact_id)
        pipe.srem(QUARANTINED_KEY.format(category_id), fact_id)
        await pipe.execute()


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


async def _reconcile_batch(redis: Any, category_id: str, fact_ids: list) -> None:
    """Set the index entry of each fact from its metadata: one pipelined read, one pipelined write."""
    async with redis.pipeline(transaction=False) as pipe:
        for fact_id in fact_ids:
            pipe.hget(f"fact:{fact_id}", "metadata")
        raws = await pipe.execute()
    async with redis.pipeline(transaction=False) as pipe:
        for fact_id, raw in zip(fact_ids, raws):
            (pipe.sadd if _is_held(raw) else pipe.srem)(QUARANTINED_KEY.format(category_id), fact_id)
        await pipe.execute()


async def _reconcile_category(redis: Any, key: Any) -> int:
    """Reconcile one category set in batches of :data:`REBUILD_BATCH`; returns the facts visited."""
    category_id = _text(key).split(":", 2)[2]
    members = [_text(m) for m in await redis.smembers(_text(key))]
    for start in range(0, len(members), REBUILD_BATCH):
        await _reconcile_batch(redis, category_id, members[start : start + REBUILD_BATCH])
        done = min(start + REBUILD_BATCH, len(members))
        logger.info("Category %s quarantine index: %d/%d facts", category_id, done, len(members))
    return len(members)


async def rebuild_category_quarantine_index(redis: Any) -> int:
    """Reconcile every category set's index entries with the facts' metadata; returns the facts visited.

    Runs once per :data:`INDEX_VERSION` (and again after a wipe); idempotent, never deletes a fact or a set.
    """
    if _text(await redis.get(REBUILT_MARKER)) == INDEX_VERSION:
        return 0
    visited = 0
    async for key in redis.scan_iter(match=FACTS_KEY.format("*"), count=200):
        visited += await _reconcile_category(redis, key)
    await redis.set(REBUILT_MARKER, INDEX_VERSION)
    logger.info("Category quarantine index rebuilt over %d categorised facts", visited)
    return visited
