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
from typing import TYPE_CHECKING, Any, Dict, List, Optional

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

            # Issue #370: Add to tag index in parallel
            await asyncio.gather(*[
                asyncio.to_thread(self.redis_client.sadd, f"tag:{tag}", fact_id)
                for tag in normalized_tags
            ])

            logger.info("Added tags %s to fact %s", normalized_tags, fact_id)
            return {"status": "success", "tags_added": normalized_tags}

        except Exception as e:
            logger.error("Failed to add tags to fact %s: %s", fact_id, e)
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

            # Issue #370: Remove from tag index in parallel
            await asyncio.gather(*[
                asyncio.to_thread(self.redis_client.srem, f"tag:{tag}", fact_id)
                for tag in normalized_tags
            ])

            logger.info("Removed tags %s from fact %s", normalized_tags, fact_id)
            return {"status": "success", "tags_removed": normalized_tags}

        except Exception as e:
            logger.error("Failed to remove tags from fact %s: %s", fact_id, e)
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
            logger.error("Failed to get tags for fact %s: %s", fact_id, e)
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
            logger.error("Failed to search facts by tags: %s", e)
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

            # Issue #370: Fetch all tag counts in parallel
            async def get_tag_info(tag_key):
                """Get tag name and count."""
                tag_name = (
                    tag_key.decode("utf-8").replace("tag:", "")
                    if isinstance(tag_key, bytes)
                    else tag_key.replace("tag:", "")
                )
                count = await asyncio.to_thread(self.redis_client.scard, tag_key)
                return {"tag": tag_name, "fact_count": count}

            results = await asyncio.gather(
                *[get_tag_info(tag_key) for tag_key in tag_keys],
                return_exceptions=True,
            )
            tags_info = [r for r in results if not isinstance(r, Exception)]

            # Sort by fact count descending
            tags_info.sort(key=lambda x: x["fact_count"], reverse=True)

            return {
                "status": "success",
                "total_tags": len(tags_info),
                "tags": tags_info,
            }

        except Exception as e:
            logger.error("Failed to list all tags: %s", e)
            return {"status": "error", "message": str(e)}

    def _build_bulk_tag_result(
        self, fact_id: str, result: Any, operation: str
    ) -> tuple:
        """Build single result for bulk tag operation (Issue #398: extracted)."""
        if isinstance(result, Exception):
            return False, {"fact_id": fact_id, "success": False, "error": str(result)}
        if result.get("status") == "success":
            tags_key = "tags_added" if operation == "add" else "tags_removed"
            return True, {
                "fact_id": fact_id, "success": True,
                "tags_affected": result.get(tags_key, []),
            }
        return False, {
            "fact_id": fact_id, "success": False,
            "error": result.get("message", "Unknown error"),
        }

    def _determine_bulk_status(self, processed: int, failed: int) -> str:
        """Determine overall bulk operation status (Issue #398: extracted)."""
        if failed == 0:
            return "success"
        return "partial_success" if processed > 0 else "error"

    async def bulk_tag_facts(
        self, fact_ids: List[str], tags: List[str], operation: str = "add"
    ) -> Dict[str, Any]:
        """Add or remove tags from multiple facts (Issue #398: refactored)."""
        try:
            if operation not in ("add", "remove"):
                return {
                    "status": "error",
                    "message": f"Invalid operation: {operation}. Must be 'add' or 'remove'",
                }
            tag_method = (
                self.add_tags_to_fact if operation == "add"
                else self.remove_tags_from_fact
            )
            results = await asyncio.gather(
                *[tag_method(fact_id, tags) for fact_id in fact_ids],
                return_exceptions=True,
            )

            processed_count = 0
            failed_count = 0
            per_fact_results = []
            for fact_id, result in zip(fact_ids, results):
                success, detail = self._build_bulk_tag_result(fact_id, result, operation)
                per_fact_results.append(detail)
                if success:
                    processed_count += 1
                else:
                    failed_count += 1

            logger.info(
                "Bulk %s tags: %d/%d succeeded", operation, processed_count, len(fact_ids)
            )
            return {
                "status": self._determine_bulk_status(processed_count, failed_count),
                "operation": operation,
                "processed_count": processed_count,
                "failed_count": failed_count,
                "total_facts": len(fact_ids),
                "results": per_fact_results,
            }
        except Exception as e:
            logger.error("Bulk tag operation failed: %s", e)
            return {"status": "error", "message": str(e)}

    # =========================================================================
    # TAG MANAGEMENT CRUD OPERATIONS (Issue #409)
    # =========================================================================

    async def rename_tag(self, old_tag: str, new_tag: str) -> Dict[str, Any]:
        """
        Rename a tag globally across all facts.

        This operation:
        1. Gets all fact IDs with the old tag
        2. Updates metadata in each fact (remove old, add new)
        3. Creates new tag index and deletes old one

        Args:
            old_tag: Current tag name to rename
            new_tag: New tag name

        Returns:
            Dict with status and affected fact count
        """
        try:
            # Normalize tags
            old_tag = old_tag.lower().strip()
            new_tag = new_tag.lower().strip()

            if not old_tag or not new_tag:
                return {"success": False, "message": "Tags cannot be empty"}

            if old_tag == new_tag:
                return {"success": False, "message": "Old and new tag names are identical"}

            # Check if old tag exists
            old_tag_key = f"tag:{old_tag}"
            exists = await asyncio.to_thread(self.redis_client.exists, old_tag_key)
            if not exists:
                return {"success": False, "message": f"Tag '{old_tag}' not found"}

            # Get all fact IDs with the old tag
            fact_ids = await asyncio.to_thread(self.redis_client.smembers, old_tag_key)
            fact_ids = [
                fid.decode("utf-8") if isinstance(fid, bytes) else fid
                for fid in fact_ids
            ]

            if not fact_ids:
                # Clean up empty tag index
                await asyncio.to_thread(self.redis_client.delete, old_tag_key)
                return {"success": True, "message": "Tag had no facts", "affected_count": 0}

            # Update each fact's metadata
            updated_count = 0
            for fact_id in fact_ids:
                fact_key = f"fact:{fact_id}"
                metadata_json = await asyncio.to_thread(
                    self.redis_client.hget, fact_key, "metadata"
                )
                if metadata_json:
                    metadata = json.loads(metadata_json)
                    tags = set(metadata.get("tags", []))

                    # Remove old tag, add new tag
                    tags.discard(old_tag)
                    tags.add(new_tag)
                    metadata["tags"] = list(tags)

                    await asyncio.to_thread(
                        self.redis_client.hset,
                        fact_key,
                        "metadata",
                        json.dumps(metadata),
                    )
                    updated_count += 1

            # Update tag indices atomically
            new_tag_key = f"tag:{new_tag}"

            # Add all fact IDs to new tag index
            if fact_ids:
                await asyncio.to_thread(self.redis_client.sadd, new_tag_key, *fact_ids)

            # Delete old tag index
            await asyncio.to_thread(self.redis_client.delete, old_tag_key)

            logger.info(
                "Renamed tag '%s' to '%s', updated %d facts",
                old_tag, new_tag, updated_count
            )

            return {
                "success": True,
                "old_tag": old_tag,
                "new_tag": new_tag,
                "affected_count": updated_count,
                "message": f"Tag renamed successfully, {updated_count} facts updated",
            }

        except Exception as e:
            logger.error("Failed to rename tag '%s' to '%s': %s", old_tag, new_tag, e)
            return {"success": False, "message": str(e)}

    async def delete_tag_globally(self, tag: str) -> Dict[str, Any]:
        """
        Delete a tag from all facts globally.

        This operation:
        1. Gets all fact IDs with the tag
        2. Removes the tag from each fact's metadata
        3. Deletes the tag index

        Args:
            tag: Tag name to delete

        Returns:
            Dict with status and affected fact count
        """
        try:
            # Normalize tag
            tag = tag.lower().strip()
            if not tag:
                return {"success": False, "message": "Tag cannot be empty"}

            # Check if tag exists
            tag_key = f"tag:{tag}"
            exists = await asyncio.to_thread(self.redis_client.exists, tag_key)
            if not exists:
                return {"success": False, "message": f"Tag '{tag}' not found"}

            # Get all fact IDs with this tag
            fact_ids = await asyncio.to_thread(self.redis_client.smembers, tag_key)
            fact_ids = [
                fid.decode("utf-8") if isinstance(fid, bytes) else fid
                for fid in fact_ids
            ]

            # Remove tag from each fact's metadata
            removed_count = 0
            for fact_id in fact_ids:
                fact_key = f"fact:{fact_id}"
                metadata_json = await asyncio.to_thread(
                    self.redis_client.hget, fact_key, "metadata"
                )
                if metadata_json:
                    metadata = json.loads(metadata_json)
                    tags = set(metadata.get("tags", []))

                    if tag in tags:
                        tags.discard(tag)
                        metadata["tags"] = list(tags)

                        await asyncio.to_thread(
                            self.redis_client.hset,
                            fact_key,
                            "metadata",
                            json.dumps(metadata),
                        )
                        removed_count += 1

            # Delete the tag index
            await asyncio.to_thread(self.redis_client.delete, tag_key)

            logger.info("Deleted tag '%s' globally, removed from %d facts", tag, removed_count)

            return {
                "success": True,
                "tag": tag,
                "affected_count": removed_count,
                "message": f"Tag '{tag}' deleted, removed from {removed_count} facts",
            }

        except Exception as e:
            logger.error("Failed to delete tag '%s' globally: %s", tag, e)
            return {"success": False, "message": str(e)}

    async def merge_tags(
        self, source_tags: List[str], target_tag: str
    ) -> Dict[str, Any]:
        """
        Merge multiple source tags into a single target tag.

        All facts with any of the source tags will have those tags replaced
        with the target tag. Source tag indices are deleted.

        Args:
            source_tags: List of tags to merge (will be removed)
            target_tag: Target tag to merge into

        Returns:
            Dict with status and merge statistics
        """
        try:
            # Normalize tags
            source_tags = [t.lower().strip() for t in source_tags if t.strip()]
            target_tag = target_tag.lower().strip()

            if not source_tags:
                return {"success": False, "message": "No source tags provided"}
            if not target_tag:
                return {"success": False, "message": "Target tag cannot be empty"}

            # Remove target from sources if present (no-op for that tag)
            source_tags = [t for t in source_tags if t != target_tag]
            if not source_tags:
                return {
                    "success": True,
                    "message": "No tags to merge (source equals target)",
                    "affected_count": 0,
                }

            # Collect all unique fact IDs from source tags
            all_fact_ids = set()
            existing_source_tags = []

            for source_tag in source_tags:
                tag_key = f"tag:{source_tag}"
                exists = await asyncio.to_thread(self.redis_client.exists, tag_key)
                if exists:
                    existing_source_tags.append(source_tag)
                    fact_ids = await asyncio.to_thread(
                        self.redis_client.smembers, tag_key
                    )
                    for fid in fact_ids:
                        fid_str = fid.decode("utf-8") if isinstance(fid, bytes) else fid
                        all_fact_ids.add(fid_str)

            if not all_fact_ids:
                return {
                    "success": True,
                    "message": "No facts found with source tags",
                    "affected_count": 0,
                }

            # Update each fact's metadata
            updated_count = 0
            for fact_id in all_fact_ids:
                fact_key = f"fact:{fact_id}"
                metadata_json = await asyncio.to_thread(
                    self.redis_client.hget, fact_key, "metadata"
                )
                if metadata_json:
                    metadata = json.loads(metadata_json)
                    tags = set(metadata.get("tags", []))

                    # Remove all source tags
                    for source_tag in existing_source_tags:
                        tags.discard(source_tag)

                    # Add target tag
                    tags.add(target_tag)
                    metadata["tags"] = list(tags)

                    await asyncio.to_thread(
                        self.redis_client.hset,
                        fact_key,
                        "metadata",
                        json.dumps(metadata),
                    )
                    updated_count += 1

            # Update tag indices
            target_tag_key = f"tag:{target_tag}"

            # Add all fact IDs to target tag index
            if all_fact_ids:
                await asyncio.to_thread(
                    self.redis_client.sadd, target_tag_key, *list(all_fact_ids)
                )

            # Delete source tag indices
            for source_tag in existing_source_tags:
                await asyncio.to_thread(self.redis_client.delete, f"tag:{source_tag}")

            logger.info(
                "Merged tags %s into '%s', updated %d facts",
                existing_source_tags, target_tag, updated_count
            )

            return {
                "success": True,
                "source_tags": existing_source_tags,
                "target_tag": target_tag,
                "affected_count": updated_count,
                "message": (
                    f"Merged {len(existing_source_tags)} tags into '{target_tag}', "
                    f"{updated_count} facts updated"
                ),
            }

        except Exception as e:
            logger.error("Failed to merge tags into '%s': %s", target_tag, e)
            return {"success": False, "message": str(e)}

    async def get_facts_by_tag(
        self,
        tag: str,
        limit: int = 50,
        offset: int = 0,
        include_content: bool = False,
    ) -> Dict[str, Any]:
        """
        Get all facts with a specific tag, with pagination.

        Args:
            tag: Tag to search for
            limit: Maximum number of facts to return
            offset: Number of facts to skip
            include_content: Whether to include fact content in results

        Returns:
            Dict with facts and pagination info
        """
        try:
            # Normalize tag
            tag = tag.lower().strip()
            if not tag:
                return {"success": False, "message": "Tag cannot be empty"}

            # Get all fact IDs with this tag
            tag_key = f"tag:{tag}"
            exists = await asyncio.to_thread(self.redis_client.exists, tag_key)
            if not exists:
                return {
                    "success": True,
                    "tag": tag,
                    "facts": [],
                    "total_count": 0,
                    "limit": limit,
                    "offset": offset,
                }

            # Get total count first
            total_count = await asyncio.to_thread(self.redis_client.scard, tag_key)

            # Get all fact IDs and apply pagination
            all_fact_ids = await asyncio.to_thread(self.redis_client.smembers, tag_key)
            fact_ids = [
                fid.decode("utf-8") if isinstance(fid, bytes) else fid
                for fid in all_fact_ids
            ]

            # Sort for consistent pagination
            fact_ids.sort()

            # Apply pagination
            paginated_ids = fact_ids[offset:offset + limit]

            # Fetch fact details
            facts = []
            for fact_id in paginated_ids:
                fact_key = f"fact:{fact_id}"
                fact_data = await asyncio.to_thread(
                    self.redis_client.hgetall, fact_key
                )

                if fact_data:
                    fact_info = {"id": fact_id}

                    # Parse metadata
                    metadata_json = fact_data.get(b"metadata") or fact_data.get("metadata")
                    if metadata_json:
                        if isinstance(metadata_json, bytes):
                            metadata_json = metadata_json.decode("utf-8")
                        fact_info["metadata"] = json.loads(metadata_json)

                    # Include content if requested
                    if include_content:
                        content = fact_data.get(b"content") or fact_data.get("content")
                        if content:
                            if isinstance(content, bytes):
                                content = content.decode("utf-8")
                            fact_info["content"] = content

                    facts.append(fact_info)

            return {
                "success": True,
                "tag": tag,
                "facts": facts,
                "total_count": total_count,
                "returned_count": len(facts),
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count,
            }

        except Exception as e:
            logger.error("Failed to get facts by tag '%s': %s", tag, e)
            return {"success": False, "message": str(e)}

    async def get_tag_info(self, tag: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific tag.

        Args:
            tag: Tag name to get info for

        Returns:
            Dict with tag information including usage count
        """
        try:
            # Normalize tag
            tag = tag.lower().strip()
            if not tag:
                return {"success": False, "message": "Tag cannot be empty"}

            tag_key = f"tag:{tag}"
            exists = await asyncio.to_thread(self.redis_client.exists, tag_key)

            if not exists:
                return {"success": False, "message": f"Tag '{tag}' not found"}

            # Get fact count
            fact_count = await asyncio.to_thread(self.redis_client.scard, tag_key)

            return {
                "success": True,
                "tag": tag,
                "fact_count": fact_count,
            }

        except Exception as e:
            logger.error("Failed to get tag info for '%s': %s", tag, e)
            return {"success": False, "message": str(e)}

    # =========================================================================
    # TAG STYLING OPERATIONS (Issue #410)
    # =========================================================================

    # Default tag colors for auto-assignment
    _DEFAULT_TAG_COLORS = [
        "#3B82F6",  # Blue
        "#10B981",  # Green
        "#F59E0B",  # Amber
        "#EF4444",  # Red
        "#8B5CF6",  # Purple
        "#EC4899",  # Pink
        "#06B6D4",  # Cyan
        "#F97316",  # Orange
    ]

    async def update_tag_style(
        self,
        tag: str,
        color: Optional[str] = None,
        icon: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update tag styling (color, icon, description).

        Issue #410: Tag styling - colors and visual customization.

        Args:
            tag: Tag name to update
            color: Hex color code (e.g., '#3B82F6')
            icon: Optional icon class (e.g., 'fas fa-code')
            description: Optional tag description

        Returns:
            Dict with updated tag style info
        """
        try:
            # Normalize tag
            tag = tag.lower().strip()
            if not tag:
                return {"success": False, "message": "Tag cannot be empty"}

            # Check if tag exists
            tag_key = f"tag:{tag}"
            exists = await asyncio.to_thread(self.redis_client.exists, tag_key)
            if not exists:
                return {"success": False, "message": f"Tag '{tag}' not found"}

            # Build style data
            style_key = f"tag_style:{tag}"
            style_data = {}

            if color is not None:
                style_data["color"] = color
            if icon is not None:
                style_data["icon"] = icon
            if description is not None:
                style_data["description"] = description

            if not style_data:
                return {
                    "success": False,
                    "message": "No style updates provided",
                }

            # Update style in Redis hash
            await asyncio.to_thread(self.redis_client.hset, style_key, mapping=style_data)

            # Get updated style
            updated_style = await self.get_tag_style(tag)

            logger.info("Updated tag '%s' style: %s", tag, style_data)

            return {
                "success": True,
                "tag": tag,
                "style": updated_style.get("style", {}),
                "message": "Tag style updated successfully",
            }

        except Exception as e:
            logger.error("Failed to update tag '%s' style: %s", tag, e)
            return {"success": False, "message": str(e)}

    async def get_tag_style(self, tag: str) -> Dict[str, Any]:
        """
        Get tag styling information.

        Issue #410: Tag styling - colors and visual customization.

        Args:
            tag: Tag name

        Returns:
            Dict with tag style (color, icon, description)
        """
        try:
            # Normalize tag
            tag = tag.lower().strip()
            if not tag:
                return {"success": False, "message": "Tag cannot be empty"}

            style_key = f"tag_style:{tag}"
            style_data = await asyncio.to_thread(self.redis_client.hgetall, style_key)

            # Decode bytes if needed
            style = {}
            for key, value in style_data.items():
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                value_str = value.decode("utf-8") if isinstance(value, bytes) else value
                style[key_str] = value_str

            # If no style exists, assign default color based on tag hash
            if not style.get("color"):
                # Deterministic color assignment based on tag name
                color_index = hash(tag) % len(self._DEFAULT_TAG_COLORS)
                style["color"] = self._DEFAULT_TAG_COLORS[color_index]

            return {
                "success": True,
                "tag": tag,
                "style": style,
            }

        except Exception as e:
            logger.error("Failed to get tag '%s' style: %s", tag, e)
            return {"success": False, "message": str(e)}

    async def get_tag_with_style(self, tag: str) -> Dict[str, Any]:
        """
        Get complete tag information including style and usage.

        Issue #410: Combines tag info and style for complete view.

        Args:
            tag: Tag name

        Returns:
            Dict with tag name, fact_count, and style
        """
        try:
            # Get tag info (fact count)
            tag_info = await self.get_tag_info(tag)
            if not tag_info.get("success"):
                return tag_info

            # Get tag style
            style_info = await self.get_tag_style(tag)

            return {
                "success": True,
                "tag": tag,
                "fact_count": tag_info.get("fact_count", 0),
                "style": style_info.get("style", {}),
            }

        except Exception as e:
            logger.error("Failed to get tag '%s' with style: %s", tag, e)
            return {"success": False, "message": str(e)}

    async def delete_tag_style(self, tag: str) -> Dict[str, Any]:
        """
        Delete tag styling (reset to defaults).

        Issue #410: Remove custom styling for a tag.

        Args:
            tag: Tag name

        Returns:
            Dict with success status
        """
        try:
            tag = tag.lower().strip()
            if not tag:
                return {"success": False, "message": "Tag cannot be empty"}

            style_key = f"tag_style:{tag}"
            deleted = await asyncio.to_thread(self.redis_client.delete, style_key)

            return {
                "success": True,
                "tag": tag,
                "deleted": deleted > 0,
                "message": "Tag style reset to defaults" if deleted else "No custom style existed",
            }

        except Exception as e:
            logger.error("Failed to delete tag '%s' style: %s", tag, e)
            return {"success": False, "message": str(e)}

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    # Method references needed from other mixins
    async def _get_fact_ids_by_tags(self, tags: List[str], match_all: bool = True):
        """Get fact IDs by tags - implemented in search mixin."""
        raise NotImplementedError("Should be implemented in composed class")

    async def _scan_redis_keys_async(self, pattern: str):
        """Scan Redis keys - implemented in base class."""
        raise NotImplementedError("Should be implemented in composed class")
