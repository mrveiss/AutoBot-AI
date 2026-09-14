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

from typing import Any, Dict, Optional

from autobot_shared.auth.permissions import is_admin_role
from knowledge.ownership import VisibilityLevel

#: The metadata fields ``set_owner`` indexes a fact by.
OWNERSHIP_KEYS = ("visibility", "source_type", "shared_with", "organization_id", "group_ids", "access_level")
_OWNER_KEYS = ("owner_id", "user_id")


def ownership_changed(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
    """Whether any field the ownership indexes depend on differs between *old* and *new*.

    Compared by value, not by presence: callers routinely write the whole metadata dict
    back with only a flag changed, and that must not cost a reindex.
    """
    return any(old.get(key) != new.get(key) for key in OWNERSHIP_KEYS + _OWNER_KEYS)


#: Metadata values that give a fact the reach of every signed-in user (owner decision, #16654).
PLATFORM_WIDE_VISIBILITY = ("system", "public")
PLATFORM_WIDE_ACCESS = ("general", "autobot")


def requests_platform_wide(metadata: Optional[Dict[str, Any]]) -> bool:
    """Whether *metadata* asks for a platform-wide reach: SYSTEM/PUBLIC, or a general/autobot access level."""
    meta = metadata or {}
    return meta.get("visibility") in PLATFORM_WIDE_VISIBILITY or meta.get("access_level") in PLATFORM_WIDE_ACCESS


def refuses_platform_wide(metadata: Optional[Dict[str, Any]], caller_role: Optional[str]) -> bool:
    """True when a non-admin asks for a platform-wide reach -- a route answers that with 403 (#16663)."""
    return requests_platform_wide(metadata) and not is_admin_role(caller_role)


def drop_owner_fields_unless_admin(metadata: Optional[Dict[str, Any]], caller_role: Optional[str]) -> Dict[str, Any]:
    """*metadata* without ``owner_id``/``user_id`` unless an admin sent it: no one files a fact under another name."""
    if is_admin_role(caller_role):
        return dict(metadata or {})
    return {key: value for key, value in (metadata or {}).items() if key not in _OWNER_KEYS}


def drop_ownership_unless_admin(metadata: Optional[Dict[str, Any]], caller_role: Optional[str]) -> Dict[str, Any]:
    """*metadata* as a caller may set it on ingestion: only an admin chooses who owns or sees a fact.

    A route that forwards caller metadata into the store otherwise lets any signed-in
    user file a fact as SYSTEM or PUBLIC, or under another user's name.
    """
    if is_admin_role(caller_role):
        return dict(metadata or {})
    return {key: value for key, value in (metadata or {}).items() if key not in OWNERSHIP_KEYS + _OWNER_KEYS}


async def index_ownership(ownership_manager, fact_id: str, metadata: Dict[str, Any]) -> bool:
    """Add *fact_id* to every index *metadata* names; False when it names no owner."""
    owner_id = metadata.get("owner_id") or metadata.get("user_id")
    if not owner_id:
        return False
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
