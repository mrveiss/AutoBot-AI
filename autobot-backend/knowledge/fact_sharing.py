# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fact sharing between users (#689).

Split out of ``facts.py`` rather than added to it: that module is a
grandfathered large file whose exemption freezes the size it was granted for
(#14236), and sharing facts between users is a distinct concern from the
CRUD/dedup lifecycle the rest of that module covers -- these methods only
touch the ``fact:<id>`` hash's ``metadata`` field and the
``user:shared_facts:<user_id>`` index, never the durable row or the dedup
content-hash keys.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class FactSharingMixin:
    """Share facts with other users and look up what was shared with you."""

    async def share_facts(
        self,
        fact_ids: List[str],
        shared_with: List[str],
        shared_by: str,
    ) -> Dict[str, Any]:
        """Share specific facts with other users.

        Creates sharing indices and updates fact metadata with
        shared_with user IDs while preserving original ownership.

        Args:
            fact_ids: List of fact IDs to share
            shared_with: List of user IDs to share with
            shared_by: User ID of the person sharing

        Returns:
            Dict with sharing results
        """
        shared_count = 0
        errors = []

        for fact_id in fact_ids:
            try:
                await self._share_single_fact(fact_id, shared_with, shared_by)
                shared_count += 1
            except Exception as e:
                logger.error("Failed to share fact %s: %s", fact_id, e)
                errors.append({"fact_id": fact_id, "error": "Fact sharing failed"})

        return {
            "shared_count": shared_count,
            "errors": errors,
        }

    async def _share_single_fact(self, fact_id: str, shared_with: List[str], shared_by: str) -> None:
        """Share a single fact with users. Helper for share_facts (#689).
        #16709: routes through the canonical share_fact() index, not a second one
        that never set visibility=SHARED."""
        fact_key = "fact:%s" % fact_id
        raw = await asyncio.to_thread(self.redis_client.hget, fact_key, "metadata")
        if not raw:
            raise ValueError("Fact %s not found" % fact_id)

        raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        metadata = json.loads(raw_str) if isinstance(raw_str, str) else raw_str

        ownership_manager = getattr(self, "ownership_manager", None)
        if ownership_manager is None:
            raise ValueError("Ownership management not available")

        metadata = await ownership_manager.share_fact(fact_id, user_ids=shared_with, fact_metadata=metadata)
        metadata["shared_by"] = shared_by
        metadata["shared_at"] = datetime.now(tz=timezone.utc).isoformat()

        await asyncio.to_thread(self.redis_client.hset, fact_key, "metadata", json.dumps(metadata))

    async def get_shared_facts(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all facts shared with a user (#689).
        #16709: reads the canonical index share_fact/set_owner write, not the
        second one check_access never agreed with.

        Args:
            user_id: Recipient user ID

        Returns:
            List of fact dicts with content and metadata
        """
        try:
            ownership_manager = getattr(self, "ownership_manager", None)
            if ownership_manager is None:
                return []
            fact_ids = await ownership_manager.get_shared_facts(user_id)
            return [fact for fid in fact_ids if (fact := self.get_fact(fid))]
        except Exception as e:
            logger.error("Failed to get shared facts for %s: %s", user_id, e)
            return []
