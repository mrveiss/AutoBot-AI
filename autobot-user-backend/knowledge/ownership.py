# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Ownership and Access Control Module

Manages user ownership, visibility, and sharing for knowledge base facts.
Provides Redis index management and access control checking.

Issue #688: User ownership model for chat-derived knowledge
"""

import asyncio
import json
import logging
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class VisibilityLevel(str, Enum):
    """Visibility levels for knowledge facts.

    Issue #679: Extended with hierarchical scopes.
    """

    PRIVATE = "private"  # Only owner can access
    SHARED = "shared"  # Owner + explicitly shared users/groups
    GROUP = "group"  # Accessible to specific group/team members
    ORGANIZATION = "organization"  # Accessible to all org members
    SYSTEM = "system"  # Platform-wide, accessible to all users
    PUBLIC = "public"  # Alias for SYSTEM (backward compatibility)


class SourceType(str, Enum):
    """Source type for fact creation."""

    CHAT = "chat"  # Created from chat conversation
    MANUAL = "manual"  # Manually created by user
    IMPORT = "import"  # Imported from external source
    SYSTEM = "system"  # System-generated fact


class KnowledgeOwnership:
    """
    Manages ownership and access control for knowledge base facts.

    Maintains Redis indexes for efficient user-based queries:
    - user:kb:facts:{user_id} -> Set of fact IDs owned by user
    - user:kb:shared:{user_id} -> Set of fact IDs shared with user
    - kb:category:chat_knowledge -> Set of all chat-derived facts
    """

    def __init__(self, redis_client):
        """Initialize ownership manager with Redis client.

        Args:
            redis_client: Redis client instance (sync)
        """
        self.redis_client = redis_client
        logger.info("KnowledgeOwnership initialized")

    async def set_owner(
        self,
        fact_id: str,
        owner_id: str,
        visibility: str = VisibilityLevel.PRIVATE,
        source_type: str = SourceType.MANUAL,
        shared_with: Optional[List[str]] = None,
        organization_id: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
    ) -> None:
        """Set ownership metadata and update Redis indexes.

        Issue #679: Extended with organization and group support.

        Args:
            fact_id: Fact ID
            owner_id: User ID of the owner
            visibility: Visibility level (private/shared/group/organization/system)
            source_type: Source type (chat/manual/import/system)
            shared_with: Optional list of user IDs to share with
            organization_id: Organization ID for org-level knowledge
            group_ids: List of group/team IDs for group-level knowledge
        """
        shared_with = shared_with or []
        group_ids = group_ids or []

        # Add to owner's facts index
        await asyncio.to_thread(
            self.redis_client.sadd, f"user:kb:facts:{owner_id}", fact_id
        )

        # Add to chat_knowledge category if source is chat
        if source_type == SourceType.CHAT:
            await asyncio.to_thread(
                self.redis_client.sadd, "kb:category:chat_knowledge", fact_id
            )

        # Add to organization index
        if organization_id:
            await asyncio.to_thread(
                self.redis_client.sadd, f"org:kb:facts:{organization_id}", fact_id
            )

        # Add to group indexes
        if visibility == VisibilityLevel.GROUP and group_ids:
            for group_id in group_ids:
                await asyncio.to_thread(
                    self.redis_client.sadd, f"group:kb:facts:{group_id}", fact_id
                )

        # Add to shared users' indexes
        if visibility == VisibilityLevel.SHARED and shared_with:
            for user_id in shared_with:
                await asyncio.to_thread(
                    self.redis_client.sadd, f"user:kb:shared:{user_id}", fact_id
                )

        # Add to system-wide index
        if visibility == VisibilityLevel.SYSTEM:
            await asyncio.to_thread(self.redis_client.sadd, "kb:system:facts", fact_id)

        logger.debug(
            "Set ownership for fact %s: owner=%s, visibility=%s, org=%s, groups=%d, shared=%d",
            fact_id,
            owner_id,
            visibility,
            organization_id,
            len(group_ids),
            len(shared_with),
        )

    async def check_access(
        self,
        fact_id: str,
        user_id: str,
        fact_metadata: Dict,
        user_org_id: Optional[str] = None,
        user_group_ids: Optional[List[str]] = None,
    ) -> bool:
        """Check if user has access to a fact.

        Issue #679: Extended with hierarchical access control.

        Args:
            fact_id: Fact ID to check
            user_id: User ID requesting access
            fact_metadata: Fact metadata dict
            user_org_id: User's organization ID
            user_group_ids: List of group/team IDs user belongs to

        Returns:
            True if user has access, False otherwise
        """
        user_group_ids = user_group_ids or []

        # Extract ownership metadata
        owner_id = fact_metadata.get("owner_id")
        visibility = fact_metadata.get("visibility", VisibilityLevel.PRIVATE)
        shared_with = fact_metadata.get("shared_with", [])
        fact_org_id = fact_metadata.get("organization_id")
        fact_group_ids = fact_metadata.get("group_ids", [])

        # Owner always has access
        if owner_id and owner_id == user_id:
            return True

        # System-level facts are accessible to all
        if visibility in (VisibilityLevel.SYSTEM, VisibilityLevel.PUBLIC):
            return True

        # Organization-level facts accessible to org members
        if (
            visibility == VisibilityLevel.ORGANIZATION
            and user_org_id
            and fact_org_id == user_org_id
        ):
            return True

        # Group-level facts accessible to group members
        if visibility == VisibilityLevel.GROUP and fact_group_ids:
            # Check if user belongs to any of the fact's groups
            if any(gid in user_group_ids for gid in fact_group_ids):
                return True

        # Check if explicitly shared with user
        if visibility == VisibilityLevel.SHARED and user_id in shared_with:
            return True

        # No access
        return False

    async def share_fact(
        self,
        fact_id: str,
        user_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        fact_metadata: Dict = None,
    ) -> Dict:
        """Share a fact with additional users and/or groups.

        Issue #679: Extended to support group sharing.

        Args:
            fact_id: Fact ID to share
            user_ids: List of user IDs to share with
            group_ids: List of group IDs to share with
            fact_metadata: Current fact metadata

        Returns:
            Updated metadata dict
        """
        user_ids = user_ids or []
        group_ids = group_ids or []

        if fact_metadata is None:
            fact_metadata = {}

        # Share with individual users
        shared_with = set(fact_metadata.get("shared_with", []))
        new_users = []

        for user_id in user_ids:
            if user_id not in shared_with:
                shared_with.add(user_id)
                new_users.append(user_id)
                # Add to user's shared index
                await asyncio.to_thread(
                    self.redis_client.sadd, f"user:kb:shared:{user_id}", fact_id
                )

        # Share with groups
        fact_group_ids = set(fact_metadata.get("group_ids", []))
        new_groups = []

        for group_id in group_ids:
            if group_id not in fact_group_ids:
                fact_group_ids.add(group_id)
                new_groups.append(group_id)
                # Add to group's facts index
                await asyncio.to_thread(
                    self.redis_client.sadd, f"group:kb:facts:{group_id}", fact_id
                )

        # Update metadata
        fact_metadata["shared_with"] = list(shared_with)
        fact_metadata["group_ids"] = list(fact_group_ids)

        # Set appropriate visibility
        if group_ids and not user_ids:
            fact_metadata["visibility"] = VisibilityLevel.GROUP
        elif fact_metadata.get("visibility") == VisibilityLevel.PRIVATE:
            fact_metadata["visibility"] = VisibilityLevel.SHARED

        logger.info(
            "Shared fact %s with %d new users and %d new groups (total: %d users, %d groups)",
            fact_id,
            len(new_users),
            len(new_groups),
            len(shared_with),
            len(fact_group_ids),
        )

        return fact_metadata

    async def unshare_fact(
        self,
        fact_id: str,
        user_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        fact_metadata: Dict = None,
    ) -> Dict:
        """Remove users and/or groups from fact sharing list.

        Issue #679: Extended to support group unsharing.

        Args:
            fact_id: Fact ID to unshare
            user_ids: List of user IDs to remove
            group_ids: List of group IDs to remove
            fact_metadata: Current fact metadata

        Returns:
            Updated metadata dict
        """
        user_ids = user_ids or []
        group_ids = group_ids or []

        if fact_metadata is None:
            fact_metadata = {}

        # Unshare from individual users
        shared_with = set(fact_metadata.get("shared_with", []))
        removed_users = []

        for user_id in user_ids:
            if user_id in shared_with:
                shared_with.remove(user_id)
                removed_users.append(user_id)
                # Remove from user's shared index
                await asyncio.to_thread(
                    self.redis_client.srem, f"user:kb:shared:{user_id}", fact_id
                )

        # Unshare from groups
        fact_group_ids = set(fact_metadata.get("group_ids", []))
        removed_groups = []

        for group_id in group_ids:
            if group_id in fact_group_ids:
                fact_group_ids.remove(group_id)
                removed_groups.append(group_id)
                # Remove from group's facts index
                await asyncio.to_thread(
                    self.redis_client.srem, f"group:kb:facts:{group_id}", fact_id
                )

        # Update metadata
        fact_metadata["shared_with"] = list(shared_with)
        fact_metadata["group_ids"] = list(fact_group_ids)

        # Adjust visibility if needed
        if not shared_with and not fact_group_ids:
            if fact_metadata.get("visibility") in (
                VisibilityLevel.SHARED,
                VisibilityLevel.GROUP,
            ):
                fact_metadata["visibility"] = VisibilityLevel.PRIVATE

        logger.info(
            "Unshared fact %s from %d users and %d groups (remaining: %d users, %d groups)",
            fact_id,
            len(removed_users),
            len(removed_groups),
            len(shared_with),
            len(fact_group_ids),
        )

        return fact_metadata

    async def get_user_facts(
        self, user_id: str, limit: Optional[int] = None, offset: int = 0
    ) -> List[str]:
        """Get all fact IDs owned by a user.

        Args:
            user_id: User ID
            limit: Optional limit on results
            offset: Pagination offset

        Returns:
            List of fact IDs
        """
        fact_ids = await asyncio.to_thread(
            self.redis_client.smembers, f"user:kb:facts:{user_id}"
        )

        # Decode bytes to strings
        fact_ids = [
            fid.decode("utf-8") if isinstance(fid, bytes) else fid
            for fid in (fact_ids or [])
        ]

        # Sort for consistent pagination
        fact_ids = sorted(fact_ids)

        # Apply pagination
        if offset > 0:
            fact_ids = fact_ids[offset:]
        if limit is not None:
            fact_ids = fact_ids[:limit]

        return fact_ids

    async def get_shared_facts(
        self, user_id: str, limit: Optional[int] = None, offset: int = 0
    ) -> List[str]:
        """Get all fact IDs shared with a user.

        Args:
            user_id: User ID
            limit: Optional limit on results
            offset: Pagination offset

        Returns:
            List of fact IDs
        """
        fact_ids = await asyncio.to_thread(
            self.redis_client.smembers, f"user:kb:shared:{user_id}"
        )

        # Decode bytes to strings
        fact_ids = [
            fid.decode("utf-8") if isinstance(fid, bytes) else fid
            for fid in (fact_ids or [])
        ]

        # Sort for consistent pagination
        fact_ids = sorted(fact_ids)

        # Apply pagination
        if offset > 0:
            fact_ids = fact_ids[offset:]
        if limit is not None:
            fact_ids = fact_ids[:limit]

        return fact_ids

    async def get_chat_knowledge_facts(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List[str]:
        """Get all chat-derived fact IDs.

        Args:
            limit: Optional limit on results
            offset: Pagination offset

        Returns:
            List of fact IDs
        """
        fact_ids = await asyncio.to_thread(
            self.redis_client.smembers, "kb:category:chat_knowledge"
        )

        # Decode bytes to strings
        fact_ids = [
            fid.decode("utf-8") if isinstance(fid, bytes) else fid
            for fid in (fact_ids or [])
        ]

        # Sort for consistent pagination
        fact_ids = sorted(fact_ids)

        # Apply pagination
        if offset > 0:
            fact_ids = fact_ids[offset:]
        if limit is not None:
            fact_ids = fact_ids[:limit]

        return fact_ids

    async def get_organization_facts(
        self, organization_id: str, limit: Optional[int] = None, offset: int = 0
    ) -> List[str]:
        """Get all fact IDs for an organization.

        Issue #679: Organization-level knowledge access.

        Args:
            organization_id: Organization ID
            limit: Optional limit on results
            offset: Pagination offset

        Returns:
            List of fact IDs
        """
        fact_ids = await asyncio.to_thread(
            self.redis_client.smembers, f"org:kb:facts:{organization_id}"
        )

        # Decode bytes to strings
        fact_ids = [
            fid.decode("utf-8") if isinstance(fid, bytes) else fid
            for fid in (fact_ids or [])
        ]

        # Sort for consistent pagination
        fact_ids = sorted(fact_ids)

        # Apply pagination
        if offset > 0:
            fact_ids = fact_ids[offset:]
        if limit is not None:
            fact_ids = fact_ids[:limit]

        return fact_ids

    async def get_group_facts(
        self, group_id: str, limit: Optional[int] = None, offset: int = 0
    ) -> List[str]:
        """Get all fact IDs for a group/team.

        Issue #679: Group-level knowledge access.

        Args:
            group_id: Group/Team ID
            limit: Optional limit on results
            offset: Pagination offset

        Returns:
            List of fact IDs
        """
        fact_ids = await asyncio.to_thread(
            self.redis_client.smembers, f"group:kb:facts:{group_id}"
        )

        # Decode bytes to strings
        fact_ids = [
            fid.decode("utf-8") if isinstance(fid, bytes) else fid
            for fid in (fact_ids or [])
        ]

        # Sort for consistent pagination
        fact_ids = sorted(fact_ids)

        # Apply pagination
        if offset > 0:
            fact_ids = fact_ids[offset:]
        if limit is not None:
            fact_ids = fact_ids[:limit]

        return fact_ids

    async def get_system_facts(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List[str]:
        """Get all system-wide fact IDs.

        Issue #679: System-level knowledge access.

        Args:
            limit: Optional limit on results
            offset: Pagination offset

        Returns:
            List of fact IDs
        """
        fact_ids = await asyncio.to_thread(
            self.redis_client.smembers, "kb:system:facts"
        )

        # Decode bytes to strings
        fact_ids = [
            fid.decode("utf-8") if isinstance(fid, bytes) else fid
            for fid in (fact_ids or [])
        ]

        # Sort for consistent pagination
        fact_ids = sorted(fact_ids)

        # Apply pagination
        if offset > 0:
            fact_ids = fact_ids[offset:]
        if limit is not None:
            fact_ids = fact_ids[:limit]

        return fact_ids

    async def filter_accessible_facts(
        self,
        fact_ids: List[str],
        user_id: str,
        redis_client,
        user_org_id: Optional[str] = None,
        user_group_ids: Optional[List[str]] = None,
    ) -> Set[str]:
        """Filter list of facts to only those accessible by user.

        Issue #679: Extended with hierarchical access control.

        Args:
            fact_ids: List of fact IDs to filter
            user_id: User ID requesting access
            redis_client: Redis client for fact metadata lookup
            user_org_id: User's organization ID
            user_group_ids: List of group IDs user belongs to

        Returns:
            Set of accessible fact IDs
        """
        accessible = set()

        # Batch fetch all fact metadata
        pipeline = redis_client.pipeline()
        for fact_id in fact_ids:
            pipeline.hgetall(f"fact:{fact_id}")
        facts_data = await asyncio.to_thread(pipeline.execute)

        for fact_id, fact_data in zip(fact_ids, facts_data):
            if not fact_data:
                continue

            # Decode and parse metadata
            metadata_str = fact_data.get(b"metadata") or fact_data.get("metadata")
            if metadata_str:
                try:
                    if isinstance(metadata_str, bytes):
                        metadata_str = metadata_str.decode("utf-8")
                    metadata = json.loads(metadata_str)

                    if await self.check_access(
                        fact_id, user_id, metadata, user_org_id, user_group_ids
                    ):
                        accessible.add(fact_id)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # If metadata is malformed, skip this fact
                    continue

        return accessible

    async def get_all_accessible_facts(
        self,
        user_id: str,
        user_org_id: Optional[str] = None,
        user_group_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[str]:
        """Get all facts accessible to a user across all scopes.

        Issue #679: Aggregates facts from all accessible scopes.

        Args:
            user_id: User ID
            user_org_id: User's organization ID
            user_group_ids: List of group IDs user belongs to
            limit: Optional limit on results
            offset: Pagination offset

        Returns:
            List of fact IDs accessible to the user
        """
        user_group_ids = user_group_ids or []
        all_fact_ids = set()

        # Get user's own facts
        own_facts = await self.get_user_facts(user_id)
        all_fact_ids.update(own_facts)

        # Get facts shared with user
        shared_facts = await self.get_shared_facts(user_id)
        all_fact_ids.update(shared_facts)

        # Get system facts
        system_facts = await self.get_system_facts()
        all_fact_ids.update(system_facts)

        # Get organization facts
        if user_org_id:
            org_facts = await self.get_organization_facts(user_org_id)
            all_fact_ids.update(org_facts)

        # Get group facts
        for group_id in user_group_ids:
            group_facts = await self.get_group_facts(group_id)
            all_fact_ids.update(group_facts)

        # Convert to sorted list
        fact_ids = sorted(all_fact_ids)

        # Apply pagination
        if offset > 0:
            fact_ids = fact_ids[offset:]
        if limit is not None:
            fact_ids = fact_ids[:limit]

        return fact_ids

    async def cleanup_ownership_indexes(self, fact_id: str, fact_metadata: Dict):
        """Clean up Redis indexes when a fact is deleted.

        Issue #679: Extended to clean up org/group indexes.

        Args:
            fact_id: Fact ID being deleted
            fact_metadata: Fact metadata for cleanup
        """
        owner_id = fact_metadata.get("owner_id")
        source_type = fact_metadata.get("source_type")
        shared_with = fact_metadata.get("shared_with", [])
        organization_id = fact_metadata.get("organization_id")
        group_ids = fact_metadata.get("group_ids", [])
        visibility = fact_metadata.get("visibility")

        # Remove from owner's index
        if owner_id:
            await asyncio.to_thread(
                self.redis_client.srem, f"user:kb:facts:{owner_id}", fact_id
            )

        # Remove from chat_knowledge category
        if source_type == SourceType.CHAT:
            await asyncio.to_thread(
                self.redis_client.srem, "kb:category:chat_knowledge", fact_id
            )

        # Remove from organization index
        if organization_id:
            await asyncio.to_thread(
                self.redis_client.srem, f"org:kb:facts:{organization_id}", fact_id
            )

        # Remove from group indexes
        for group_id in group_ids:
            await asyncio.to_thread(
                self.redis_client.srem, f"group:kb:facts:{group_id}", fact_id
            )

        # Remove from all shared users' indexes
        for user_id in shared_with:
            await asyncio.to_thread(
                self.redis_client.srem, f"user:kb:shared:{user_id}", fact_id
            )

        # Remove from system index
        if visibility == VisibilityLevel.SYSTEM:
            await asyncio.to_thread(self.redis_client.srem, "kb:system:facts", fact_id)

        logger.debug(
            "Cleaned up ownership indexes for fact %s (owner=%s, org=%s, groups=%d, shared=%d)",
            fact_id,
            owner_id,
            organization_id,
            len(group_ids),
            len(shared_with),
        )
