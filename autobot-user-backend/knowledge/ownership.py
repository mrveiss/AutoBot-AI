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
    """Visibility levels for knowledge facts."""

    PRIVATE = "private"  # Only owner can access
    SHARED = "shared"  # Owner + explicitly shared users
    PUBLIC = "public"  # All users can access


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
    ) -> None:
        """Set ownership metadata and update Redis indexes.

        Args:
            fact_id: Fact ID
            owner_id: User ID of the owner
            visibility: Visibility level (private/shared/public)
            source_type: Source type (chat/manual/import/system)
            shared_with: Optional list of user IDs to share with
        """
        shared_with = shared_with or []

        # Add to owner's facts index
        await asyncio.to_thread(
            self.redis_client.sadd, f"user:kb:facts:{owner_id}", fact_id
        )

        # Add to chat_knowledge category if source is chat
        if source_type == SourceType.CHAT:
            await asyncio.to_thread(
                self.redis_client.sadd, "kb:category:chat_knowledge", fact_id
            )

        # Add to shared users' indexes
        if visibility == VisibilityLevel.SHARED and shared_with:
            for user_id in shared_with:
                await asyncio.to_thread(
                    self.redis_client.sadd, f"user:kb:shared:{user_id}", fact_id
                )

        logger.debug(
            "Set ownership for fact %s: owner=%s, visibility=%s, shared_with=%d",
            fact_id,
            owner_id,
            visibility,
            len(shared_with),
        )

    async def check_access(
        self, fact_id: str, user_id: str, fact_metadata: Dict
    ) -> bool:
        """Check if user has access to a fact.

        Args:
            fact_id: Fact ID to check
            user_id: User ID requesting access
            fact_metadata: Fact metadata dict

        Returns:
            True if user has access, False otherwise
        """
        # Extract ownership metadata
        owner_id = fact_metadata.get("owner_id")
        visibility = fact_metadata.get("visibility", VisibilityLevel.PRIVATE)
        shared_with = fact_metadata.get("shared_with", [])

        # Owner always has access
        if owner_id and owner_id == user_id:
            return True

        # Public facts are accessible to all
        if visibility == VisibilityLevel.PUBLIC:
            return True

        # Check if explicitly shared with user
        if visibility == VisibilityLevel.SHARED and user_id in shared_with:
            return True

        # No access
        return False

    async def share_fact(
        self, fact_id: str, user_ids: List[str], fact_metadata: Dict
    ) -> Dict:
        """Share a fact with additional users.

        Args:
            fact_id: Fact ID to share
            user_ids: List of user IDs to share with
            fact_metadata: Current fact metadata

        Returns:
            Updated metadata dict
        """
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

        # Update metadata
        fact_metadata["shared_with"] = list(shared_with)

        # Ensure visibility is set to shared if sharing
        if fact_metadata.get("visibility") == VisibilityLevel.PRIVATE:
            fact_metadata["visibility"] = VisibilityLevel.SHARED

        logger.info(
            "Shared fact %s with %d new users (total: %d)",
            fact_id,
            len(new_users),
            len(shared_with),
        )

        return fact_metadata

    async def unshare_fact(
        self, fact_id: str, user_ids: List[str], fact_metadata: Dict
    ) -> Dict:
        """Remove users from fact sharing list.

        Args:
            fact_id: Fact ID to unshare
            user_ids: List of user IDs to remove
            fact_metadata: Current fact metadata

        Returns:
            Updated metadata dict
        """
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

        # Update metadata
        fact_metadata["shared_with"] = list(shared_with)

        # If no more shared users, revert to private
        if (
            not shared_with
            and fact_metadata.get("visibility") == VisibilityLevel.SHARED
        ):
            fact_metadata["visibility"] = VisibilityLevel.PRIVATE

        logger.info(
            "Unshared fact %s from %d users (remaining: %d)",
            fact_id,
            len(removed_users),
            len(shared_with),
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

    async def filter_accessible_facts(
        self, fact_ids: List[str], user_id: str, redis_client
    ) -> Set[str]:
        """Filter list of facts to only those accessible by user.

        Args:
            fact_ids: List of fact IDs to filter
            user_id: User ID requesting access
            redis_client: Redis client for fact metadata lookup

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

                    if await self.check_access(fact_id, user_id, metadata):
                        accessible.add(fact_id)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # If metadata is malformed, skip this fact
                    continue

        return accessible

    async def cleanup_ownership_indexes(self, fact_id: str, fact_metadata: Dict):
        """Clean up Redis indexes when a fact is deleted.

        Args:
            fact_id: Fact ID being deleted
            fact_metadata: Fact metadata for cleanup
        """
        owner_id = fact_metadata.get("owner_id")
        source_type = fact_metadata.get("source_type")
        shared_with = fact_metadata.get("shared_with", [])

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

        # Remove from all shared users' indexes
        for user_id in shared_with:
            await asyncio.to_thread(
                self.redis_client.srem, f"user:kb:shared:{user_id}", fact_id
            )

        logger.debug(
            "Cleaned up ownership indexes for fact %s (owner=%s, shared=%d)",
            fact_id,
            owner_id,
            len(shared_with),
        )
