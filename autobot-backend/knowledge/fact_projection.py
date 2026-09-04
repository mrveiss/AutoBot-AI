# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The half of a fact's lifecycle that treats Redis as a projection (#15663).

``FactsMixin`` writes facts; the methods here are the ones that only make sense
once the ``knowledge_facts`` row — not the ``fact:<id>`` hash — is the fact.
Each of them exists because a Redis key can be absent without the knowledge
being gone, which is precisely the state #12733 left the knowledge base in and
could not distinguish from an empty one:

* :meth:`FactProjectionMixin._read_fact_for_write` settles existence from the
  row when the hash is missing, instead of reporting "fact not found";
* the two lookups fall back to the row, so a stale dedup index cannot turn one
  fact into two;
* :meth:`FactProjectionMixin.rebuild_fact_projections` is the reconstruction
  ``autobot_shared/store_authority.py`` promises for this concept, which is what
  makes the Redis copy disposable rather than a second original.

``knowledge.fact_store`` is imported inside each method, never at module
scope: it pulls SQLAlchemy, which the startup-import smoke environment does
not install, so a module-level import would break every importer of this
file rather than only the paths that actually touch the durable store.

Split out of ``facts.py`` rather than added to it: that module is a
grandfathered large file whose exemption freezes the size it was granted for
(#14236). The seam is real regardless — everything here is about the
relationship between the stores, not about what a fact is.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Width of the deduplication fingerprint carried by ``content_hash:<hash>``.
_CONTENT_HASH_WIDTH = 16


class FactProjectionMixin:
    """Reads and rebuilds that treat the Redis fact keys as a derived copy."""

    async def _read_fact_for_write(self, fact_id: str) -> tuple[Dict[str, Any], Dict[str, Any]] | None:
        """The fact as it stands, for an update or a delete. ``None`` if unknown.

        Reads the Redis projection first because it is warm, and falls back to
        the durable row — which is the case #12733 could not survive: the hashes
        were gone, so every fact "did not exist" even though the knowledge was
        still recoverable. The row settles existence; Redis only makes it fast.
        """
        # Lazy: see the module docstring on why fact_store is not imported at module scope.
        from knowledge import fact_store

        fact_data = await asyncio.to_thread(self.redis_client.hgetall, "fact:%s" % fact_id)
        if fact_data:
            decoded = self._decode_fact_data(fact_data)
            raw = decoded.get("metadata")
            try:
                metadata = raw if isinstance(raw, dict) else json.loads(raw or "{}")
            except (json.JSONDecodeError, TypeError):
                metadata = {}
            return decoded, metadata

        row = await fact_store.load_fact(fact_id)
        if row is None:
            return None
        logger.info("Fact %s served from the durable row; its Redis projection is missing", fact_id)
        return {"content": row["content"], "timestamp": ""}, row["metadata"]

    async def _find_fact_by_unique_key(self, unique_key: str) -> Dict[str, Any] | None:
        """Find an existing fact by unique key (fast Redis SET lookup).

        Issue #315: Refactored to use helper for reduced nesting.

        Args:
            unique_key: The unique key to search for (e.g., "machine:os:command:section")

        Returns:
            Dict with fact info if found, None otherwise
        """
        # Lazy: see the module docstring on why fact_store is not imported at module scope.
        from knowledge import fact_store

        try:
            unique_key_name = "unique_key:man_page:%s" % unique_key
            fact_id = await asyncio.to_thread(self.redis_client.get, unique_key_name)

            if isinstance(fact_id, bytes):
                fact_id = fact_id.decode("utf-8")
            if not fact_id:
                # #15663: the index is a projection. A missing entry means the
                # projection is stale, not that the fact was never ingested --
                # and re-ingesting on that assumption is how duplicates appear.
                fact_id = await fact_store.fact_id_for_unique_key(unique_key)
            if not fact_id:
                return None

            current = await self._read_fact_for_write(fact_id)
            if current is None:
                return None
            decoded_data, fact_metadata = current
            return {
                "fact_id": fact_id,
                "content": decoded_data.get("content", ""),
                "metadata": fact_metadata,
            }
        except Exception as e:
            logger.debug("Error finding fact by unique key: %s", e)
        return None

    async def _find_existing_fact(self, content: str, metadata: Dict[str, Any]) -> str | None:
        """Check if a fact with identical content already exists.

        Args:
            content: Fact content
            metadata: Fact metadata (unused; kept for call-site compatibility)

        Returns:
            Existing fact_id if found, None otherwise
        """
        # Lazy: see the module docstring on why fact_store is not imported at module scope.
        from knowledge import fact_store

        try:
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:_CONTENT_HASH_WIDTH]
            existing_id = await asyncio.to_thread(self.redis_client.get, "content_hash:%s" % content_hash)

            if isinstance(existing_id, bytes):
                existing_id = existing_id.decode("utf-8")
            if existing_id:
                return existing_id

            # #15663: fall back to the durable row. The dedup index is a
            # projection, so its absence says nothing about whether the fact
            # exists -- and answering "no" would store the content twice.
            return await fact_store.fact_id_for_content_hash(content_hash)
        except Exception as e:
            logger.debug("Error checking for existing fact: %s", e)
        return None

    async def _record_vector_observation(self, fact_id: str) -> None:
        """Note on the durable row that ChromaDB was seen holding this vector.

        Issue #15663: an observation with a timestamp, never consulted to decide
        whether a vector exists. It answers "when did the two stores last agree",
        which is a question a flag pretending to be authority cannot answer.
        Best-effort — a missed stamp costs a reporting detail, not a vector.
        """
        # Lazy: see the module docstring on why fact_store is not imported at module scope.
        from knowledge import fact_store

        try:
            await fact_store.record_vector_seen(fact_id)
        except Exception as exc:  # noqa: BLE001 - reporting detail, never the write path
            logger.debug("Could not stamp vector_seen_at for fact %s: %s", fact_id, exc)

    async def rebuild_fact_projections(self, batch_size: int = 500) -> Dict[str, Any]:
        """Rebuild every Redis projection from the durable rows (#15663 rule 2).

        This is the claim ``store_authority.py`` makes about knowledge facts,
        made executable: the ``fact:*`` hashes, the dedup and unique-key indexes,
        the session links and the ownership sets are all derivable from
        ``knowledge_facts``, so losing them costs a rebuild rather than the data.
        Had this existed in #12733, the 43 lost facts would have been one call
        away instead of gone.

        Idempotent — a fact already projected is simply rewritten.
        """
        # Lazy: see the module docstring on why fact_store is not imported at module scope.
        from knowledge import fact_store

        rebuilt = 0
        async for batch in fact_store.iter_facts(batch_size=batch_size):
            for fact in batch:
                await self._project_fact_to_redis(fact["fact_id"], fact["content"], fact["metadata"])
                rebuilt += 1
        self._schedule_bm25_refresh()
        logger.info("Rebuilt Redis projections for %d facts from knowledge_facts", rebuilt)
        return {"status": "success", "rebuilt": rebuilt}
