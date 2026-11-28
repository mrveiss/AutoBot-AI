# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Delete exactly the facts a human selected, whatever collections they belong to (#21886, #17038).

Most facts belong to no collection (upload and ingest never write membership), so the selection is by fact id and
not by collection. Each existing selected fact is unlinked from every collection it is in, then deleted completely (row,
vectors, mappings, through ``delete_fact``, which also invalidates the retrieval caches). ``approved`` {facts,
created_at} is checked with the same ``_unapproved`` the collection deletes use; there is no collection identity
here, so ``created_at`` is absent on both sides.
"""

from __future__ import annotations

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from knowledge.collections import _unapproved

logger = get_logger(__name__)


def _text(value) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else value


class SelectedFactsDeleteMixin:
    """The selected-facts delete of the knowledge base (membership-agnostic)."""

    async def _existing_selected(self, fact_ids: List[str]) -> List[str]:
        """The selected ids that exist now, de-duplicated and sorted.

        Existence is settled the way ``delete_fact`` settles it: the Redis hash is only a projection, so a fact
        whose hash is missing but whose durable row exists still counts (and is deleted).
        """
        return [fid for fid in sorted(set(fact_ids)) if await self._read_fact_for_write(fid) is not None]

    async def _unlink_from_collections(self, fid: str) -> None:
        """Take the fact out of every collection it is in and refresh their counts. Idempotent; the row is untouched."""
        collections = [_text(c) for c in await self.redis().smembers(f"fact:collections:{fid}")]
        for cid in collections:
            await self.redis().srem(f"collection:facts:{cid}", fid)
        for cid in collections:
            await self._update_collection_fact_count(cid)
        await self.redis().delete(f"fact:collections:{fid}")  # last: until it is gone a retry redoes the whole unlink

    async def _delete_selected_one(self, fid: str) -> bool:
        """One fact unlinked from its collections, THEN deleted; False when it was not deleted.

        The cleanup runs first and is idempotent while the durable row still exists, so a failure in it leaves a fact
        a retry still finds and finishes; after ``delete_fact`` there is nothing left to repair.
        """
        await self._unlink_from_collections(fid)
        return (await self.delete_fact(fid, _skip_bm25_refresh=True)).get("status") == "success"

    async def _delete_each(self, existing: List[str]) -> List[str]:
        """Delete each fact in turn; the one BM25 refresh (``delete_fact`` skips it) runs even if one raises."""
        done: List[str] = []
        try:
            for fid in existing:
                if await self._delete_selected_one(fid):
                    done.append(fid)
        finally:
            if done:
                self._schedule_bm25_refresh()
        return done

    async def delete_selected_facts(
        self, fact_ids: List[str], confirm: bool = False, approved: dict | None = None
    ) -> Dict[str, Any]:
        """Delete the selected facts that exist; without ``confirm`` only count them (read only)."""
        try:
            existing = await self._existing_selected(fact_ids)
            if not confirm:
                return {"success": True, "facts_to_delete": len(existing), "confirm_required": True}
            if refused := _unapproved(approved, {}, len(existing)):
                return refused
            done = await self._delete_each(existing)
            logger.info("Deleted %d of %d selected facts", len(done), len(existing))
            return self._selected_outcome(len(done), len(existing))
        except Exception as e:
            logger.error("Failed to delete the selected facts: %s", e)
            return {"success": False, "message": "Knowledge operation failed"}

    @staticmethod
    def _selected_outcome(deleted: int, wanted: int) -> Dict[str, Any]:
        if deleted < wanted:
            return {"success": False, "deleted_count": deleted, "message": f"only {deleted} of {wanted} facts deleted"}
        return {"success": True, "deleted_count": deleted, "message": f"Deleted {deleted} facts"}
