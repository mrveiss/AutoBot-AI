# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Keep a fact's ownership indexes in step with its metadata (#16663).

``KnowledgeOwnership.set_owner`` only ever adds to the Redis indexes. A visibility
change written through it alone left the fact in the index it was leaving --
``kb:system:facts`` included, which every signed-in user reads -- so a fact demoted
from SYSTEM stayed platform-wide. A write that changes ownership metadata goes
through :func:`reindex_ownership`, which removes the old entries before adding the
new ones.
"""

import asyncio
from typing import Any, Dict, Optional

from autobot_shared.auth.permissions import is_admin_role
from knowledge.ownership import VisibilityLevel

#: Read for every signed-in user (``KnowledgeOwnership.get_system_facts``).
SYSTEM_FACTS_INDEX = "kb:system:facts"

#: The metadata fields ``set_owner`` indexes a fact by.
OWNERSHIP_KEYS = ("visibility", "source_type", "shared_with", "organization_id", "group_ids", "access_level")
_OWNER_KEYS = ("owner_id", "user_id")


def ownership_changed(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
    """Whether any field the ownership indexes depend on differs between *old* and *new*.

    Compared by value, not by presence: callers routinely write the whole metadata dict
    back with only a flag changed, and that must not cost a reindex.
    """
    return any(old.get(key) != new.get(key) for key in OWNERSHIP_KEYS + _OWNER_KEYS)


def drop_ownership_unless_admin(metadata: Optional[Dict[str, Any]], caller_role: Optional[str]) -> Dict[str, Any]:
    """*metadata* as a caller may set it on ingestion: only an admin chooses who owns or sees a fact.

    A route that forwards caller metadata into the store otherwise lets any signed-in
    user file a fact as SYSTEM or PUBLIC, or under another user's name.
    """
    if is_admin_role(caller_role):
        return dict(metadata or {})
    return {key: value for key, value in (metadata or {}).items() if key not in OWNERSHIP_KEYS + _OWNER_KEYS}


async def index_ownership(ownership_manager, fact_id: str, metadata: Dict[str, Any]) -> bool:
    """Add *fact_id* to every index *metadata* names; False when it names none.

    A fact nobody owns has no owner index, but an ownerless SYSTEM fact, an ingested
    document (#16693), still belongs in ``kb:system:facts``.
    """
    owner_id = metadata.get("owner_id") or metadata.get("user_id")
    if not owner_id:
        if metadata.get("visibility") != VisibilityLevel.SYSTEM:
            return False
        await asyncio.to_thread(ownership_manager.redis_client.sadd, SYSTEM_FACTS_INDEX, fact_id)
        return True
    ownership = {key: metadata[key] for key in OWNERSHIP_KEYS if metadata.get(key)}
    await ownership_manager.set_owner(fact_id=fact_id, owner_id=owner_id, **ownership)
    return True


async def reindex_ownership(ownership_manager, fact_id: str, old: Dict[str, Any], new: Dict[str, Any]) -> None:
    """Move *fact_id* from the indexes *old* filed it under to the ones *new* names.

    Remove first, then add. A failure in between leaves the fact in fewer indexes, never
    in one its metadata no longer grants, so it fails closed, and the caller sees the error.
    A retry of the same write does NOT repair the indexes: ``update_fact`` has already
    stored the new metadata, so the retry sees no ownership change. The ownership
    reconciliation (#16676) is what brings the indexes back in step.
    """
    # Clean up as though it had been SYSTEM: srem of a non-member is a no-op, and this
    # also drops a stale kb:system:facts entry an add-only write before #16663 left.
    await ownership_manager.cleanup_ownership_indexes(fact_id, {**old, "visibility": VisibilityLevel.SYSTEM})
    await index_ownership(ownership_manager, fact_id, new)
