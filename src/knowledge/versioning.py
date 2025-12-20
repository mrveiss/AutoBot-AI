# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Versioning Module

Issue #414: Implements fact version history tracking and reversion.

Features:
- Track changes to facts over time
- Store configurable number of versions
- Revert to previous versions
- View version history and diffs
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    import aioredis
    import redis

logger = logging.getLogger(__name__)

# Maximum versions to keep per fact
MAX_VERSIONS = 20


class VersioningMixin:
    """
    Version history mixin for knowledge base facts.

    Issue #414: Provides version tracking for facts with ability to
    view history and revert to previous versions.

    Features:
    - Automatic version creation on fact updates
    - Configurable version limit per fact
    - Version comparison/diff
    - Revert to any previous version
    """

    # Type hints for attributes from base class
    redis_client: "redis.Redis"
    aioredis_client: "aioredis.Redis"

    # Redis key patterns
    VERSION_PREFIX = "fact:versions:"
    VERSION_META = "fact:version:meta:"

    async def _get_next_version_number(self, version_meta_key: str) -> int:
        """Get next version number for a fact (Issue #398: extracted)."""
        current_version = await asyncio.to_thread(
            self.redis_client.hget, version_meta_key, "current_version"
        )
        return int(current_version) + 1 if current_version else 1

    async def _store_version_data(
        self, fact_id: str, version_data: Dict, version_num: int
    ) -> None:
        """Store version data in Redis (Issue #398: extracted)."""
        version_list_key = f"{self.VERSION_PREFIX}{fact_id}"
        version_meta_key = f"{self.VERSION_META}{fact_id}"

        await asyncio.to_thread(
            self.redis_client.lpush, version_list_key, json.dumps(version_data)
        )
        await asyncio.to_thread(
            self.redis_client.ltrim, version_list_key, 0, MAX_VERSIONS - 1
        )
        await asyncio.to_thread(
            self.redis_client.hset, version_meta_key, mapping={
                "current_version": str(version_num),
                "total_versions": str(min(version_num, MAX_VERSIONS)),
                "last_updated": datetime.utcnow().isoformat(),
            }
        )

    async def create_version(
        self,
        fact_id: str,
        content: str,
        metadata: Dict[str, Any] = None,
        change_summary: str = None,
        created_by: str = None,
    ) -> Dict[str, Any]:
        """Create a new version for a fact (Issue #398: refactored)."""
        try:
            version_meta_key = f"{self.VERSION_META}{fact_id}"
            version_num = await self._get_next_version_number(version_meta_key)

            version_data = {
                "version": version_num,
                "content": content,
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat(),
                "created_by": created_by,
                "change_summary": change_summary,
            }

            await self._store_version_data(fact_id, version_data, version_num)

            logger.debug("Created version %d for fact %s", version_num, fact_id)
            return {"status": "success", "version": version_num, "fact_id": fact_id}

        except Exception as e:
            logger.error("Failed to create version for %s: %s", fact_id, e)
            return {"status": "error", "message": str(e)}

    async def get_version(
        self, fact_id: str, version: int = None
    ) -> Dict[str, Any]:
        """
        Get a specific version of a fact.

        Args:
            fact_id: Fact ID
            version: Version number (None = latest)

        Returns:
            Dict with version data
        """
        try:
            version_list_key = f"{self.VERSION_PREFIX}{fact_id}"

            if version is None:
                # Get latest version (index 0)
                version_json = await asyncio.to_thread(
                    self.redis_client.lindex, version_list_key, 0
                )
            else:
                # Find specific version
                all_versions = await asyncio.to_thread(
                    self.redis_client.lrange, version_list_key, 0, -1
                )

                version_json = None
                for v in all_versions:
                    v_str = v.decode() if isinstance(v, bytes) else v
                    v_data = json.loads(v_str)
                    if v_data.get("version") == version:
                        version_json = v_str
                        break

            if not version_json:
                return {
                    "status": "error",
                    "message": f"Version {version} not found for fact {fact_id}",
                }

            if isinstance(version_json, bytes):
                version_json = version_json.decode()

            version_data = json.loads(version_json)
            return {
                "status": "success",
                "version": version_data,
                "fact_id": fact_id,
            }

        except Exception as e:
            logger.error("Failed to get version for %s: %s", fact_id, e)
            return {"status": "error", "message": str(e)}

    async def list_versions(
        self, fact_id: str, limit: int = 10
    ) -> Dict[str, Any]:
        """
        List version history for a fact.

        Args:
            fact_id: Fact ID
            limit: Maximum versions to return

        Returns:
            Dict with list of versions (newest first)
        """
        try:
            version_list_key = f"{self.VERSION_PREFIX}{fact_id}"
            versions_raw = await asyncio.to_thread(
                self.redis_client.lrange, version_list_key, 0, limit - 1
            )

            versions = []
            for v in versions_raw:
                v_str = v.decode() if isinstance(v, bytes) else v
                v_data = json.loads(v_str)
                # Include summary info, not full content
                versions.append({
                    "version": v_data.get("version"),
                    "created_at": v_data.get("created_at"),
                    "created_by": v_data.get("created_by"),
                    "change_summary": v_data.get("change_summary"),
                    "content_length": len(v_data.get("content", "")),
                })

            # Get metadata
            version_meta_key = f"{self.VERSION_META}{fact_id}"
            meta = await asyncio.to_thread(
                self.redis_client.hgetall, version_meta_key
            )

            total_versions = 0
            if meta:
                total_str = meta.get(b"total_versions") or meta.get("total_versions")
                if total_str:
                    total_versions = int(
                        total_str.decode() if isinstance(total_str, bytes) else total_str
                    )

            return {
                "status": "success",
                "versions": versions,
                "total_versions": total_versions,
                "fact_id": fact_id,
            }

        except Exception as e:
            logger.error("Failed to list versions for %s: %s", fact_id, e)
            return {"status": "error", "message": str(e), "versions": []}

    async def revert_to_version(
        self,
        fact_id: str,
        version: int,
        created_by: str = None,
    ) -> Dict[str, Any]:
        """
        Revert a fact to a previous version.

        Creates a new version with the content from the specified version.

        Args:
            fact_id: Fact ID to revert
            version: Version number to revert to
            created_by: User/agent performing revert

        Returns:
            Dict with revert result
        """
        try:
            # Get the target version
            result = await self.get_version(fact_id, version)
            if result.get("status") != "success":
                return result

            target_version = result["version"]

            # Get current fact
            fact_key = f"fact:{fact_id}"
            exists = await asyncio.to_thread(self.redis_client.exists, fact_key)
            if not exists:
                return {"status": "error", "message": "Fact not found"}

            # Update fact with version content
            await asyncio.to_thread(
                self.redis_client.hset,
                fact_key,
                mapping={
                    "content": target_version["content"],
                    "metadata": json.dumps(target_version.get("metadata", {})),
                },
            )

            # Create new version for the revert
            revert_summary = f"Reverted to version {version}"
            if target_version.get("change_summary"):
                revert_summary += f": {target_version['change_summary']}"

            await self.create_version(
                fact_id=fact_id,
                content=target_version["content"],
                metadata=target_version.get("metadata"),
                change_summary=revert_summary,
                created_by=created_by,
            )

            logger.info("Reverted fact %s to version %d", fact_id, version)
            return {
                "status": "success",
                "fact_id": fact_id,
                "reverted_to": version,
                "message": f"Successfully reverted to version {version}",
            }

        except Exception as e:
            logger.error("Failed to revert %s to version %d: %s", fact_id, version, e)
            return {"status": "error", "message": str(e)}

    async def compare_versions(
        self, fact_id: str, version_a: int, version_b: int
    ) -> Dict[str, Any]:
        """
        Compare two versions of a fact.

        Args:
            fact_id: Fact ID
            version_a: First version number
            version_b: Second version number

        Returns:
            Dict with comparison details
        """
        try:
            # Get both versions
            result_a = await self.get_version(fact_id, version_a)
            result_b = await self.get_version(fact_id, version_b)

            if result_a.get("status") != "success":
                return result_a
            if result_b.get("status") != "success":
                return result_b

            v_a = result_a["version"]
            v_b = result_b["version"]

            # Compare content
            content_a = v_a.get("content", "")
            content_b = v_b.get("content", "")

            # Simple diff info
            content_changed = content_a != content_b
            length_diff = len(content_b) - len(content_a)

            # Compare metadata
            meta_a = v_a.get("metadata", {})
            meta_b = v_b.get("metadata", {})

            added_keys = set(meta_b.keys()) - set(meta_a.keys())
            removed_keys = set(meta_a.keys()) - set(meta_b.keys())
            modified_keys = {
                k for k in meta_a.keys() & meta_b.keys()
                if meta_a[k] != meta_b[k]
            }

            return {
                "status": "success",
                "fact_id": fact_id,
                "version_a": {
                    "version": version_a,
                    "created_at": v_a.get("created_at"),
                    "content_length": len(content_a),
                },
                "version_b": {
                    "version": version_b,
                    "created_at": v_b.get("created_at"),
                    "content_length": len(content_b),
                },
                "changes": {
                    "content_changed": content_changed,
                    "length_diff": length_diff,
                    "metadata_added": list(added_keys),
                    "metadata_removed": list(removed_keys),
                    "metadata_modified": list(modified_keys),
                },
            }

        except Exception as e:
            logger.error("Failed to compare versions for %s: %s", fact_id, e)
            return {"status": "error", "message": str(e)}

    async def get_version_count(self, fact_id: str) -> int:
        """Get the number of versions for a fact."""
        try:
            version_list_key = f"{self.VERSION_PREFIX}{fact_id}"
            count = await asyncio.to_thread(
                self.redis_client.llen, version_list_key
            )
            return count
        except Exception:
            return 0

    async def delete_version_history(self, fact_id: str) -> Dict[str, Any]:
        """
        Delete all version history for a fact.

        Use with caution - this cannot be undone.

        Args:
            fact_id: Fact ID to delete history for

        Returns:
            Dict with deletion result
        """
        try:
            version_list_key = f"{self.VERSION_PREFIX}{fact_id}"
            version_meta_key = f"{self.VERSION_META}{fact_id}"

            # Get count before deletion
            count = await self.get_version_count(fact_id)

            # Delete version list and metadata
            await asyncio.to_thread(
                self.redis_client.delete, version_list_key, version_meta_key
            )

            logger.info("Deleted %d versions for fact %s", count, fact_id)
            return {
                "status": "success",
                "fact_id": fact_id,
                "versions_deleted": count,
            }

        except Exception as e:
            logger.error("Failed to delete version history for %s: %s", fact_id, e)
            return {"status": "error", "message": str(e)}

    def ensure_initialized(self):
        """Ensure the knowledge base is initialized. Implemented in composed class."""
        raise NotImplementedError("Should be implemented in composed class")
