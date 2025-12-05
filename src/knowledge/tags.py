# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Tags Management Module

Contains the TagsMixin class for tag operations including adding,
removing, searching, and managing tags on facts.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    import aioredis
    import redis

logger = logging.getLogger(__name__)


class TagsMixin:
    """
    Tag management mixin for knowledge base.

    Provides tag operations:
    - Add tags to facts
    - Remove tags from facts
    - Get fact tags
    - Search facts by tags
    - List all tags
    - Bulk tag operations

    Key Features:
    - Redis SET-based tag indexing
    - Fast tag lookups
    - Tag normalization
    """

    # Type hints for attributes from base class
    redis_client: "redis.Redis"
    aioredis_client: "aioredis.Redis"

    async def add_tags_to_fact(
        self, fact_id: str, tags: List[str]
    ) -> Dict[str, Any]:
        """
        Add tags to a fact.

        Args:
            fact_id: Fact ID
            tags: List of tags to add

        Returns:
            Dict with status
        """
        try:
            # Normalize tags
            normalized_tags = [t.lower().strip() for t in tags if t.strip()]
            if not normalized_tags:
                return {"status": "error", "message": "No valid tags provided"}

            # Get current fact tags
            fact_key = f"fact:{fact_id}"
            exists = await asyncio.to_thread(self.redis_client.exists, fact_key)
            if not exists:
                return {"status": "error", "message": "Fact not found"}

            # Get current metadata
            metadata_json = await asyncio.to_thread(
                self.redis_client.hget, fact_key, "metadata"
            )
            if metadata_json:
                metadata = json.loads(metadata_json)
            else:
                metadata = {}

            # Get current tags
            current_tags = set(metadata.get("tags", []))

            # Add new tags
            current_tags.update(normalized_tags)

            # Update metadata
            metadata["tags"] = list(current_tags)
            await asyncio.to_thread(
                self.redis_client.hset,
                fact_key,
                "metadata",
                json.dumps(metadata),
            )

            # Add to tag index
            for tag in normalized_tags:
                tag_key = f"tag:{tag}"
                await asyncio.to_thread(self.redis_client.sadd, tag_key, fact_id)

            logger.info(f"Added tags {normalized_tags} to fact {fact_id}")
            return {"status": "success", "tags_added": normalized_tags}

        except Exception as e:
            logger.error(f"Failed to add tags to fact {fact_id}: {e}")
            return {"status": "error", "message": str(e)}

    async def remove_tags_from_fact(
        self, fact_id: str, tags: List[str]
    ) -> Dict[str, Any]:
        """
        Remove tags from a fact.

        Args:
            fact_id: Fact ID
            tags: List of tags to remove

        Returns:
            Dict with status
        """
        try:
            # Normalize tags
            normalized_tags = [t.lower().strip() for t in tags if t.strip()]
            if not normalized_tags:
                return {"status": "error", "message": "No valid tags provided"}

            # Get fact
            fact_key = f"fact:{fact_id}"
            exists = await asyncio.to_thread(self.redis_client.exists, fact_key)
            if not exists:
                return {"status": "error", "message": "Fact not found"}

            # Get current metadata
            metadata_json = await asyncio.to_thread(
                self.redis_client.hget, fact_key, "metadata"
            )
            if metadata_json:
                metadata = json.loads(metadata_json)
            else:
                metadata = {}

            # Get current tags
            current_tags = set(metadata.get("tags", []))

            # Remove specified tags
            current_tags.difference_update(normalized_tags)

            # Update metadata
            metadata["tags"] = list(current_tags)
            await asyncio.to_thread(
                self.redis_client.hset,
                fact_key,
                "metadata",
                json.dumps(metadata),
            )

            # Remove from tag index
            for tag in normalized_tags:
                tag_key = f"tag:{tag}"
                await asyncio.to_thread(self.redis_client.srem, tag_key, fact_id)

            logger.info(f"Removed tags {normalized_tags} from fact {fact_id}")
            return {"status": "success", "tags_removed": normalized_tags}

        except Exception as e:
            logger.error(f"Failed to remove tags from fact {fact_id}: {e}")
            return {"status": "error", "message": str(e)}

    async def get_fact_tags(self, fact_id: str) -> Dict[str, Any]:
        """
        Get all tags for a fact.

        Args:
            fact_id: Fact ID

        Returns:
            Dict with tags list
        """
        try:
            fact_key = f"fact:{fact_id}"
            metadata_json = await asyncio.to_thread(
                self.redis_client.hget, fact_key, "metadata"
            )

            if not metadata_json:
                return {"status": "error", "message": "Fact not found"}

            metadata = json.loads(metadata_json)
            tags = metadata.get("tags", [])

            return {"status": "success", "fact_id": fact_id, "tags": tags}

        except Exception as e:
            logger.error(f"Failed to get tags for fact {fact_id}: {e}")
            return {"status": "error", "message": str(e)}

    async def search_facts_by_tags(
        self, tags: List[str], match_all: bool = True
    ) -> Dict[str, Any]:
        """
        Search for facts by tags.

        Args:
            tags: List of tags to search
            match_all: If True, match ALL tags. If False, match ANY tag.

        Returns:
            Dict with fact IDs
        """
        try:
            result = await self._get_fact_ids_by_tags(tags, match_all=match_all)
            if result["success"]:
                return {
                    "status": "success",
                    "fact_ids": list(result["fact_ids"]),
                    "count": len(result["fact_ids"]),
                }
            else:
                return {"status": "error", "message": result.get("message", "Unknown error")}

        except Exception as e:
            logger.error(f"Failed to search facts by tags: {e}")
            return {"status": "error", "message": str(e)}

    async def list_all_tags(self) -> Dict[str, Any]:
        """
        List all tags in the knowledge base with fact counts.

        Returns:
            Dict with tags and counts
        """
        try:
            # Scan for all tag keys
            tag_keys = await self._scan_redis_keys_async("tag:*")

            tags_info = []
            for tag_key in tag_keys:
                # Extract tag name
                tag_name = (
                    tag_key.decode("utf-8").replace("tag:", "")
                    if isinstance(tag_key, bytes)
                    else tag_key.replace("tag:", "")
                )

                # Get fact count for this tag
                count = await asyncio.to_thread(self.redis_client.scard, tag_key)

                tags_info.append({"tag": tag_name, "fact_count": count})

            # Sort by fact count descending
            tags_info.sort(key=lambda x: x["fact_count"], reverse=True)

            return {
                "status": "success",
                "total_tags": len(tags_info),
                "tags": tags_info,
            }

        except Exception as e:
            logger.error(f"Failed to list all tags: {e}")
            return {"status": "error", "message": str(e)}

    async def bulk_tag_facts(
        self, fact_ids: List[str], tags: List[str]
    ) -> Dict[str, Any]:
        """
        Add tags to multiple facts in bulk.

        Args:
            fact_ids: List of fact IDs
            tags: List of tags to add

        Returns:
            Dict with status and counts
        """
        try:
            success_count = 0
            error_count = 0

            for fact_id in fact_ids:
                result = await self.add_tags_to_fact(fact_id, tags)
                if result.get("status") == "success":
                    success_count += 1
                else:
                    error_count += 1

            return {
                "status": "success",
                "success_count": success_count,
                "error_count": error_count,
                "total_facts": len(fact_ids),
            }

        except Exception as e:
            logger.error(f"Bulk tag operation failed: {e}")
            return {"status": "error", "message": str(e)}

    # Method references needed from other mixins
    async def _get_fact_ids_by_tags(self, tags: List[str], match_all: bool = True):
        """Get fact IDs by tags - implemented in search mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    async def _scan_redis_keys_async(self, pattern: str):
        """Scan Redis keys - implemented in base class"""
        raise NotImplementedError("Should be implemented in composed class")
